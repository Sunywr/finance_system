# 财务系统

个人/家庭财务管理系统：记账流水、账户互转、信用卡账单与债务、周期债务、房贷与公积金冲还、资产、投资持仓与行情指标、可配置 AI 财务分析、发薪日前现金流总览。

技术栈：Vue 3 + TypeScript + Vite + Element Plus + ECharts；Django 5.2 + DRF + MySQL 8；Gunicorn + Nginx；APScheduler；东方财富免费行情。

## 已实现功能

- 账户：储蓄卡、公积金主/补充账户、股票、理财、支付宝、微信；账户互转自动生成两条流水。
- 流水：分类树、系统特殊分类（理财/股票/转账/退款）、标签、现金/信用卡/公积金/支付宝/微信/股票账户支付、退款关联原流水、作废、资产关联或创建。
- 信用卡：账单起止日、还款日、额度；按周期自动出账；账单金额由周期内流水 + 分期期次 - 退款统计；最低还款、还款减免、部分还款。
- 分期：输入金额和期数自动计算每期金额（分币尾差落在最后一期），首期进入购买周期的下一期，随账单出账。
- 债务：信用卡债务、周期债务（期数 + 间隔月）、房贷债务统一视图；部分还款、减免、逾期、取消、自动生成任务。
- 房贷：商贷/公积金贷款，等额本息/等额本金，完整还款计划；公积金冲还配置与模拟（可支撑月数、第一笔现金日期、逐期分摊）；到期自动扣公积金/现金。
- 资产：关联多笔流水按金额汇总，或手工估值（保留估值历史）。
- 投资：股票/ETF/场外基金/理财；股票账户可买理财；加权平均成本、已实现/未实现盈亏、分红、收益率、上次交易至今收益；东方财富行情、K 线/MA/MACD/KDJ/RSI/BOLL；自选。
- 投资智能：市场风向/行业动量、全市场低估值/股息/趋势/超跌筛选（带评分与理由）、季报/年报日历与业绩风向、B/S 点信号、股息持有、打新日历与市值资格、网格降成本测算。
- 总览：发薪日配置、发薪日前每日现金余额、近 6 个月 + 未来 3 个月现金流/信用卡还款/周期债务折线、应还清单、资产负债。
- AI：OpenAI 兼容服务配置（DeepSeek/OpenAI/Moonshot/Ollama/商汤 SenseNova 等）、Key 加密、连接测试、聚合数据分析、历史记录；支持 429/5xx 自动重试与 thinking 开关；分析结果使用 Markdown 渲染并做 XSS 过滤。
- 基础设施：JWT、OpenAPI/Swagger、定时任务、演示数据、pytest 测试。
- 生产部署：前后端分离，后端 Ubuntu 24.04 + Gunicorn + Nginx + MySQL，前端 AnolisOS 8.4 + Nginx；配置见 [deploy/README.md](deploy/README.md)。

## 目录

```
backend/   Django + DRF + MySQL
frontend/  Vue 3 + Vite
scripts/   init_db.ps1 / start_mysql_local.ps1 / stop_mysql_local.ps1 / dev.ps1
deploy/    生产部署：Gunicorn/Nginx/systemd/环境变量/备份
docs/      架构说明
```

## 快速开始

### 1. 数据库

系统要求 MySQL 8。提供两种方式：

**方式 A：使用本机已有的 MySQL 服务（3306）**

```powershell
powershell -ExecutionPolicy Bypass -File scripts/init_db.ps1
```

脚本会安全提示输入 root 密码，创建 `finance` 库、`finance_app` 账号、`test_finance` 测试库，并更新 `backend/.env`。密码不会写入仓库。

**方式 B：使用项目内置的独立 MySQL 实例（3307，当前 `.env` 已指向此实例）**

