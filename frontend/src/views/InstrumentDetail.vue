<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">
          {{ instrument?.symbol }} <span class="muted">{{ instrument?.name }}</span>
        </h2>
        <div class="page-subtitle">
          {{ instrument?.type_label }} · {{ instrument?.exchange_label }} · {{ instrument?.industry || '未分类行业' }}
          <el-tag v-if="quote?.is_stale" size="small" type="warning" class="ml-8">缓存行情</el-tag>
        </div>
      </div>
      <div class="header-actions">
        <el-button @click="$router.push('/investments')">返回</el-button>
        <el-button :loading="syncing" @click="sync">同步行情</el-button>
        <el-button @click="addWatch">加入自选</el-button>
        <el-button type="primary" @click="$router.push('/investments')">去交易</el-button>
      </div>
    </div>

    <div class="card-grid">
      <StatCard label="最新价" :value="money(latestPrice)" :extra="quote?.updated_at || '暂无行情'" />
      <StatCard
        label="涨跌幅"
        :value="percent(quote?.change_pct)"
        :tone="Number(quote?.change_pct || 0) >= 0 ? 'amount-positive' : 'amount-negative'"
        :extra="`昨收 ${money(quote?.prev_close)}`"
      />
      <StatCard label="持仓" :value="holding ? `${Number(holding.quantity).toFixed(2)} 股/份` : '未持有'" :extra="holding ? `成本价 ${Number(holding.avg_cost).toFixed(4)}` : ''" />
      <StatCard label="持仓收益" :value="holding ? `¥ ${money(holding.total_pnl)}` : '—'" :tone="Number(holding?.total_pnl || 0) >= 0 ? 'amount-positive' : 'amount-negative'" :extra="holding ? percent(holding.return_rate) : ''" />
      <StatCard label="上次交易至今" :value="holding ? percent(holding.since_last_trade_return) : '—'" :extra="holding ? `${holding.days_since_last_trade ?? '—'} 天` : ''" />
    </div>

    <div class="panel">
      <div class="panel-header">
        <h3 class="panel-title">K 线 / MA / 成交量</h3>
        <span class="muted">{{ bars.length }} 根日线</span>
      </div>
      <BaseChart v-if="bars.length" :option="candleOption" height="420px" />
      <el-empty v-else description="暂无日线数据，请点击同步行情" />
    </div>

    <div class="two-column">
      <div class="panel">
        <div class="panel-header"><h3 class="panel-title">MACD</h3></div>
        <BaseChart v-if="indicatorRows.length" :option="macdOption" height="250px" />
        <el-empty v-else description="暂无指标" :image-size="50" />
      </div>
      <div class="panel">
        <div class="panel-header"><h3 class="panel-title">KDJ</h3></div>
        <BaseChart v-if="indicatorRows.length" :option="kdjOption" height="250px" />
        <el-empty v-else description="暂无指标" :image-size="50" />
      </div>
    </div>

    <div class="two-column">
      <div class="panel">
        <div class="panel-header"><h3 class="panel-title">RSI</h3></div>
        <BaseChart v-if="indicatorRows.length" :option="rsiOption" height="250px" />
        <el-empty v-else description="暂无指标" :image-size="50" />
      </div>
      <div class="panel">
        <div class="panel-header">
          <h3 class="panel-title">技术信号</h3>
          <span class="muted">规则计算，仅供参考</span>
        </div>
        <div class="signals">
          <el-tag v-for="(value, key) in activeSignals" :key="key" type="warning" class="signal-tag">{{ value }}</el-tag>
          <span v-if="!Object.keys(activeSignals).length" class="muted">暂无明确信号</span>
        </div>
        <el-descriptions :column="2" border size="small" class="indicator-desc">
          <el-descriptions-item label="MA20">{{ money(indicatorLatest?.ma20) }}</el-descriptions-item>
          <el-descriptions-item label="MA60">{{ money(indicatorLatest?.ma60) }}</el-descriptions-item>
          <el-descriptions-item label="MACD DIF">{{ number(indicatorLatest?.macd_dif, 4) }}</el-descriptions-item>
          <el-descriptions-item label="MACD DEA">{{ number(indicatorLatest?.macd_dea, 4) }}</el-descriptions-item>
          <el-descriptions-item label="KDJ K">{{ number(indicatorLatest?.kdj_k, 2) }}</el-descriptions-item>
          <el-descriptions-item label="RSI6">{{ number(indicatorLatest?.rsi6, 2) }}</el-descriptions-item>
          <el-descriptions-item label="BOLL 上轨">{{ money(indicatorLatest?.boll_upper) }}</el-descriptions-item>
          <el-descriptions-item label="BOLL 下轨">{{ money(indicatorLatest?.boll_lower) }}</el-descriptions-item>
        </el-descriptions>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header">
        <h3 class="panel-title">定期报告与风向</h3>
        <el-button size="small" :loading="syncingReports" @click="syncReports">同步报告</el-button>
      </div>
      <div v-if="reportsData.trend" class="report-trend">
        <el-tag :type="reportsData.trend.direction === '向好' ? 'success' : reportsData.trend.direction === '承压' ? 'danger' : 'info'">
          {{ reportsData.trend.direction }}
        </el-tag>
        <span>营收同比 {{ percent(reportsData.trend.avg_revenue_yoy) }}</span>
        <span>净利同比 {{ percent(reportsData.trend.avg_profit_yoy) }}</span>
        <span v-if="reportsData.upcoming" class="muted">下次披露 {{ reportsData.upcoming.disclosure_date || '待定' }}</span>
      </div>
      <el-table :data="reportsData.items" size="small" max-height="260">
        <el-table-column prop="report_type_label" label="报告" width="90" />
        <el-table-column prop="period_end" label="报告期" width="110" />
        <el-table-column prop="disclosure_date" label="预约披露" width="110" />
        <el-table-column prop="status_label" label="状态" width="90" />
        <el-table-column label="营收同比" width="100" align="right">
          <template #default="{ row }">{{ percent(row.revenue_yoy) }}</template>
        </el-table-column>
        <el-table-column label="净利同比" width="100" align="right">
          <template #default="{ row }">{{ percent(row.profit_yoy) }}</template>
        </el-table-column>
        <el-table-column label="ROE" width="80" align="right">
          <template #default="{ row }">{{ percent(row.roe) }}</template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!reportsData.items.length" description="暂无报告数据，点击同步报告" :image-size="50" />
    </div>

    <div class="panel">
      <div class="panel-header">
        <h3 class="panel-title">策略信号与网格</h3>
        <el-button size="small" :loading="analyzing" @click="analyzeSignals">分析信号</el-button>
      </div>
      <el-table :data="signalRows" size="small" max-height="260">
        <el-table-column prop="signal_type_label" label="信号" width="110" />
        <el-table-column prop="trade_date" label="日期" width="110" />
        <el-table-column label="区间" width="170" align="right">
          <template #default="{ row }">{{ money(row.price_low) }} ~ {{ money(row.price_high) }}</template>
        </el-table-column>
        <el-table-column prop="confidence" label="置信" width="70" align="right" />
        <el-table-column label="依据" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ (row.reasons || []).join('；') }}</template>
        </el-table-column>
      </el-table>
      <div v-if="grid" class="grid-box">
        <div class="grid-title">网格测算</div>
        <div class="grid-row">
          <span>买入参考 <strong>{{ money(grid.buy_price) }}</strong></span>
          <span>卖出参考 <strong>{{ money(grid.sell_price) }}</strong></span>
          <span>潜在降本 <strong>{{ Number(grid.potential_reduction_pct).toFixed(2) }}%</strong></span>
        </div>
        <div class="muted small">{{ grid.note }}</div>
      </div>
      <el-empty v-if="!signalRows.length" description="暂无信号，点击分析信号" :image-size="50" />
    </div>

    <div class="panel">
      <div class="panel-header">
        <h3 class="panel-title">交易记录</h3>
      </div>
      <el-table :data="trades" size="small">
        <el-table-column prop="trade_date" label="时间" width="170" />
        <el-table-column prop="side_label" label="方向" width="90" />
        <el-table-column prop="operation_label" label="操作" width="90" />
        <el-table-column label="数量" width="110" align="right">
          <template #default="{ row }">{{ Number(row.quantity).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="价格" width="110" align="right">
          <template #default="{ row }">{{ Number(row.price).toFixed(4) }}</template>
        </el-table-column>
        <el-table-column label="金额" width="130" align="right">
          <template #default="{ row }">¥ {{ money(row.amount) }}</template>
        </el-table-column>
        <el-table-column label="已实现盈亏" width="130" align="right">
          <template #default="{ row }">
            <span v-if="row.realized_pnl !== null" :class="Number(row.realized_pnl) >= 0 ? 'amount-positive' : 'amount-negative'">
              ¥ {{ money(row.realized_pnl) }}
            </span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="note" label="备注" min-width="160" />
      </el-table>
      <el-empty v-if="!trades.length" description="暂无交易" :image-size="60" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import BaseChart from '@/components/BaseChart.vue'
