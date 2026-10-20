<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">投资管理</h2>
        <div class="page-subtitle">股票/ETF/基金/理财持仓、成本收益、行情与技术指标</div>
      </div>
      <div class="header-actions">
        <el-button :loading="syncing" @click="syncAll">同步行情</el-button>
        <el-button @click="openInstrumentCreate">新增标的</el-button>
        <el-button type="primary" @click="openTrade()">记录交易</el-button>
      </div>
    </div>

    <div class="card-grid">
      <StatCard label="持仓市值" :value="`¥ ${money(totals.market_value)}`" :extra="`${totals.count || 0} 个持仓`" />
      <StatCard label="持仓成本" :value="`¥ ${money(totals.cost)}`" :extra="`累计买入 ¥${money(totals.invested)}`" />
      <StatCard label="累计收益" :value="`¥ ${money(totals.total_pnl)}`" :extra="`已实现 ¥${money(totals.realized_pnl)} / 分红 ¥${money(totals.dividends)}`" :tone="Number(totals.total_pnl) >= 0 ? 'amount-positive' : 'amount-negative'" />
      <StatCard label="总收益率" :value="percent(totals.return_rate)" extra="累计收益 / 累计买入" :tone="Number(totals.return_rate) >= 0 ? 'amount-positive' : 'amount-negative'" />
    </div>

    <div class="panel">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="持仓" name="holdings">
          <el-table :data="holdings" v-loading="loading" size="small" stripe>
            <el-table-column label="标的" min-width="170">
              <template #default="{ row }">
                <div class="symbol">{{ row.symbol }} <span class="muted">{{ row.name }}</span></div>
                <div class="muted small">{{ row.account_name }} · {{ row.valuation_mode === 'ACCRUAL' ? '收益累计' : '行情估值' }}</div>
              </template>
            </el-table-column>
            <el-table-column label="持仓" width="120" align="right">
              <template #default="{ row }">{{ Number(row.quantity).toFixed(2) }}</template>
            </el-table-column>
            <el-table-column label="成本价" width="100" align="right">
              <template #default="{ row }">{{ Number(row.avg_cost).toFixed(4) }}</template>
            </el-table-column>
            <el-table-column label="成本" width="120" align="right">
              <template #default="{ row }">¥ {{ money(row.cost) }}</template>
            </el-table-column>
            <el-table-column label="现价" width="100" align="right">
              <template #default="{ row }">{{ Number(row.last_price).toFixed(4) }}</template>
            </el-table-column>
            <el-table-column label="市值" width="120" align="right">
              <template #default="{ row }">¥ {{ money(row.market_value) }}</template>
            </el-table-column>
            <el-table-column label="浮动盈亏" width="120" align="right">
              <template #default="{ row }">
                <span :class="Number(row.unrealized_pnl) >= 0 ? 'amount-positive' : 'amount-negative'">¥ {{ money(row.unrealized_pnl) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="收益率" width="100" align="right">
              <template #default="{ row }">{{ percent(row.return_rate) }}</template>
            </el-table-column>
            <el-table-column label="上次交易至今" width="140" align="right">
              <template #default="{ row }">
                <div>{{ percent(row.since_last_trade_return) }}</div>
                <div class="muted small">{{ row.days_since_last_trade ?? '—' }} 天</div>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="150" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="$router.push(`/investments/${row.instrument}`)">K线</el-button>
                <el-button link type="primary" @click="openTrade(row.instrument, row.account)">交易</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!holdings.length" description="暂无持仓" :image-size="60" />
        </el-tab-pane>

        <el-tab-pane label="标的" name="instruments">
          <div class="filters">
            <el-input v-model="instrumentSearch" clearable placeholder="代码/名称/行业" style="width: 220px" @keyup.enter="loadInstruments" />
            <el-button @click="loadInstruments">查询</el-button>
          </div>
          <el-table :data="instruments" v-loading="loading" size="small" stripe>
            <el-table-column prop="symbol" label="代码" width="100" />
            <el-table-column prop="name" label="名称" min-width="130" />
            <el-table-column prop="type_label" label="类型" width="100" />
            <el-table-column prop="exchange_label" label="市场" width="90" />
            <el-table-column prop="industry" label="行业" width="110" />
            <el-table-column label="股息率" width="90" align="right">
              <template #default="{ row }">{{ row.dividend_yield === null ? '—' : `${Number(row.dividend_yield).toFixed(2)}%` }}</template>
            </el-table-column>
            <el-table-column label="最新价" width="110" align="right">
              <template #default="{ row }">{{ money(row.latest_price) }}</template>
            </el-table-column>
            <el-table-column label="涨跌幅" width="100" align="right">
              <template #default="{ row }">
                <span v-if="row.quote" :class="Number(row.quote.change_pct) >= 0 ? 'amount-positive' : 'amount-negative'">
                  {{ percent(row.quote.change_pct) }}
                </span>
                <span v-else class="muted">—</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag v-if="row.quote?.is_stale" size="small" type="warning">缓存</el-tag>
                <el-tag v-else-if="row.quote" size="small" type="success">实时</el-tag>
                <span v-else class="muted">无行情</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="210" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="$router.push(`/investments/${row.id}`)">详情</el-button>
                <el-button link type="primary" @click="syncInstrument(row)">同步</el-button>
                <el-button link type="primary" @click="addWatch(row)">自选</el-button>
                <el-button link type="primary" @click="openTrade(row.id)">交易</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="自选" name="watchlist">
          <el-table :data="watchlist" v-loading="loading" size="small">
            <el-table-column label="标的" min-width="180">
              <template #default="{ row }">{{ row.instrument_symbol }} {{ row.instrument_name }}</template>
            </el-table-column>
            <el-table-column label="最新价" width="110" align="right">
              <template #default="{ row }">{{ money(row.latest_price) }}</template>
            </el-table-column>
            <el-table-column label="目标买入" width="110" align="right">
              <template #default="{ row }">{{ money(row.target_buy_price) }}</template>
            </el-table-column>
            <el-table-column label="目标卖出" width="110" align="right">
              <template #default="{ row }">{{ money(row.target_sell_price) }}</template>
            </el-table-column>
            <el-table-column prop="note" label="备注" min-width="160" />
            <el-table-column label="操作" width="100" fixed="right">
              <template #default="{ row }">
                <el-button link type="danger" @click="removeWatch(row)">移除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!watchlist.length" description="暂无自选" :image-size="60" />
        </el-tab-pane>
      </el-tabs>
    </div>

    <el-alert
      title="投资智能"
      description="市场风向、全市场筛选、B/S 点、打新日历与网格降成本已上线，请进入「投资智能」页面使用；季报/年报可在标的详情查看。"
      type="info"
      :closable="false"
      class="roadmap"
    />

    <el-dialog v-model="tradeDialog" title="记录投资交易" width="600px" destroy-on-close>
      <el-form :model="tradeForm" label-width="100px">
        <el-form-item label="账户">
          <el-select v-model="tradeForm.account" style="width: 100%">
            <el-option v-for="item in investAccounts" :key="item.id" :label="`${item.name}（¥${money(item.current_balance)}）`" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="标的">
          <el-select v-model="tradeForm.instrument" filterable style="width: 100%">
            <el-option v-for="item in instruments" :key="item.id" :label="`${item.symbol} ${item.name}`" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="方向">
          <el-radio-group v-model="tradeForm.side">
            <el-radio-button value="BUY">买入</el-radio-button>
            <el-radio-button value="SELL">卖出</el-radio-button>
            <el-radio-button value="DIVIDEND">分红</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="tradeForm.side !== 'DIVIDEND'" label="操作">
          <el-select v-model="tradeForm.operation" style="width: 100%">
            <el-option label="建仓" value="OPEN" />
            <el-option label="加仓" value="ADD" />
            <el-option v-if="tradeForm.side === 'SELL'" label="减仓" value="REDUCE" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="tradeForm.side !== 'DIVIDEND'" label="数量">
          <el-input-number v-model="tradeForm.quantity" :min="0" :precision="6" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item v-if="tradeForm.side !== 'DIVIDEND'" label="价格">
          <el-input-number v-model="tradeForm.price" :min="0" :precision="4" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item v-else label="分红金额">
          <el-input-number v-model="tradeForm.amount" :min="0" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="费用">
          <el-input-number v-model="tradeForm.fee" :min="0" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="交易时间">
          <el-date-picker v-model="tradeForm.trade_date" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="tradeForm.note" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="tradeDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitTrade">保存交易</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="instrumentDialog" title="新增标的" width="560px" destroy-on-close>
      <el-form :model="instrumentForm" label-width="100px">
        <el-form-item label="代码">
          <el-input v-model="instrumentForm.symbol" placeholder="如 600519、510300、WY001" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="instrumentForm.name" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="instrumentForm.type" style="width: 100%" @change="onInstrumentType">
            <el-option label="股票" value="STOCK" />
            <el-option label="场内基金" value="ETF" />
            <el-option label="场外基金" value="OTC_FUND" />
            <el-option label="理财" value="WEALTH" />
          </el-select>
        </el-form-item>
        <el-form-item label="市场">
          <el-select v-model="instrumentForm.exchange" style="width: 100%">
            <el-option label="上交所" value="SH" />
            <el-option label="深交所" value="SZ" />
            <el-option label="北交所" value="BJ" />
            <el-option label="场外" value="OTC" />
          </el-select>
        </el-form-item>
        <el-form-item label="行业">
          <el-input v-model="instrumentForm.industry" />
        </el-form-item>
        <el-form-item label="估值方式">
          <el-radio-group v-model="instrumentForm.valuation_mode">
            <el-radio-button value="MARKET">行情估值</el-radio-button>
            <el-radio-button value="ACCRUAL">收益累计</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="instrumentForm.valuation_mode === 'ACCRUAL'" label="年化(%)">
          <el-input-number v-model="instrumentForm.annual_rate" :min="0" :precision="4" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="股息率(%)">
          <el-input-number v-model="instrumentForm.dividend_yield" :min="0" :precision="4" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="instrumentForm.note" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="instrumentDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveInstrument">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="watchDialog" title="加入自选" width="460px">
      <el-form label-width="100px">
        <el-form-item label="标的">
          <span>{{ watchInstrument?.symbol }} {{ watchInstrument?.name }}</span>
        </el-form-item>
        <el-form-item label="目标买入">
          <el-input-number v-model="watchForm.target_buy_price" :min="0" :precision="4" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="目标卖出">
          <el-input-number v-model="watchForm.target_sell_price" :min="0" :precision="4" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="watchForm.note" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="watchDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveWatch">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import StatCard from '@/components/StatCard.vue'
import { api, unwrap } from '@/api'
import { errorMessage, money, percent } from '@/api/client'

const activeTab = ref('holdings')
const holdings = ref<any[]>([])
const totals = ref<any>({})
const instruments = ref<any[]>([])
const watchlist = ref<any[]>([])
const accounts = ref<any[]>([])
const loading = ref(false)
const saving = ref(false)
const syncing = ref(false)
const instrumentSearch = ref('')

const tradeDialog = ref(false)
const instrumentDialog = ref(false)
const watchDialog = ref(false)
const watchInstrument = ref<any>(null)

const tradeForm = reactive<any>({
  account: null,
  instrument: null,
  side: 'BUY',
  operation: 'OPEN',
  quantity: undefined,
  price: undefined,
  fee: 0,
  amount: undefined,
  trade_date: new Date().toISOString().slice(0, 19),
  note: '',
})

const instrumentForm = reactive<any>({
  symbol: '',
  name: '',
  type: 'STOCK',
  exchange: 'SH',
  industry: '',
  valuation_mode: 'MARKET',
  annual_rate: 0,
  dividend_yield: null,
  note: '',
})

const watchForm = reactive<any>({ target_buy_price: null, target_sell_price: null, note: '' })

const investAccounts = computed(() =>
  accounts.value.filter((item: any) => ['STOCK', 'WEALTH', 'ALIPAY', 'WECHAT'].includes(item.type) && item.is_active),
)

async function loadHoldings() {
  const response = await api.holdings()
  holdings.value = response.data.items || []
  totals.value = response.data.totals || {}
}

async function loadInstruments() {
  const response = await api.instruments({ page_size: 200, search: instrumentSearch.value || undefined })
  instruments.value = unwrap(response)
}

async function loadWatchlist() {
  const response = await api.watchlist()
  watchlist.value = unwrap(response)
}

async function loadAccounts() {
  const response = await api.accounts({ page_size: 200 })
  accounts.value = unwrap(response)
}

async function loadAll() {
  loading.value = true
  try {
    await Promise.all([loadHoldings(), loadInstruments(), loadWatchlist(), loadAccounts()])
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    loading.value = false
  }
}

function openTrade(instrumentId?: number, accountId?: number) {
  Object.assign(tradeForm, {
    account: accountId || investAccounts.value[0]?.id || null,
    instrument: instrumentId || instruments.value[0]?.id || null,
    side: 'BUY',
    operation: 'OPEN',
    quantity: undefined,
    price: undefined,
    fee: 0,
    amount: undefined,
    trade_date: new Date().toISOString().slice(0, 19),
    note: '',
  })
  tradeDialog.value = true
}

async function submitTrade() {
  if (!tradeForm.account || !tradeForm.instrument) {
    ElMessage.warning('请选择账户和标的')
    return
  }
  saving.value = true
  try {
    const payload: any = {
      account: tradeForm.account,
      instrument: tradeForm.instrument,
      side: tradeForm.side,
      operation: tradeForm.side === 'DIVIDEND' ? 'DIVIDEND' : tradeForm.operation,
      quantity: tradeForm.side === 'DIVIDEND' ? 0 : tradeForm.quantity,
      price: tradeForm.side === 'DIVIDEND' ? 0 : tradeForm.price,
      fee: tradeForm.fee,
      trade_date: tradeForm.trade_date,
      note: tradeForm.note,
    }
    if (tradeForm.side === 'DIVIDEND') payload.amount = tradeForm.amount
    await api.createTrade(payload)
    ElMessage.success('交易已记录')
    tradeDialog.value = false
    await loadAll()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

function openInstrumentCreate() {
  Object.assign(instrumentForm, {
    symbol: '',
    name: '',
    type: 'STOCK',
    exchange: 'SH',
    industry: '',
    valuation_mode: 'MARKET',
    annual_rate: 0,
    dividend_yield: null,
    note: '',
  })
  instrumentDialog.value = true
}

function onInstrumentType() {
  if (instrumentForm.type === 'WEALTH') {
    instrumentForm.valuation_mode = 'ACCRUAL'
    instrumentForm.exchange = 'OTC'
  } else if (instrumentForm.type === 'OTC_FUND') {
    instrumentForm.exchange = 'OTC'
  }
}

async function saveInstrument() {
  saving.value = true
  try {
    await api.createInstrument(instrumentForm)
    ElMessage.success('标的已创建')
    instrumentDialog.value = false
    await loadInstruments()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

async function syncInstrument(row: any) {
  syncing.value = true
  try {
    const response = await api.syncInstrument(row.id)
    ElMessage.success(`同步完成：${JSON.stringify(response.data)}`)
    await loadInstruments()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    syncing.value = false
  }
}

async function syncAll() {
  syncing.value = true
  try {
    const response = await api.syncMarket()
    ElMessage.success(`同步完成：${JSON.stringify(response.data)}`)
    await loadAll()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    syncing.value = false
  }
}

function addWatch(row: any) {
  watchInstrument.value = row
  watchForm.target_buy_price = null
  watchForm.target_sell_price = null
  watchForm.note = ''
  watchDialog.value = true
}

async function saveWatch() {
  saving.value = true
  try {
    await api.createWatch({ instrument: watchInstrument.value.id, ...watchForm })
    ElMessage.success('已加入自选')
    watchDialog.value = false
    await loadWatchlist()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

async function removeWatch(row: any) {
  try {
    await api.deleteWatch(row.id)
    ElMessage.success('已移除')
    await loadWatchlist()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

onMounted(loadAll)
</script>

<style scoped>
.header-actions {
  display: flex;
  gap: 10px;
}
.filters {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
}
.symbol {
  font-weight: 600;
}
.small {
  font-size: 12px;
}
.roadmap {
  margin-top: 4px;
}
</style>
