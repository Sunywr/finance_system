# 架构说明

## 总体

- 前端：Vue 3 + TypeScript + Vite + Element Plus + ECharts + Pinia + Vue Router。
- 后端：Django 5.2 + DRF + SimpleJWT + drf-spectacular；MySQL 8（开发可用独立 3307 实例）。
- 定时任务：APScheduler 独立进程 `manage.py run_scheduler`，任务本身也提供管理命令，幂等可重跑。
- 行情：东方财富 HTTP 接口，强制绕过系统代理，带重试与本地缓存；akshare 作为可选依赖。

## 后端应用

| App | 职责 |
|---|---|
| `users` | 自定义 User、JWT 当前用户信息 |
| `accounts` | Account、公积金配置、UserSetting、余额聚合 |
| `ledger` | 分类/标签、流水、账户转账、分期计划与期次 |
| `debts` | 信用卡、账单周期、债务项、周期债务、还款、自动扣款 |
| `mortgages` | 贷款、还款计划、公积金冲还配置与模拟 |
| `assets` | 资产、估值历史、关联流水汇总 |
| `investments` | 标的、交易、持仓、行情/日线/指标、报告、筛选、信号、打新 |
| `insights` | AI Provider/Analysis、总览现金流、月度序列、枚举 |
| `common` | JobRun、分页、异常、金额/日期/加密工具、调度命令 |

## 关键依赖方向

`users -> accounts -> mortgages -> debts -> assets -> ledger -> investments`。

为避免迁移循环，`ledger.Transaction` 通过外键引用 `debts.CreditCard`/`assets.Asset`/`accounts.Account`；反向的还款流水与交易链接使用 `BigIntegerField`（如 `DebtPayment.transaction_id`、`AccountTransfer.in_transaction_id`）。`RecurringDebt.category_id` 也使用整数 ID，避免 debts 与 ledger 的循环依赖。

## 数据流

1. 记账：`Transaction` 写入后，按 `occurred_at` 归入信用卡周期；`refresh_bill_for_card_date` 重算当前/历史账单。
2. 出账：`generate_due_bills` 关闭已结束周期，生成 `CreditCardBill` 与 `DebtItem`。
3. 还款：`settle_debt` 原子地锁债务项、写还款、生成流水、更新状态；信用卡还款是 `TRANSFER_OUT`，不重复计消费。
4. 分期：`InstallmentPlan` 一次生成全部 `InstallmentPeriod`，账单关闭时计入；原始消费流水 `exclude_from_card_bill=True`。
5. 房贷：`LoanSchedule` 生成后滚动生成 `DebtItem(MORTGAGE)`；冲还模拟用 PF 余额 + 月缴逐期扣减。
6. 投资：`Trade` 与一条资金流水一一对应；持仓由交易重算，行情/指标缓存到 `Quote`/`DailyBar`/`IndicatorSnapshot`。
7. 总览：账户余额 + 应付债务 + 发薪日 → 每日余额曲线与月度现金流序列；所有日期过滤使用 aware datetime 区间，避免 MySQL 缺失时区表时 `CONVERT_TZ` 返回 NULL。
8. 投资智能：东方财富股票池 → 条件过滤/评分 → 可选技术指标复核 → `ScreenerResult`；市场风向、报告、信号、打新分别落库。

## 金额与日期

- 金额：`Decimal(18,2)`，`ROUND_HALF_UP`；分期本金/手续费分别均摊，尾差落最后一期。
- 日期：数据库存 UTC，业务按 `Asia/Shanghai`；账单周期包含起始日 00:00 至结束日 23:59:59。
- 月末：`clamp_day` 统一将 29/30/31 钳制到当月最后一天。

## 幂等与并发

- 生成任务使用 `get_or_create`/唯一约束（账单周期、分期期次、周期债务期次、房贷期次）。
- 还款使用 `select_for_update` 锁债务项；`DebtPayment`/`Transaction` 支持幂等键。
- 行情重试 5 次；失败时保留缓存并标记 `is_stale`；市场风向失败时回退最近一次记录。

## 安全

- JWT 访问 30 分钟、刷新 7 天，轮换 + 黑名单；关闭注册。
- 所有业务查询按 `owner` 过滤。
- AI Key 使用 Fernet 加密，接口只返回掩码；日志不打印密钥。
- MySQL 独立实例仅监听 `127.0.0.1:3307`，数据目录在 `.mysql-data/`（gitignore）。

## 测试

- 后端 pytest + MySQL 测试库，覆盖金额/日期、账单、分期、还款、房贷冲还、投资持仓、仪表盘、API CRUD。
- 前端 `vue-tsc --noEmit` + `vite build`。