import StatCard from '@/components/StatCard.vue'
import { api } from '@/api'
import { errorMessage, money, percent } from '@/api/client'

const route = useRoute()
const instrumentId = Number(route.params.id)
const instrument = ref<any>(null)
const quote = ref<any>(null)
const bars = ref<any[]>([])
const indicatorRows = ref<any[]>([])
const indicatorLatest = ref<any>(null)
const signals = ref<any>({})
const trades = ref<any[]>([])
const holding = ref<any>(null)
const syncing = ref(false)
const syncingReports = ref(false)
const analyzing = ref(false)
const reportsData = ref<any>({ trend: null, items: [], upcoming: null })
const signalRows = ref<any[]>([])
const grid = ref<any>(null)

const signalLabels: any = {
  macd_golden_cross: 'MACD 金叉',
  macd_death_cross: 'MACD 死叉',
  kdj_golden_cross: 'KDJ 金叉',
  above_ma20: '站上 MA20',
  above_ma60: '站上 MA60',
  kdj_oversold: 'KDJ 超卖',
  kdj_overbought: 'KDJ 超买',
  rsi_oversold: 'RSI 超卖',
  rsi_overbought: 'RSI 超买',
}

const activeSignals = computed(() => {
  const result: any = {}
  Object.entries(signals.value || {}).forEach(([key, value]) => {
    if (value) result[key] = signalLabels[key] || key
  })
  return result
})

