from unittest.mock import Mock, patch

import pytest

from apps.common.utils.crypto import encrypt_text
from apps.insights.models import AIProviderConfig
from apps.insights.services import _chat_url, call_provider

pytestmark = pytest.mark.django_db


def _provider(user, **overrides):
    defaults = {
        "owner": user,
        "name": "SenseNova",
        "base_url": "https://token.sensenova.cn/v1",
        "api_key_encrypted": encrypt_text("sk-test"),
        "model": "deepseek-flash",
        "max_tokens": 2048,
        "timeout_seconds": 90,
        "max_retries": 1,
        "retry_wait_seconds": 1,
        "extra_body": {"thinking": {"type": "disabled"}},
    }
    defaults.update(overrides)
    return AIProviderConfig.objects.create(**defaults)


def _response(status, payload, headers=None):
    response = Mock()
    response.status_code = status
    response.headers = headers or {}
    response.json.return_value = payload
    response.text = str(payload)
    return response


def test_chat_url_accepts_base_or_full_endpoint():
    assert _chat_url("https://token.sensenova.cn/v1") == "https://token.sensenova.cn/v1/chat/completions"
    assert (
        _chat_url("https://token.sensenova.cn/v1/chat/completions")
        == "https://token.sensenova.cn/v1/chat/completions"
    )


@patch("apps.insights.services.requests.post")
@patch("apps.insights.services.time.sleep")
def test_call_provider_retries_429_and_disables_sensenova_thinking(sleep, post, user):
    provider = _provider(user)
    first = _response(429, {"error": {"message": "rate limit", "code": "EndpointRPMExceeded"}}, {"Retry-After": "1"})
    second = _response(
        200,
        {
            "choices": [{"message": {"content": "OK"}}],
            "usage": {"total_tokens": 12},
        },
    )
    post.side_effect = [first, second]
    content, tokens = call_provider(provider, [{"role": "user", "content": "hi"}], max_tokens=64)
    assert content == "OK"
    assert tokens == 12
    assert sleep.called
    sent_payload = post.call_args.kwargs["json"]
    assert sent_payload["max_tokens"] == 64
    assert sent_payload["thinking"] == {"type": "disabled"}


@patch("apps.insights.services.requests.post")
@patch("apps.insights.services.time.sleep")
def test_call_provider_raises_clear_error_after_429(sleep, post, user):
    provider = _provider(user, max_retries=0)
    post.return_value = _response(
        429, {"error": {"message": "exceeds tpm/rpm limit", "code": "RateLimitExceeded.EndpointTPMExceeded"}}
    )
    with pytest.raises(RuntimeError, match="限流"):
        call_provider(provider, [{"role": "user", "content": "hi"}], max_tokens=64)


def test_call_provider_requires_final_content(user):
    provider = _provider(user)
    response = _response(
        200,
        {
            "choices": [{"message": {"content": "", "reasoning_content": "thinking only"}}],
            "usage": {"total_tokens": 10},
        },
    )
    with patch("apps.insights.services.requests.post", return_value=response):
        with pytest.raises(RuntimeError, match="reasoning_content"):
            call_provider(provider, [{"role": "user", "content": "hi"}], max_tokens=64)
