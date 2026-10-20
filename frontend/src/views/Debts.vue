<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">债务管理</h2>
        <div class="page-subtitle">信用卡债务、周期债务与房贷债务的统一视图</div>
      </div>
      <div class="header-actions">
        <el-button :loading="loading" @click="generate">生成债务项</el-button>
        <el-button type="primary" @click="openRecurringCreate">新增周期债务</el-button>
      </div>
    </div>

    <div class="card-grid">
      <StatCard label="未还总额" :value="`¥ ${money(summary.unpaid_total)}`" :extra="`${summary.unpaid_count || 0} 笔待处理`" />
      <StatCard label="逾期笔数" :value="String(summary.overdue_count || 0)" extra="请优先处理" :tone="summary.overdue_count ? 'amount-negative' : ''" />
      <StatCard label="信用卡债务" :value="`¥ ${money(summary.by_kind?.CREDIT_CARD)}`" extra="已出账账单" />
      <StatCard label="周期债务" :value="`¥ ${money(summary.by_kind?.PERIODIC)}`" extra="保险/房租等" />
      <StatCard label="房贷债务" :value="`¥ ${money(summary.by_kind?.MORTGAGE)}`" extra="未来 12 个月" />
    </div>

    <div class="panel">
      <div class="panel-header">
        <el-tabs v-model="activeTab" class="tabs">
          <el-tab-pane label="债务项" name="items" />
          <el-tab-pane label="周期债务模板" name="templates" />
        </el-tabs>
      </div>

      <template v-if="activeTab === 'items'">
        <div class="filters">
          <el-select v-model="filters.kind" clearable placeholder="类型" style="width: 140px">
            <el-option label="信用卡" value="CREDIT_CARD" />
            <el-option label="周期债务" value="PERIODIC" />
            <el-option label="房贷" value="MORTGAGE" />
          </el-select>
          <el-select v-model="filters.status" clearable placeholder="状态" style="width: 140px">
            <el-option label="待还" value="PENDING" />
            <el-option label="部分还款" value="PARTIAL" />
            <el-option label="逾期" value="OVERDUE" />
            <el-option label="已结清" value="PAID" />
            <el-option label="已取消" value="CANCELLED" />
          </el-select>
          <el-date-picker v-model="filters.month" type="month" value-format="YYYY-MM" placeholder="月份" style="width: 140px" />
          <el-button @click="load">查询</el-button>
        </div>
        <el-table :data="items" v-loading="loading" size="small" stripe>
          <el-table-column type="expand">
            <template #default="{ row }">
              <div class="expand">
                <div><strong>备注：</strong>{{ row.note || '—' }}</div>
                <div v-if="row.payments?.length">
                  <strong>还款记录：</strong>
                  <el-tag v-for="payment in row.payments" :key="payment.id" size="small" class="payment-tag">
                    {{ payment.paid_at }} / {{ payment.channel_label }} / ¥{{ money(payment.amount) }}
                    <span v-if="Number(payment.discount_amount)">（减免 ¥{{ money(payment.discount_amount) }}）</span>
                  </el-tag>
                </div>
                <div v-else class="muted">暂无还款记录</div>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="due_date" label="到期日" width="110" />
          <el-table-column prop="title" label="项目" min-width="180" show-overflow-tooltip />
          <el-table-column label="类型" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="row.kind === 'CREDIT_CARD' ? 'warning' : row.kind === 'MORTGAGE' ? 'info' : ''">
                {{ row.kind_label }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="应还" width="110" align="right">
            <template #default="{ row }">¥ {{ money(row.amount) }}</template>
          </el-table-column>
          <el-table-column label="减免" width="100" align="right">
            <template #default="{ row }">¥ {{ money(row.discount_amount) }}</template>
          </el-table-column>
          <el-table-column label="已还" width="100" align="right">
            <template #default="{ row }">¥ {{ money(row.paid_amount) }}</template>
          </el-table-column>
          <el-table-column label="剩余" width="110" align="right">
            <template #default="{ row }"><strong>¥ {{ money(row.payable_amount) }}</strong></template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="statusType(row.status)">{{ row.status_label }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="140" fixed="right">
            <template #default="{ row }">
              <el-button v-if="!['PAID', 'CANCELLED'].includes(row.status)" link type="primary" @click="openPay(row)">还款</el-button>
              <el-button v-if="!['PAID', 'CANCELLED'].includes(row.status) && row.kind !== 'CREDIT_CARD'" link type="danger" @click="cancelItem(row)">取消</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="pagination">
          <el-pagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            :total="total"
            :page-sizes="[20, 50, 100]"
            layout="total, sizes, prev, pager, next"
            @size-change="load"
            @current-change="load"
          />
        </div>
      </template>

      <template v-else>
        <el-table :data="recurring" v-loading="loading" size="small" stripe>
          <el-table-column prop="name" label="名称" min-width="160" />
          <el-table-column label="类型" width="100">
            <template #default="{ row }">{{ row.debt_type_label }}</template>
          </el-table-column>
          <el-table-column label="每期" width="110" align="right">
            <template #default="{ row }">¥ {{ money(row.amount) }}</template>
          </el-table-column>
          <el-table-column prop="periods" label="期数" width="70" />
          <el-table-column prop="interval_months" label="间隔月" width="80" />
          <el-table-column prop="first_due_date" label="首次到期" width="110" />
          <el-table-column prop="payment_channel" label="支付渠道" width="110" />
          <el-table-column label="进度" width="120">
            <template #default="{ row }">{{ row.paid_count }} / {{ row.items_count }}</template>
          </el-table-column>
          <el-table-column label="自动支付" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="row.auto_pay ? 'success' : 'info'">{{ row.auto_pay ? '是' : '否' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openRecurringEdit(row)">编辑</el-button>
              <el-button link type="danger" @click="removeRecurring(row)">取消</el-button>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </div>

    <el-dialog v-model="payDialog" title="债务还款" width="520px">
      <el-form label-width="100px">
        <el-form-item label="债务项">
          <span>{{ selectedDebt?.title }} / 剩余 ¥{{ money(selectedDebt?.payable_amount) }}</span>
        </el-form-item>
        <el-form-item label="还款金额">
          <el-input-number v-model="payForm.amount" :min="0" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="减免金额">
          <el-input-number v-model="payForm.discount" :min="0" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="支付渠道">
          <el-select v-model="payForm.channel" style="width: 100%" @change="onPayChannelChange">
            <el-option v-for="item in payChannelOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="payForm.channel === 'CREDIT_CARD'" label="信用卡">
          <el-select v-model="payForm.credit_card" style="width: 100%">
            <el-option v-for="item in cards" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-else label="支付账户">
          <el-select v-model="payForm.account" style="width: 100%">
            <el-option
              v-for="item in payAccounts"
              :key="item.id"
              :label="`${item.name}（¥${money(item.current_balance)}）`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="payForm.note" />
        </el-form-item>
        <el-form-item label="幂等键">
          <el-input v-model="payForm.idempotency_key" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="payDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitPay">确认还款</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="recurringDialog" :title="editingRecurring ? '编辑周期债务' : '新增周期债务'" width="600px" destroy-on-close>
      <el-form :model="recurringForm" label-width="104px">
        <el-form-item label="名称">
          <el-input v-model="recurringForm.name" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="recurringForm.debt_type" style="width: 100%">
            <el-option label="保险" value="INSURANCE" />
            <el-option label="房贷" value="MORTGAGE" />
            <el-option label="房租" value="RENT" />
            <el-option label="教育" value="EDUCATION" />
            <el-option label="其他" value="OTHER" />
          </el-select>
        </el-form-item>
        <el-form-item label="每期金额">
          <el-input-number v-model="recurringForm.amount" :min="0.01" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="期数">
          <el-input-number v-model="recurringForm.periods" :min="1" :max="600" />
          <span class="muted form-hint">间隔</span>
          <el-input-number v-model="recurringForm.interval_months" :min="1" :max="12" />
          <span class="muted form-hint">月</span>
        </el-form-item>
        <el-form-item label="首次到期">
          <el-date-picker v-model="recurringForm.first_due_date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="每期到期日">
          <el-input-number v-model="recurringForm.due_day" :min="1" :max="31" />
        </el-form-item>
        <el-form-item label="支付渠道">
          <el-select v-model="recurringForm.payment_channel" style="width: 100%">
            <el-option label="现金（储蓄卡）" value="CASH" />
            <el-option label="公积金" value="PROVIDENT_FUND" />
            <el-option label="信用卡" value="CREDIT_CARD" />
            <el-option label="支付宝" value="ALIPAY" />
            <el-option label="微信" value="WECHAT" />
          </el-select>
        </el-form-item>
        <el-form-item label="默认账户">
          <el-select v-model="recurringForm.account" clearable style="width: 100%">
            <el-option v-for="item in accounts" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="recurringForm.payment_channel === 'CREDIT_CARD'" label="默认信用卡">
          <el-select v-model="recurringForm.credit_card" clearable style="width: 100%">
            <el-option v-for="item in cards" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="支出分类">
          <el-select v-model="recurringForm.category_id" clearable filterable style="width: 100%">
            <el-option v-for="item in categories" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="自动支付">
          <el-switch v-model="recurringForm.auto_pay" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="recurringForm.note" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="recurringDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveRecurring">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import StatCard from '@/components/StatCard.vue'
import { api, unwrap } from '@/api'
import { errorMessage, money } from '@/api/client'

const items = ref<any[]>([])
const recurring = ref<any[]>([])
const accounts = ref<any[]>([])
const cards = ref<any[]>([])
const categories = ref<any[]>([])
const summary = ref<any>({})
const loading = ref(false)
const saving = ref(false)
const activeTab = ref('items')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const filters = reactive({ kind: '', status: '', month: '' })

const payDialog = ref(false)
const recurringDialog = ref(false)
const editingRecurring = ref<any>(null)
const selectedDebt = ref<any>(null)

const payForm = reactive<any>({
  amount: 0,
  discount: 0,
  channel: 'CASH',
  account: null,
  credit_card: null,
  note: '',
  idempotency_key: '',
})

const recurringForm = reactive<any>({
  name: '',
  debt_type: 'INSURANCE',
  amount: 0,
  periods: 12,
  interval_months: 1,
  first_due_date: '',
  due_day: 5,
  payment_channel: 'CASH',
  account: null,
  credit_card: null,
  category_id: null,
  auto_pay: false,
  note: '',
})

const channelOptions = [
  { value: 'CASH', label: '现金（储蓄卡）', types: ['SAVINGS'] },
  { value: 'PROVIDENT_FUND', label: '公积金', types: ['PROVIDENT_FUND_MAIN', 'PROVIDENT_FUND_SUPP'] },
  { value: 'CREDIT_CARD', label: '信用卡', types: [] },
  { value: 'ALIPAY', label: '支付宝', types: ['ALIPAY'] },
  { value: 'WECHAT', label: '微信', types: ['WECHAT'] },
]

const payChannelOptions = computed(() => {
  if (selectedDebt.value?.kind === 'CREDIT_CARD') {
    return channelOptions.filter((item) => ['CASH', 'ALIPAY', 'WECHAT'].includes(item.value))
  }
  if (selectedDebt.value?.kind === 'MORTGAGE') {
    return channelOptions.filter((item) => ['CASH', 'PROVIDENT_FUND'].includes(item.value))
  }
  return channelOptions
})

const payAccounts = computed(() => {
  const channel = channelOptions.find((item) => item.value === payForm.channel)
  if (!channel) return accounts.value
  return accounts.value.filter((item: any) => channel.types.includes(item.type) && item.is_active)
})

async function load() {
  loading.value = true
  try {
    const params: any = { page: page.value, page_size: pageSize.value, ordering: 'due_date' }
    if (filters.kind) params.kind = filters.kind
    if (filters.status) params.status = filters.status
    if (filters.month) params.month = filters.month
    const [itemRes, recurringRes, summaryRes, accountRes, cardRes, categoryRes] = await Promise.all([
      api.debts(params),
      api.recurringDebts({ page_size: 200 }),
      api.debtSummary(),
      api.accounts({ page_size: 200 }),
      api.cards({ page_size: 100 }),
      api.categories({ page_size: 300, kind: 'GENERAL', is_active: true }),
    ])
    items.value = unwrap(itemRes)
    total.value = itemRes.data.count ?? items.value.length
    recurring.value = unwrap(recurringRes)
    summary.value = summaryRes.data
    accounts.value = unwrap(accountRes)
    cards.value = unwrap(cardRes)
    categories.value = unwrap(categoryRes)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    loading.value = false
  }
}

function openPay(row: any) {
  selectedDebt.value = row
  payForm.amount = Number(row.payable_amount)
  payForm.discount = 0
  payForm.channel = row.kind === 'MORTGAGE' ? 'CASH' : 'CASH'
  payForm.account = accounts.value.find((item: any) => item.type === 'SAVINGS')?.id || null
  payForm.credit_card = null
  payForm.note = ''
  payForm.idempotency_key = ''
  payDialog.value = true
}

function onPayChannelChange() {
  payForm.account = null
  payForm.credit_card = null
  if (payForm.channel !== 'CREDIT_CARD') {
    payForm.account = payAccounts.value[0]?.id || null
  }
}

async function submitPay() {
  if (!payForm.amount && !payForm.discount) {
    ElMessage.warning('请填写还款或减免金额')
    return
  }
  if (payForm.channel === 'CREDIT_CARD' && !payForm.credit_card) {
    ElMessage.warning('请选择信用卡')
    return
  }
  if (payForm.channel !== 'CREDIT_CARD' && !payForm.account) {
    ElMessage.warning('请选择支付账户')
    return
  }
  saving.value = true
  try {
    await api.payDebt(selectedDebt.value.id, {
      amount: payForm.amount,
      discount: payForm.discount,
      channel: payForm.channel,
      account: payForm.channel === 'CREDIT_CARD' ? null : payForm.account,
      credit_card: payForm.channel === 'CREDIT_CARD' ? payForm.credit_card : null,
      note: payForm.note,
      idempotency_key: payForm.idempotency_key || undefined,
    })
    ElMessage.success('还款已记录')
    payDialog.value = false
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

async function cancelItem(row: any) {
  try {
    await ElMessageBox.confirm('取消后该债务项不再参与统计，确定继续？', '取消债务项', { type: 'warning' })
    await api.cancelDebt(row.id)
    ElMessage.success('已取消')
    await load()
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(errorMessage(error))
  }
}

function openRecurringCreate() {
  editingRecurring.value = null
  Object.assign(recurringForm, {
    name: '',
    debt_type: 'INSURANCE',
    amount: 0,
    periods: 12,
    interval_months: 1,
    first_due_date: '',
    due_day: 5,
    payment_channel: 'CASH',
    account: accounts.value.find((item: any) => item.type === 'SAVINGS')?.id || null,
    credit_card: null,
    category_id: categories.value.find((item: any) => item.name === '保险')?.id || null,
    auto_pay: false,
    note: '',
  })
  recurringDialog.value = true
}

function openRecurringEdit(row: any) {
  editingRecurring.value = row
  Object.assign(recurringForm, {
    name: row.name,
    debt_type: row.debt_type,
    amount: Number(row.amount),
    periods: row.periods,
    interval_months: row.interval_months,
    first_due_date: row.first_due_date,
    due_day: row.due_day,
    payment_channel: row.payment_channel,
    account: row.account,
    credit_card: row.credit_card,
    category_id: row.category,
    auto_pay: row.auto_pay,
    note: row.note,
  })
  recurringDialog.value = true
}

async function saveRecurring() {
  saving.value = true
  try {
    const payload = { ...recurringForm, category: recurringForm.category_id }
    delete payload.category_id
    if (editingRecurring.value) await api.updateRecurringDebt(editingRecurring.value.id, payload)
    else await api.createRecurringDebt(payload)
    ElMessage.success('已保存')
    recurringDialog.value = false
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

async function removeRecurring(row: any) {
  try {
    await ElMessageBox.confirm(`确定取消「${row.name}」的后续债务项？`, '取消周期债务', { type: 'warning' })
    await api.deleteRecurringDebt(row.id)
    ElMessage.success('已取消')
    await load()
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(errorMessage(error))
  }
}

async function generate() {
  loading.value = true
  try {
    const response = await api.generateDebts()
    ElMessage.success(`生成完成：${JSON.stringify(response.data)}`)
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    loading.value = false
  }
}

function statusType(status: string) {
  const map: any = { PAID: 'success', PARTIAL: 'warning', OVERDUE: 'danger', PENDING: 'info', CANCELLED: 'info' }
  return map[status] || 'info'
}

onMounted(load)
</script>

<style scoped>
.header-actions {
  display: flex;
  gap: 10px;
}
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 14px;
}
.pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
.expand {
  padding: 6px 18px;
  color: #4b5563;
  font-size: 12px;
  line-height: 1.9;
}
.payment-tag {
  margin-right: 6px;
  margin-bottom: 4px;
}
.form-hint {
  margin: 0 8px;
  font-size: 12px;
}
.tabs :deep(.el-tabs__header) {
  margin: 0;
}
</style>