const latestPrice = computed(() => quote.value?.price ?? instrument.value?.latest_price ?? 0)
const dates = computed(() => bars.value.map((bar) => bar.trade_date))
const rowsByDate = computed(() => {
  const map: any = {}
  indicatorRows.value.forEach((row) => {
    map[row.trade_date] = row
  })
  return map
})
const seriesValues = (key: string) =>
  dates.value.map((date) => {
    const value = rowsByDate.value[date]?.[key]
    return value === null || value === undefined ? null : Number(value)
  })

const candleOption = computed(() => ({
  animation: false,
  tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
  legend: { top: 0, data: ['K线', 'MA5', 'MA10', 'MA20', 'MA60'] },
  axisPointer: { link: [{ xAxisIndex: 'all' }] },
  grid: [
    { left: 64, right: 20, top: 34, height: '52%' },
    { left: 64, right: 20, top: '72%', height: '16%' },
  ],
  xAxis: [
    { type: 'category', data: dates.value, gridIndex: 0, boundaryGap: true, axisLabel: { show: false } },
    { type: 'category', data: dates.value, gridIndex: 1, boundaryGap: true },
  ],
  yAxis: [
    { scale: true, gridIndex: 0 },
    { scale: true, gridIndex: 1, axisLabel: { show: false } },
  ],
  dataZoom: [
    { type: 'inside', xAxisIndex: [0, 1], start: 55, end: 100 },
    { type: 'slider', xAxisIndex: [0, 1], bottom: 0, height: 18, start: 55, end: 100 },
  ],
  series: [
    {
      name: 'K线',
      type: 'candlestick',
      data: bars.value.map((bar) => [Number(bar.open), Number(bar.close), Number(bar.low), Number(bar.high)]),
      itemStyle: { color: '#ef4444', color0: '#10b981', borderColor: '#ef4444', borderColor0: '#10b981' },
    },
    { name: 'MA5', type: 'line', symbol: 'none', data: seriesValues('ma5'), lineStyle: { width: 1 }, itemStyle: { color: '#f59e0b' } },
    { name: 'MA10', type: 'line', symbol: 'none', data: seriesValues('ma10'), lineStyle: { width: 1 }, itemStyle: { color: '#3b82f6' } },
    { name: 'MA20', type: 'line', symbol: 'none', data: seriesValues('ma20'), lineStyle: { width: 1 }, itemStyle: { color: '#8b5cf6' } },
    { name: 'MA60', type: 'line', symbol: 'none', data: seriesValues('ma60'), lineStyle: { width: 1 }, itemStyle: { color: '#64748b' } },
    {
      name: '成交量',
      type: 'bar',
      xAxisIndex: 1,
      yAxisIndex: 1,
      data: bars.value.map((bar) => Number(bar.volume)),
      itemStyle: { color: '#93c5fd' },
    },
  ],
}))

