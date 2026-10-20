# API 概览

Base URL：`http://127.0.0.1:8000/api/v1`；交互式文档：`/api/docs`；OpenAPI：`/api/schema`。

认证：`POST /auth/token`、`POST /auth/token/refresh`、`GET /auth/me`；除登录/健康检查外均需 `Authorization: Bearer <access>`。

## 账户与设置

- `GET/PATCH /settings`
- `GET/POST /accounts/`；`GET/PATCH/DELETE /accounts/{id}/`
- `GET /accounts/{id}/balance/`
- `GET/PUT /accounts/{id}/pf-profile/`
- `GET/POST /transfers/`

## 分类/标签/流水

- `GET/POST /categories/`、`GET /categories/tree/`
- `GET/POST /tags/`
- `GET/POST /transactions/`；`GET/PATCH/DELETE /transactions/{id}/`
- `POST /transactions/{id}/refund/`、`POST /transactions/{id}/void/`
- `POST /transactions/installment-preview/`

## 信用卡与债务

- `GET/POST /credit-cards/`；`GET /credit-cards/{id}/current/`、`/bills/`、`/installments/`
- `POST /credit-cards/generate/`
- `GET /bills/`、`POST /bills/{id}/pay/`
- `GET /debts/`、`POST /debts/{id}/pay/`、`POST /debts/{id}/cancel/`、`GET /debts/summary/`
- `GET/POST /recurring-debts/`、`GET /recurring-debts/{id}/items/`
- `GET /debt-payments/`

## 房贷

- `GET/POST /loans/`；`GET /loans/{id}/schedule/`、`/summary/`
- `GET/PUT /loans/{id}/offset-plan/`
- `GET/POST /loans/{id}/offset-simulation/`

## 资产

- `GET/POST /assets/`；`GET /assets/{id}/transactions/`
- `GET/POST /assets/{id}/valuations/`

## 投资

- `GET/POST /instruments/`；`GET/PATCH/DELETE /instruments/{id}/`
- `GET /instruments/{id}/quote/`、`/bars/`、`/indicators/`
- `POST /instruments/{id}/sync/`
- `POST /market/sync`
- `GET/POST /trades/`
- `GET /holdings`
- `GET/POST /watchlist/`

## 投资智能

- `GET/POST /market/regime`
- `GET/POST /screener/presets/`
- `GET/POST /screener/runs/`
- `GET/POST /ipo`
- `GET /signals/`
- `GET/POST /instruments/{id}/signals/`
- `GET /instruments/{id}/reports/`、`POST /instruments/{id}/sync-reports/`
- `GET /instruments/{id}/grid-plan/`

## AI 与总览

- `GET/POST /ai/providers/`；`POST /ai/providers/{id}/test/`
- `GET/POST /ai/analyses/`；`GET /ai/analyses/{id}/`
- `GET /dashboard/overview`
- `GET /dashboard/cashflow`
- `GET /meta/enums`
- `GET /health`
