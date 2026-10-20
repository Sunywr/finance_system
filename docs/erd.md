# 数据模型（摘要）

## 账户域

- `User`：单登录账号；所有业务表带 `owner`。
- `UserSetting`：`payday`、`salary_amount`、`salary_account`、`dashboard_prefs`。
- `Account`：`type`（SAVINGS/PF_MAIN/PF_SUPP/STOCK/WEALTH/ALIPAY/WECHAT）、`opening_balance`、`allow_negative`。
- `ProvidentFundProfile`：一对一账户，主/补充、个人/单位月缴、缴存日。
- `AccountTransfer`：转出/转入账户、金额、手续费、两条流水的 ID。

## 流水域

- `Category`：`kind`（GENERAL/INVESTMENT/STOCK/TRANSFER/REFUND），树形。
- `Tag`：多对多流水。
- `Transaction`：类型（支出/收入/转出/转入/退款）、分类、金额、支付渠道、账户/信用卡、投资操作、退款原流水、分期计划、资产、状态、来源、幂等键。
- `InstallmentPlan`：本金、期数、费率、每期金额、首期账单起始。
- `InstallmentPeriod`：期次、账单起止、还款日、本金/手续费/合计、账单 FK。

## 债务域

- `CreditCard`：账单起始/结束日、还款日、额度、最低还款比例。
- `CreditCardBill`：周期起止、还款截止、普通/分期/退款/合计、最低还款、状态。
- `RecurringDebt`：名称、类型、金额、期数、间隔月、首次到期、支付渠道、账户/信用卡、分类 ID、自动支付。
- `DebtItem`：来源（信用卡账单/周期债务/房贷期次）、到期日、应还、减免、已还、状态。
- `DebtPayment`：金额、减免、渠道、账户/信用卡、支付时间、流水 ID、幂等键。

## 房贷与资产

- `Loan` / `LoanSchedule` / `OffsetPlan`：贷款、逐期本金利息、公积金冲还配置。
- `Asset` / `AssetValuation`：估值方式（关联流水/手工）、估值历史。

## 投资

- `Instrument`：代码/名称/类型/市场/行业/估值方式/股息率。
- `Trade`：账户、标的、资金流水、方向、操作、数量、价格、费用、已实现盈亏。
- `Quote` / `DailyBar` / `IndicatorSnapshot`：最新行情、日线、技术指标。
- `Watchlist`：自选、目标买卖价。
- `ReportEvent`：报告类型、报告期、预约/实际披露、营收/净利/同比/ROE。
- `MarketRegime`：日期、风向、评分、指数/均线、涨跌家数、行业动量。
- `ScreenerPreset` / `ScreenerRun` / `ScreenerResult`：筛选条件、运行记录、结果评分与理由。
- `IPOCalendar`：申购日、上市日、发行价、申购上限、所需市值。
- `StrategySignal`：B/S 点、网格、股息信号，区间/置信度/依据。

## 系统

- `JobRun`：定时任务运行状态与统计。
- `AIProviderConfig` / `AIAnalysis`：AI 服务配置（Key 加密）与分析历史。