const macdOption = computed(() => ({
  animation: false,
  tooltip: { trigger: 'axis' },
  legend: { top: 0 },
  grid: { left: 54, right: 18, top: 32, bottom: 26 },
  xAxis: { type: 'category', data: dates.value, axisLabel: { show: false } },
  yAxis: { type: 'value', scale: true },
  series: [
    {
      name: 'MACD',
      type: 'bar',
      data: seriesValues('macd_hist').map((value) => ({
        value,
        itemStyle: { color: Number(value) >= 0 ? '#ef4444' : '#10b981' },
      })),
    },
    { name: 'DIF', type: 'line', symbol: 'none', data: seriesValues('macd_dif'), itemStyle: { color: '#3b82f6' } },
    { name: 'DEA', type: 'line', symbol: 'none', data: seriesValues('macd_dea'), itemStyle: { color: '#f59e0b' } },
  ],
}))

const kdjOption = computed(() => ({
  animation: false,
  tooltip: { trigger: 'axis' },
  legend: { top: 0 },
  grid: { left: 44, right: 18, top: 32, bottom: 26 },
  xAxis: { type: 'category', data: dates.value, axisLabel: { show: false } },
  yAxis: { type: 'value', scale: true, min: 0, max: 100 },
  series: [
    { name: 'K', type: 'line', symbol: 'none', data: seriesValues('kdj_k'), itemStyle: { color: '#3b82f6' } },
    { name: 'D', type: 'line', symbol: 'none', data: seriesValues('kdj_d'), itemStyle: { color: '#f59e0b' } },
    { name: 'J', type: 'line', symbol: 'none', data: seriesValues('kdj_j'), itemStyle: { color: '#8b5cf6' } },
  ],
}))