无需 root 密码，数据目录在 `.mysql-data/`（已被 gitignore）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_mysql_local.ps1
powershell -ExecutionPolicy Bypass -File scripts/stop_mysql_local.ps1
```

独立实例仅监听 `127.0.0.1:3307`，使用 `finance_app` 账号；`backend/.env` 中的 `DB_PORT` 需为 `3307`。该实例仅用于本地开发/验收，不作为生产数据库。

> 首次使用方式 A 或方式 B 后，执行 `python manage.py migrate`。SQLite 仅作为无 MySQL 时的临时回退，最终验收以 MySQL 8 为准。

### 2. 后端

```powershell
cd backend
python -m pip install -r requirements-dev.txt
python manage.py migrate
python manage.py seed_system_data
python manage.py seed_demo          # 可选，生成演示数据
python manage.py runserver 127.0.0.1:8000
```

默认账号：`admin / admin123456`（登录后请在设置页修改）。

### 3. 前端

```powershell
cd frontend
pnpm install
pnpm dev
```

打开 http://127.0.0.1:5173 。API 文档：http://127.0.0.1:8000/api/docs 。

### 4. 定时任务

```powershell
cd backend
python manage.py run_scheduler
```

任务：每日 00:10 生成账单/债务项；00:30 自动还款；每月 1 日公积金缴存；交易日 15:30 同步行情；交易日 18:30 刷新市场风向、打新日历并运行默认筛选器。所有任务幂等，可手动执行：

```powershell
python manage.py generate_financial_cycles
python manage.py settle_auto_payments
python manage.py generate_pf_contributions
python manage.py sync_market_data
python manage.py refresh_investment_intelligence --skip-screener
```

## 测试与构建

```powershell
cd backend
python -m pytest -q

cd frontend
pnpm typecheck
pnpm build
```

## 配置

`backend/.env`：

| 变量 | 说明 |
|---|---|
| `DB_ENGINE` | `mysql` 或 `sqlite` |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` | MySQL 连接 |
| `SECRET_KEY` | Django 密钥 |
| `AI_ENCRYPTION_KEY` | AI Key 加密密钥，留空时从 `SECRET_KEY` 派生 |
| `MARKET_DATA_TIMEOUT` | 行情请求超时秒数 |
| `CSRF_TRUSTED_ORIGINS` | 生产域名，逗号分隔，如 `https://finance.example.com` |
| `USE_X_FORWARDED_HOST` / `USE_X_FORWARDED_PROTO` | 位于 Nginx 后时设为 `1` |
| `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` | HTTPS 生产设为 `1` |
| `SECURE_SSL_REDIRECT` | 生产建议 `1`；前端 Nginx 传入 `X-Forwarded-Proto: https` 后不会循环重定向 |

AI 服务在页面「AI 分析」中配置，API Key 使用 Fernet 加密存储，接口只返回掩码。

### 商汤 SenseNova DeepSeek V4.1 Flash

| 配置项 | 值 |
|---|---|
| Base URL | `https://token.sensenova.cn/v1` |
| 模型 | `deepseek-flash` |
| 额外请求体 | `{"thinking":{"type":"disabled"}}` |
| max_tokens | 2048（不足时增大） |
| 重试 | 2 次，等待 60 秒 |

该模型默认开启思考模式，`reasoning_content` 会占用输出 token；关闭 thinking 可获得直接回答并降低 TPM 消耗。遇到 429（`EndpointRPMExceeded` / `EndpointTPMExceeded`）时后端会自动等待重试，仍失败请检查 token plan 配额或更换 Key。页面上的「填充商汤 DeepSeek V4.1 Flash」可一键填入上述配置。

## 主要业务规则

- 信用卡账单周期包含起始日 00:00 至结束日 23:59:59；周期结束后出账；还款日取周期结束后第一个 `due_day`，月末钳制。
- 分期原始消费只计入消费统计一次，不计入信用卡账单；分期期次单独进入账单。
- 信用卡还款是账户间资金转移，不计入消费支出；周期债务/房贷支付计入支出。
- 房贷只支持现金/公积金支付；公积金冲还到期自动扣 PF，现金差额按配置自动或待确认。
- 投资采用加权平均成本，买入费用计入成本；卖出按平均成本结转已实现盈亏。
- 金额全部使用 Decimal，分期/还款分币尾差精确处理。

## 投资智能说明

- 筛选器默认按总市值前 1000 只 A 股构建股票池（东方财富接口分页，单页 100 条）；技术条件会对排名靠前的标的额外拉取日线。
- 市场风向基于沪深 300 的 MA20/MA60、涨跌家数宽度、行业平均涨跌幅计算，属于规则化评分，不是预测。
- 季报/年报通过东方财富数据中心同步；B/S 点、股息、网格均为规则信号，仅供决策参考，不自动下单。
- 打新资格按当前股票持仓市值与 `TOP_APPLY_MARKETCAP`（万元）估算，实际以券商规则为准。
- 所有行情接口均为免费延迟数据，网络异常时自动重试并回退到最近一次缓存/记录。

## 说明

- 系统为单登录账号设计，所有业务表保留 `owner` 字段。
- 行情为免费延迟数据，仅覆盖 A 股/场内基金；所有技术指标、AI 结论均为参考信息，不构成投资建议。
- 记账数据需手工录入，暂未接入银行/券商自动同步。
