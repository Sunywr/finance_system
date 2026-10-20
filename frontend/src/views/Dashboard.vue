<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">总览</h2>
        <div class="page-subtitle" v-if="data">
          截至 {{ data.as_of }}，距离下一个发薪日 {{ data.payday }} 还有 {{ data.days_to_payday }} 天
        </div>
      </div>
      <div class="header-actions">
        <el-button :loading="loading" @click="load">刷新</el-button>
        <el-button type="primary" @click="$router.push('/transactions')">记一笔</el-button>
      </div>
    </div>

    <el-alert v-if="data && data.alerts?.length" type="warning" :closable="false" class="alerts">
      <template #title>
        <span v-for="(alert, index) in data.alerts" :key="index" class="alert-item">{{ alert }}</span>
      </template>
    </el-alert>

    <div v-if="data" class="card-grid">
      <StatCard label="当前可动用现金" :value="`¥ ${money(data.cash_now)}`" extra="储蓄卡 + 支付宝 + 微信" />
      <StatCard
        label="发薪日前应还"
        :value="`¥ ${money(data.upcoming_total)}`"
        :extra="`预计发薪 ¥ ${money(data.salary_expected)}`"
        :tone="Number(data.upcoming_total) > Number(data.cash_now) ? 'amount-negative' : ''"
      />
      <StatCard
        label="发薪后预计现金"
        :value="`¥ ${money(data.projected_cash)}`"
        :extra="Number(data.min_cash) < 0 ? `期间最低 ¥ ${money(data.min_cash)}` : '现金流安全'"
        :tone="Number(data.projected_cash) < 0 ? 'amount-negative' : 'amount-positive'"
      />
      <StatCard label="净资产" :value="`¥ ${money(data.net_worth.net_worth)}`" extra="资产 - 负债" />
      <StatCard label="投资市值" :value="`¥ ${money(data.investment.market_value)}`" :extra="`累计收益 ¥ ${money(data.investment.total_pnl)}`" />
      <StatCard
        label="本期消费"
        :value="`¥ ${money(data.current_month.living_expense)}`"
        :extra="`储蓄率 ${percent(data.current_month.savings_rate)}`"
      />
    </div>

    <div v-if="data" class="two-column">
      <div class="panel">
        <div class="panel-header">
          <h3 class="panel-title">发薪日前每日现金余额</h3>
          <span class="muted">工资按发薪日计入</span>
        </div>
        <BaseChart :option="dailyOption" height="300px" />
      </div>
      <div class="panel">
        <div class="panel-header">
          <h3 class="panel-title">近 6 个月 + 未来 3 个月</h3>
          <span class="muted">金额 / 元</span>
        </div>
        <BaseChart :option="monthlyOption" height="300px" />
      </div>
    </div>

    <div v-if="data" class="two-column">
      <div class="panel">
        <div class="panel-header">
          <h3 class="panel-title">发薪日前应还清单</h3>
          <el-button link type="primary" @click="$router.push('/debts')">债务管理</el-button>
        </div>
        <el-table :data="data.upcoming" size="small" max-height="330">
          <el-table-column prop="due_date" label="到期" width="104" />
          <el-table-column prop="title" label="项目" min-width="150" show-overflow-tooltip />
          <el-table-column label="应还" width="110" align="right">
            <template #default="{ row }">¥ {{ money(row.payable) }}</template>
          </el-table-column>
          <el-table-column label="现金支出" width="110" align="right">
            <template #default="{ row }">
              <span :class="Number(row.cash_due) > 0 ? 'amount-negative' : 'muted'">¥ {{ money(row.cash_due) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="96">
            <template #default="{ row }">
              <el-tag v-if="row.overdue" type="danger" size="small">逾期</el-tag>
              <el-tag v-else-if="row.status === 'PROJECTED'" type="info" size="small">预计</el-tag>
              <el-tag v-else type="warning" size="small">待还</el-tag>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!data.upcoming.length" description="发薪日前没有应还项目" :image-size="60" />
      </div>
      <div class="panel">
        <div class="panel-header">
          <h3 class="panel-title">本月支出分类</h3>
          <el-button link type="primary" @click="$router.push('/transactions')">查看流水</el-button>
        </div>
        <BaseChart v-if="data.current_month.category_breakdown?.length" :option="categoryOption" height="300px" />
        <el-empty v-else description="本月暂无消费" :image-size="60" />
      </div>
    </div>

    <div v-if="data" class="panel">
      <div class="panel-header">
        <h3 class="panel-title">资产负债概览</h3>
      </div>
      <el-descriptions :column="3" border size="small">
        <el-descriptions-item label="账户余额">¥ {{ money(data.net_worth.account_total) }}</el-descriptions-item>
        <el-descriptions-item label="投资市值">¥ {{ money(data.net_worth.investment_market_value) }}</el-descriptions-item>
        <el-descriptions-item label="实物资产">¥ {{ money(data.net_worth.physical_assets) }}</el-descriptions-item>
        <el-descriptions-item label="信用卡负债">¥ {{ money(data.net_worth.card_debt) }}</el-descriptions-item>
        <el-descriptions-item label="周期债务">¥ {{ money(data.net_worth.periodic_debt) }}</el-descriptions-item>
        <el-descriptions-item label="房贷剩余">¥ {{ money(data.net_worth.loan_debt) }}</el-descriptions-item>
      </el-descriptions>
    </div>

    <el-skeleton v-if="!data && loading" :rows="8" animated />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import StatCard from '@/components/StatCard.vue'
import BaseChart from '@/components/BaseChart.vue'
import { api } from '@/api'
import { errorMessage, money, percent } from '@/api/client'

const data = ref<any>(null)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const response = await api.dashboard()
    data.value = response.data
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    loading.value = false
  }
}