const rsiOption = computed(() => ({
  animation: false,
  tooltip: { trigger: 'axis' },
  legend: { top: 0 },
  grid: { left: 44, right: 18, top: 32, bottom: 26 },
  xAxis: { type: 'category', data: dates.value, axisLabel: { show: false } },
  yAxis: { type: 'value', scale: true, min: 0, max: 100 },
  series: [
    { name: 'RSI6', type: 'line', symbol: 'none', data: seriesValues('rsi6'), itemStyle: { color: '#3b82f6' } },
    { name: 'RSI12', type: 'line', symbol: 'none', data: seriesValues('rsi12'), itemStyle: { color: '#f59e0b' } },
    { name: 'RSI24', type: 'line', symbol: 'none', data: seriesValues('rsi24'), itemStyle: { color: '#8b5cf6' } },
  ],
}))

function number(value: any, digits = 2) {
  if (value === null || value === undefined || value === '') return '—'
  return Number(value).toFixed(digits)
}

async function load() {
  try {
    const [instrumentRes, quoteRes, barsRes, indicatorRes, tradeRes, holdingRes] = await Promise.all([
      api.instrument(instrumentId),
      api.instrumentQuote(instrumentId),
      api.instrumentBars(instrumentId, { limit: 500 }),
      api.instrumentIndicators(instrumentId, { limit: 500 }),
      api.trades({ instrument: instrumentId, page_size: 200 }),
      api.holdings(),
    ])
    instrument.value = instrumentRes.data
    quote.value = instrumentRes.data.quote || quoteRes.data.quote
    bars.value = barsRes.data || []
    indicatorRows.value = indicatorRes.data.items || []
    indicatorLatest.value = indicatorRes.data.latest
    signals.value = indicatorRes.data.signals || {}
    trades.value = tradeRes.data.results || tradeRes.data
    holding.value = (holdingRes.data.items || []).find((item: any) => item.instrument === instrumentId) || null
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
  await loadIntelligence()
}

async function loadIntelligence() {
  try {
    const response = await api.instrumentReports(instrumentId)
    reportsData.value = response.data
  } catch {
    reportsData.value = { trend: null, items: [], upcoming: null }
  }
  try {
    const response = await api.instrumentSignals(instrumentId)
    signalRows.value = response.data
  } catch {
    signalRows.value = []
  }
  try {
    const response = await api.gridPlan(instrumentId)
    grid.value = response.data
  } catch {
    grid.value = null
  }
}

async function syncReports() {
  syncingReports.value = true
  try {
    await api.syncInstrumentReports(instrumentId)
    ElMessage.success('报告已同步')
    await loadIntelligence()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    syncingReports.value = false
  }
}

async function analyzeSignals() {
  analyzing.value = true
  try {
    const response = await api.analyzeInstrumentSignals(instrumentId)
    signalRows.value = response.data
    ElMessage.success('信号已更新')
    await loadIntelligence()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    analyzing.value = false
  }
}

async function sync() {
  syncing.value = true
  try {
    await api.syncInstrument(instrumentId)
    ElMessage.success('行情已同步')
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    syncing.value = false
  }
}

async function addWatch() {
  try {
    await api.createWatch({ instrument: instrumentId, note: '从标的详情加入' })
    ElMessage.success('已加入自选')
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

onMounted(load)
</script>

<style scoped>
.header-actions {
  display: flex;
  gap: 10px;
}
.two-column {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
}
.two-column > .panel {
  min-width: 0;
}
.signals {
  min-height: 60px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-content: flex-start;
}
.signal-tag {
  margin: 0;
}
.indicator-desc {
  margin-top: 14px;
}
.ml-8 {
  margin-left: 8px;
}
.report-trend {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 12px;
  font-size: 13px;
  color: #374151;
  flex-wrap: wrap;
}
.grid-box {
  margin-top: 12px;
  padding: 12px 14px;
  background: #f8fafc;
  border-radius: 8px;
}
.grid-title {
  font-weight: 700;
  margin-bottom: 8px;
}
.grid-row {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
  margin-bottom: 6px;
  font-size: 13px;
}
.small {
  font-size: 12px;
}
@media (max-width: 1100px) {
  .two-column {
    grid-template-columns: 1fr;
  }
}
</style>
