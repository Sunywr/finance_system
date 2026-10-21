<template>
  <div class="history-page">
    <h2>家庭与历史资料</h2>
    <el-alert title="可查看已导入的家庭与历史资料；完整替换状态以验收报告为准。" type="info" :closable="false" />
    <el-card class="section" v-loading="loading">
      <template #header>家庭总览</template>
      <el-table :data="summary.members || []">
        <el-table-column prop="name" label="成员" />
        <el-table-column prop="cash_balance" label="现金余额" />
        <el-table-column prop="pending_debt" label="待还债务" />
        <el-table-column prop="portfolio.market_value" label="持仓市值" />
        <el-table-column prop="portfolio.total_pnl" label="持仓收益" />
      </el-table>
    </el-card>
    <el-card class="section">
      <template #header>历史资料查询</template>
      <el-form inline @submit.prevent="search">
        <el-form-item label="资料类型"><el-select v-model="table" filterable style="width: 300px"><el-option v-for="t in types" :key="t" :label="labels[t] || t" :value="t" /></el-select></el-form-item>
        <el-form-item label="证券代码"><el-input v-model="code" maxlength="32" clearable /></el-form-item>
        <el-form-item label="日期"><el-date-picker v-model="dates" type="daterange" value-format="YYYY-MM-DD" /></el-form-item>
        <el-button native-type="submit" type="primary" :loading="querying">查询</el-button>
      </el-form>
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <el-table :data="records" v-loading="querying">
        <el-table-column prop="source_pk" label="原记录编号" width="160" />
        <el-table-column prop="business_date" label="日期" width="120" />
        <el-table-column prop="code" label="证券代码" width="110" />
        <el-table-column label="资料"><template #default="{ row }"><el-button link @click="selected = row">查看内容</el-button></template></el-table-column>
      </el-table>
      <el-empty v-if="searched && !records.length && !querying" description="本页暂无匹配记录；如有下一页可继续查找" />
      <el-button v-if="nextCursor" class="section" @click="loadPage(nextCursor)" :loading="querying">下一页</el-button>
    </el-card>
    <el-dialog :model-value="!!selected" title="历史资料" width="min(900px, 95vw)" @close="selected = null"><pre>{{ selected ? JSON.stringify(selected.payload, null, 2) : '' }}</pre></el-dialog>
  </div>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { client } from '@/api/client'
const loading = ref(false), querying = ref(false), searched = ref(false), error = ref('')
const summary = ref<any>({}), types = ref<string[]>([]), table = ref('account_account'), code = ref(''), dates = ref<string[]>([])
const records = ref<any[]>([]), nextCursor = ref<string | null>(null), selected = ref<any>(null)
const labels = ref<Record<string, string>>({ account_account: '历史流水', account_budget: '预算', account_presale: '预售订单', account_autoinvestplan: '定投计划', account_balancefix: '余额校正', stock_cost_basis_anchor: '持仓成本核实', account_invest: '原投资记录', mortgage_repayment_plan: '房贷还款计划', sim_trade: '模拟交易', stock_holding_plan: '持仓计划' })
async function loadPage(cursor?: string) {
  querying.value = true; error.value = ''; searched.value = true
  try {
    const { data } = await client.get('/history/records', { params: { table: table.value, code: code.value || undefined, start_date: dates.value?.[0], end_date: dates.value?.[1], cursor, page_size: 50 } })
    records.value = data.results; nextCursor.value = data.next_cursor
  } catch (e: any) { error.value = e.response?.data?.detail || '资料读取失败，请重试'; nextCursor.value = null }
  finally { querying.value = false }
}
function search() { return loadPage() }
onMounted(async () => { loading.value = true; try { const [a, b] = await Promise.all([client.get('/household/summary'), client.get('/history/types')]); summary.value = a.data; types.value = b.data.tables; labels.value = { ...b.data.labels, ...labels.value } } catch { error.value = '家庭资料加载失败' } finally { loading.value = false } })
</script>
<style scoped>.section { margin-top: 18px; } pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 65vh; overflow: auto; }</style>