const dailyOption = computed(() => {
  const series = data.value?.daily_series || []
  return {
    tooltip: { trigger: 'axis', valueFormatter: (value: any) => `¥ ${money(value)}` },
    grid: { left: 58, right: 18, top: 20, bottom: 30 },
    xAxis: { type: 'category', data: series.map((row: any) => row.date.slice(5)), boundaryGap: false },
    yAxis: { type: 'value', axisLabel: { formatter: (value: number) => `${(value / 1000).toFixed(0)}k` } },
    series: [
      {
        name: '现金余额',
        type: 'line',
        smooth: true,
        symbol: 'none',
        data: series.map((row: any) => Number(row.balance)),
        areaStyle: { opacity: 0.12 },
        lineStyle: { width: 2.5, color: '#2563eb' },
        itemStyle: { color: '#2563eb' },
      },
      {
        name: '当日支出',
        type: 'bar',
        data: series.map((row: any) => Number(row.outflow)),
        barMaxWidth: 12,
        itemStyle: { color: '#f59e0b' },
      },
    ],
    legend: { top: 0, right: 0 },
  }
})

const monthlyOption = computed(() => {
  const series = data.value?.monthly_series || []
  return {
    tooltip: { trigger: 'axis', valueFormatter: (value: any) => `¥ ${money(value)}` },
    legend: { top: 0, right: 0 },
    grid: { left: 58, right: 18, top: 34, bottom: 30 },
    xAxis: { type: 'category', data: series.map((row: any) => row.month) },
    yAxis: { type: 'value', axisLabel: { formatter: (value: number) => `${(value / 1000).toFixed(0)}k` } },
    series: [
      { name: '收入', type: 'line', smooth: true, data: series.map((row: any) => Number(row.income)), itemStyle: { color: '#16a34a' } },
      { name: '消费支出', type: 'line', smooth: true, data: series.map((row: any) => Number(row.expense)), itemStyle: { color: '#dc2626' } },
      { name: '信用卡还款', type: 'line', smooth: true, data: series.map((row: any) => Number(row.card_repayment)), itemStyle: { color: '#7c3aed' } },
      { name: '周期债务现金', type: 'line', smooth: true, data: series.map((row: any) => Number(row.periodic_cash)), itemStyle: { color: '#f59e0b' } },
      { name: '期末现金', type: 'line', smooth: true, data: series.map((row: any) => Number(row.ending_cash)), lineStyle: { width: 2.5 }, itemStyle: { color: '#0ea5e9' } },
    ],
  }
})

const categoryOption = computed(() => {
  const rows = data.value?.current_month.category_breakdown || []
  return {
    tooltip: { trigger: 'item', formatter: (params: any) => `${params.name}<br/>¥ ${money(params.value)} (${params.percent}%)` },
    legend: { orient: 'vertical', right: 0, top: 'middle', type: 'scroll' },
    series: [
      {
        type: 'pie',
        radius: ['46%', '72%'],
        center: ['38%', '50%'],
        data: rows.map((row: any) => ({ name: row.name, value: Number(row.amount) })),
        label: { show: false },
        emphasis: { label: { show: true, fontWeight: 'bold' } },
      },
    ],
  }
})

onMounted(load)
</script>

<style scoped>
.header-actions {
  display: flex;
  gap: 10px;
}
.alerts {
  margin-bottom: 16px;
}
.alert-item {
  display: inline-block;
  margin-right: 18px;
}
.two-column {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr);
  gap: 18px;
}
.two-column > .panel {
  min-width: 0;
}
@media (max-width: 1200px) {
  .two-column {
    grid-template-columns: 1fr;
  }
}
</style>
