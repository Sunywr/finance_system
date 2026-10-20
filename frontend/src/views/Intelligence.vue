<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">投资智能</h2>
        <div class="page-subtitle">市场风向、全市场筛选、B/S 信号、打新日历与网格降成本</div>
      </div>
      <div class="header-actions">
        <el-button :loading="refreshing" @click="refreshRegime">刷新市场风向</el-button>
        <el-button @click="$router.push('/investments')">投资持仓</el-button>
      </div>
    </div>

    <div class="card-grid">
      <StatCard
        label="市场风向"
        :value="regime?.regime_label || '未计算'"
        :extra="regime ? `综合评分 ${Number(regime.score).toFixed(1)}` : '点击刷新获取'"
        :tone="regime?.regime === 'BULL' ? 'amount-positive' : regime?.regime === 'BEAR' ? 'amount-negative' : ''"
      />
      <StatCard label="沪深300" :value="money(regime?.index_close)" :extra="`MA20 ${money(regime?.ma20)} / MA60 ${money(regime?.ma60)}`" />
      <StatCard
        label="市场宽度"
        :value="regime ? percent(regime.breadth_ratio) : '—'"
        :extra="regime ? `上涨 ${regime.advance_count} / 下跌 ${regime.decline_count}` : ''"
      />
      <StatCard label="今日信号" :value="String(signalRows.length)" extra="B/S、网格、股息" />
      <StatCard label="打新日历" :value="String(ipoRows.length)" :extra="`可用市值 ${money(stockMarketValue)}`" />
    </div>

    <div class="two-column">
      <div class="panel">
        <div class="panel-header">
          <h3 class="panel-title">市场风向与行业动量</h3>
          <span v-if="regime" class="muted">{{ regime.trade_date }}</span>
        </div>
        <template v-if="regime">
          <p class="explanation">{{ regime.explanation }}</p>
          <div class="sector-list">
            <div v-for="sector in regime.sectors" :key="sector.name" class="sector-row">
              <span class="sector-name">{{ sector.name }}</span>
              <el-progress
                :percentage="Math.min(100, Math.abs(Number(sector.avg_change)) * 12)"
                :color="Number(sector.avg_change) >= 0 ? '#ef4444' : '#10b981'"
                :show-text="false"
              />
              <span :class="Number(sector.avg_change) >= 0 ? 'amount-positive' : 'amount-negative'" class="sector-value">
                {{ Number(sector.avg_change).toFixed(2) }}%
              </span>
            </div>
          </div>
          <div class="muted small">行业动量为前 10 与后 3 名，按平均涨跌幅计算。</div>
        </template>
        <el-empty v-else description="尚未计算，点击右上角刷新" :image-size="60" />
      </div>

      <div class="panel">
        <div class="panel-header">
          <h3 class="panel-title">智能筛选</h3>
          <div class="screener-actions">
            <el-select v-model="selectedPreset" placeholder="筛选器" style="width: 150px">
              <el-option v-for="item in presets" :key="item.id" :label="item.name" :value="item.id" />
            </el-select>
            <el-button type="primary" :loading="screening" @click="runScreener">运行筛选</el-button>
          </div>
        </div>
        <el-alert v-if="currentRun?.status === 'FAILED'" type="error" :closable="false" :title="currentRun.error" class="run-alert" />
        <template v-if="currentRun">
          <div class="run-meta">
            <el-tag size="small" :type="currentRun.status === 'SUCCESS' ? 'success' : 'danger'">{{ currentRun.status_label }}</el-tag>
            <span class="muted">股票池 {{ currentRun.universe_size }}，结果 {{ currentRun.result_count }}</span>
          </div>
          <el-table :data="currentRun.results" size="small" max-height="330">
            <el-table-column prop="symbol" label="代码" width="90" />
            <el-table-column prop="name" label="名称" min-width="100" />
            <el-table-column prop="industry" label="行业" width="110" show-overflow-tooltip />
            <el-table-column label="价格" width="90" align="right">
              <template #default="{ row }">{{ money(row.price) }}</template>
            </el-table-column>
            <el-table-column label="PE/PB" width="100" align="right">
              <template #default="{ row }">{{ Number(row.pe || 0).toFixed(1) }} / {{ Number(row.pb || 0).toFixed(2) }}</template>
            </el-table-column>
            <el-table-column label="评分" width="80" align="right">
              <template #default="{ row }">{{ Number(row.score).toFixed(1) }}</template>
            </el-table-column>
            <el-table-column label="理由" min-width="180">
              <template #default="{ row }">
                <span class="reason">{{ (row.reasons || []).join(' · ') }}</span>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!currentRun.results?.length" description="没有满足条件的标的；可调整预设或补充股息率数据" :image-size="50" />
        </template>
        <el-empty v-else description="选择筛选器并运行；首次约需 10-20 秒" :image-size="60" />
      </div>
    </div>

    <div class="two-column">
      <div class="panel">
        <div class="panel-header">
          <h3 class="panel-title">打新日历</h3>
          <el-button size="small" :loading="syncingIpo" @click="syncIpo">同步日历</el-button>
        </div>
        <el-table :data="ipoRows" size="small" max-height="360">
          <el-table-column prop="apply_date" label="申购日" width="105" />
          <el-table-column prop="name" label="名称" min-width="110" />
          <el-table-column prop="code" label="代码" width="85" />
          <el-table-column prop="market" label="市场" width="90" />
          <el-table-column label="发行价" width="90" align="right">
            <template #default="{ row }">{{ money(row.issue_price) }}</template>
          </el-table-column>
          <el-table-column label="所需市值" width="110" align="right">
            <template #default="{ row }">{{ money(row.requirement_market_value) }}</template>
          </el-table-column>
          <el-table-column label="资格" width="80">
            <template #default="{ row }">
              <el-tag v-if="row.eligible === true" size="small" type="success">可申购</el-tag>
              <el-tag v-else-if="row.eligible === false" size="small" type="info">市值不足</el-tag>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!ipoRows.length" description="暂无数据，点击同步" :image-size="50" />
      </div>

      <div class="panel">
        <div class="panel-header">
          <h3 class="panel-title">策略信号</h3>
          <el-button size="small" @click="loadSignals">刷新</el-button>
        </div>
        <el-table :data="signalRows" size="small" max-height="360">
          <el-table-column label="标的" min-width="130">
            <template #default="{ row }">{{ row.instrument_symbol }} {{ row.instrument_name }}</template>
          </el-table-column>
          <el-table-column prop="signal_type_label" label="信号" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="row.signal_type === 'BUY_POINT' ? 'success' : row.signal_type === 'SELL_POINT' ? 'danger' : 'warning'">
                {{ row.signal_type_label }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="区间" width="150" align="right">
            <template #default="{ row }">{{ money(row.price_low) }} ~ {{ money(row.price_high) }}</template>
          </el-table-column>
          <el-table-column prop="confidence" label="置信" width="70" align="right" />
          <el-table-column label="依据" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">{{ (row.reasons || []).join('；') }}</template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!signalRows.length" description="在标的详情页点击「分析信号」生成" :image-size="50" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import StatCard from '@/components/StatCard.vue'
import { api, unwrap } from '@/api'
import { errorMessage, money, percent } from '@/api/client'

const regime = ref<any>(null)
const presets = ref<any[]>([])
const selectedPreset = ref<number | null>(null)
const currentRun = ref<any>(null)
const ipoRows = ref<any[]>([])
const signalRows = ref<any[]>([])
const refreshing = ref(false)
const screening = ref(false)
const syncingIpo = ref(false)

const stockMarketValue = computed(() => {
  const row = ipoRows.value[0]
  return row ? row.stock_market_value : 0
})

async function loadRegime() {
  try {
    const response = await api.marketRegime()
    regime.value = response.data
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function refreshRegime() {
  refreshing.value = true
  try {
    const response = await api.refreshMarketRegime()
    regime.value = response.data
    ElMessage.success('市场风向已更新')
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    refreshing.value = false
  }
}

async function loadPresets() {
  try {
    const response = await api.screenerPresets()
    presets.value = unwrap(response)
    if (presets.value.length && !selectedPreset.value) {
      selectedPreset.value = presets.value.find((item: any) => item.is_default)?.id || presets.value[0].id
    }
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function runScreener() {
  if (!selectedPreset.value) {
    ElMessage.warning('请选择筛选器')
    return
  }
  screening.value = true
  try {
    const response = await api.runScreener({ preset: selectedPreset.value })
    currentRun.value = response.data
    if (response.data.status === 'FAILED') ElMessage.error(response.data.error || '筛选失败')
    else ElMessage.success(`筛选完成，命中 ${response.data.result_count} 个标的`)
    await loadSignals()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    screening.value = false
  }
}

async function loadIpo() {
  try {
    const response = await api.ipo()
    ipoRows.value = response.data
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function syncIpo() {
  syncingIpo.value = true
  try {
    await api.syncIpo()
    ElMessage.success('打新日历已同步')
    await loadIpo()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    syncingIpo.value = false
  }
}

async function loadSignals() {
  try {
    const response = await api.signals({ page_size: 50 })
    signalRows.value = unwrap(response)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

onMounted(async () => {
  await Promise.all([loadRegime(), loadPresets(), loadIpo(), loadSignals()])
})
</script>

<style scoped>
.header-actions,
.screener-actions {
  display: flex;
  gap: 10px;
  align-items: center;
}
.two-column {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
}
.explanation {
  color: #374151;
  line-height: 1.7;
  margin: 0 0 14px;
  font-size: 13px;
}
.sector-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.sector-row {
  display: grid;
  grid-template-columns: 100px 1fr 76px;
  gap: 12px;
  align-items: center;
  font-size: 13px;
}
.sector-name {
  color: #374151;
}
.sector-value {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.run-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.reason {
  font-size: 12px;
  color: #4b5563;
}
.small {
  font-size: 12px;
}
.run-alert {
  margin-bottom: 10px;
}
@media (max-width: 1100px) {
  .two-column {
    grid-template-columns: 1fr;
  }
}
</style>
