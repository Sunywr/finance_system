from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None
    data = response.data
    if isinstance(data, dict) and "detail" in data:
        response.data = {"detail": str(data["detail"]), "errors": data}
    elif isinstance(data, list):
        response.data = {"detail": "请求参数有误", "errors": data}
    else:
        response.data = {"detail": "请求参数有误", "errors": data}
    return response
