<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">信用卡</h2>
        <div class="page-subtitle">账单周期、自动出账、分期与还款减免</div>
      </div>
      <div class="header-actions">
        <el-button :loading="loading" @click="generateBills">生成账单</el-button>
        <el-button type="primary" @click="openCreate">新增信用卡</el-button>
      </div>
    </div>

    <div class="card-grid">
      <div
        v-for="card in cards"
        :key="card.id"
        class="card-item"
        :class="{ active: selectedCard?.id === card.id }"
        @click="selectCard(card)"
      >
        <div class="card-head">
          <div>
            <div class="card-name">{{ card.name }}</div>
            <div class="card-bank">{{ card.bank }} · 尾号 {{ card.last4 || '—' }}</div>
          </div>
          <el-dropdown @command="(command: string) => handleCardCommand(command, card)">
            <el-button text circle @click.stop><el-icon><MoreFilled /></el-icon></el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="edit">编辑</el-dropdown-item>
                <el-dropdown-item command="delete" divided>停用</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
        <div class="card-limit">额度 ¥ {{ money(card.credit_limit) }}</div>
        <div class="card-row">
          <span>账单日 {{ card.statement_start_day }} - {{ card.statement_end_day }} 日</span>
          <span>还款日 {{ card.due_day }} 日</span>
        </div>
        <div v-if="card.current_summary" class="card-current">
          <div>
            <span class="muted">本期预计</span>
            <strong>¥ {{ money(card.current_summary.total) }}</strong>
          </div>
          <div>
            <span class="muted">可用额度</span>
            <strong>¥ {{ money(card.current_summary.available_credit) }}</strong>
          </div>
        </div>
      </div>
      <el-empty v-if="!cards.length" description="暂无信用卡" />
    </div>

    <div v-if="selectedCard" class="panel">
      <div class="panel-header">
        <h3 class="panel-title">{{ selectedCard.name }} · 账单</h3>
        <el-tag type="info" size="small">当前周期 {{ current?.period_start }} ~ {{ current?.period_end }}</el-tag>
      </div>
      <el-descriptions v-if="current" :column="4" border size="small" class="current-desc">
        <el-descriptions-item label="本期预计">¥ {{ money(current.total) }}</el-descriptions-item>
        <el-descriptions-item label="最低还款">¥ {{ money(current.min_payment) }}</el-descriptions-item>
        <el-descriptions-item label="已用额度">¥ {{ money(current.used_credit) }}</el-descriptions-item>
        <el-descriptions-item label="还款截止">{{ current.due_date }}</el-descriptions-item>
      </el-descriptions>
      <el-table :data="bills" size="small" v-loading="loading">
        <el-table-column label="账单周期" min-width="190">
          <template #default="{ row }">{{ row.period_label }}</template>
        </el-table-column>
        <el-table-column prop="due_date" label="还款截止" width="110" />
        <el-table-column label="普通消费" width="110" align="right">
          <template #default="{ row }">¥ {{ money(row.normal_total) }}</template>
        </el-table-column>
        <el-table-column label="分期" width="100" align="right">
          <template #default="{ row }">¥ {{ money(row.installment_total) }}</template>
        </el-table-column>
        <el-table-column label="退款" width="100" align="right">
          <template #default="{ row }">¥ {{ money(row.refund_total) }}</template>
        </el-table-column>
        <el-table-column label="账单金额" width="120" align="right">
          <template #default="{ row }"><strong>¥ {{ money(row.total_amount) }}</strong></template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 'OPEN' ? 'info' : 'success'">{{ row.status_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="还款状态" width="110">
          <template #default="{ row }">
            <el-tag v-if="row.debt_status" size="small" :type="row.debt_status === 'PAID' ? 'success' : row.debt_status === 'OVERDUE' ? 'danger' : 'warning'">
              {{ row.debt_status_label }}
            </el-tag>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.debt_item_id && row.debt_status !== 'PAID'" link type="primary" @click="openPay(row)">还款</el-button>
            <span v-else-if="row.debt_status === 'PAID'" class="muted">已还清</span>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!bills.length" description="暂无账单" :image-size="60" />
    </div>

    <div v-if="selectedCard" class="panel">
      <div class="panel-header">
        <h3 class="panel-title">分期计划</h3>
        <span class="muted">每期金额自动进入对应账单</span>
      </div>
      <el-table :data="installments" size="small">
        <el-table-column label="本金" width="120" align="right">
          <template #default="{ row }">¥ {{ money(row.principal) }}</template>
        </el-table-column>
        <el-table-column prop="periods" label="期数" width="80" />
        <el-table-column label="每期" width="120" align="right">
          <template #default="{ row }">¥ {{ money(row.per_period_amount) }}</template>
        </el-table-column>
        <el-table-column label="手续费" width="110" align="right">
          <template #default="{ row }">¥ {{ money(row.total_fee) }}</template>
        </el-table-column>
        <el-table-column prop="first_period_start" label="首期账单" width="120" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small">{{ row.status_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="期次明细" min-width="200">
          <template #default="{ row }">
            <el-button link type="primary" @click="showPeriods(row)">查看 {{ row.period_rows?.length }} 期</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!installments.length" description="暂无分期" :image-size="60" />
    </div>

    <el-dialog v-model="cardDialog" :title="editingCard ? '编辑信用卡' : '新增信用卡'" width="560px" destroy-on-close>
      <el-form :model="cardForm" label-width="108px">
        <el-form-item label="信用卡名称">
          <el-input v-model="cardForm.name" />
        </el-form-item>
        <el-form-item label="发卡行">
          <el-input v-model="cardForm.bank" />
        </el-form-item>
        <el-form-item label="卡号后四位">
          <el-input v-model="cardForm.last4" maxlength="8" />
        </el-form-item>
        <el-form-item label="账单起始日">
          <el-input-number v-model="cardForm.statement_start_day" :min="1" :max="31" />
          <span class="muted form-hint">账单周期从该日开始</span>
        </el-form-item>
        <el-form-item label="账单结束日">
          <el-input-number v-model="cardForm.statement_end_day" :min="1" :max="31" />
          <span class="muted form-hint">结束日早于起始日表示跨月</span>
        </el-form-item>
        <el-form-item label="还款日">
          <el-input-number v-model="cardForm.due_day" :min="1" :max="31" />
        </el-form-item>
        <el-form-item label="信用额度">
          <el-input-number v-model="cardForm.credit_limit" :precision="2" :min="0" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="最低还款比例">
          <el-input-number v-model="cardForm.min_payment_rate" :precision="4" :min="0" :max="1" :step="0.01" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="cardForm.note" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="cardDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveCard">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="payDialog" title="信用卡还款" width="480px">
      <el-form label-width="100px">
        <el-form-item label="账单">
          <span>{{ payBillRow?.period_label }} / 应还 ¥{{ money(payBillRow?.payable_amount) }}</span>
        </el-form-item>
        <el-form-item label="还款金额">
          <el-input-number v-model="payForm.amount" :min="0" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="减免金额">
          <el-input-number v-model="payForm.discount" :min="0" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="还款账户">
          <el-select v-model="payForm.account" filterable style="width: 100%">
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
          <el-input v-model="payForm.idempotency_key" placeholder="可选，防止重复提交" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="payDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitPay">确认还款</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="periodsDialog" title="分期期次" width="620px">
      <el-table :data="periodRows" size="small">
        <el-table-column prop="period_no" label="期数" width="70" />
        <el-table-column prop="bill_period_start" label="账单起始" width="110" />
        <el-table-column prop="bill_period_end" label="账单结束" width="110" />
        <el-table-column prop="due_date" label="还款日" width="110" />
        <el-table-column label="本金" width="110" align="right">
          <template #default="{ row }">¥ {{ money(row.principal_part) }}</template>
        </el-table-column>
        <el-table-column label="手续费" width="100" align="right">
          <template #default="{ row }">¥ {{ money(row.fee_part) }}</template>
        </el-table-column>
        <el-table-column label="应还" width="110" align="right">
          <template #default="{ row }">¥ {{ money(row.amount) }}</template>
        </el-table-column>
        <el-table-column prop="status_label" label="状态" width="90" />
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, unwrap } from '@/api'
import { errorMessage, money } from '@/api/client'

const cards = ref<any[]>([])
const accounts = ref<any[]>([])
const selectedCard = ref<any>(null)
const bills = ref<any[]>([])
const installments = ref<any[]>([])
const current = ref<any>(null)
const loading = ref(false)
const saving = ref(false)

const cardDialog = ref(false)
const payDialog = ref(false)
const periodsDialog = ref(false)
const editingCard = ref<any>(null)
const payBillRow = ref<any>(null)
const periodRows = ref<any[]>([])

const cardForm = reactive<any>({
  name: '',
  bank: '',
  last4: '',
  statement_start_day: 5,
  statement_end_day: 4,
  due_day: 20,
  credit_limit: 0,
  min_payment_rate: 0.1,
  note: '',
})

const payForm = reactive<any>({
  amount: 0,
  discount: 0,
  account: null,
  channel: 'CASH',
  note: '',
  idempotency_key: '',
})

const payAccounts = computed(() =>
  accounts.value.filter((item: any) => ['SAVINGS', 'ALIPAY', 'WECHAT'].includes(item.type) && item.is_active),
)

async function loadCards() {
  loading.value = true
  try {
    const [cardRes, accountRes] = await Promise.all([
      api.cards({ page_size: 100 }),
      api.accounts({ page_size: 200 }),
    ])
    cards.value = unwrap(cardRes)
    accounts.value = unwrap(accountRes)
    if (selectedCard.value) {
      selectedCard.value = cards.value.find((item: any) => item.id === selectedCard.value.id) || cards.value[0]
    }
    if (!selectedCard.value && cards.value.length) selectedCard.value = cards.value[0]
    if (selectedCard.value) await loadCardDetail()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    loading.value = false
  }
}

async function loadCardDetail() {
  if (!selectedCard.value) return
  const [billRes, currentRes, installmentRes] = await Promise.all([
    api.cardBills(selectedCard.value.id),
    api.cardCurrent(selectedCard.value.id),
    api.cardInstallments(selectedCard.value.id),
  ])
  bills.value = billRes.data
  current.value = currentRes.data
  installments.value = installmentRes.data
}

async function selectCard(card: any) {
  selectedCard.value = card
  try {
    await loadCardDetail()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

function openCreate() {
  editingCard.value = null
  Object.assign(cardForm, {
    name: '',
    bank: '',
    last4: '',
    statement_start_day: 5,
    statement_end_day: 4,
    due_day: 20,
    credit_limit: 0,
    min_payment_rate: 0.1,
    note: '',
  })
  cardDialog.value = true
}

function openEdit(card: any) {
  editingCard.value = card
  Object.assign(cardForm, {
    name: card.name,
    bank: card.bank,
    last4: card.last4,
    statement_start_day: card.statement_start_day,
    statement_end_day: card.statement_end_day,
    due_day: card.due_day,
    credit_limit: Number(card.credit_limit),
    min_payment_rate: Number(card.min_payment_rate),
    note: card.note,
  })
  cardDialog.value = true
}

async function saveCard() {
  saving.value = true
  try {
    if (editingCard.value) await api.updateCard(editingCard.value.id, cardForm)
    else await api.createCard(cardForm)
    ElMessage.success('已保存')
    cardDialog.value = false
    await loadCards()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

async function removeCard(card: any) {
  try {
    await ElMessageBox.confirm(`确定停用「${card.name}」？`, '停用信用卡', { type: 'warning' })
    await api.deleteCard(card.id)
    ElMessage.success('已停用')
    selectedCard.value = null
    await loadCards()
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(errorMessage(error))
  }
}

function handleCardCommand(command: string, card: any) {
  if (command === 'edit') openEdit(card)
  else if (command === 'delete') removeCard(card)
}

function openPay(bill: any) {
  payBillRow.value = bill
  payForm.amount = Number(bill.payable_amount)
  payForm.discount = 0
  payForm.account = payAccounts.value[0]?.id || null
  payForm.note = ''
  payForm.idempotency_key = ''
  payDialog.value = true
}

async function submitPay() {
  if (!payForm.account) {
    ElMessage.warning('请选择还款账户')
    return
  }
  saving.value = true
  try {
    await api.payBill(payBillRow.value.id, {
      amount: payForm.amount,
      discount: payForm.discount,
      channel: 'CASH',
      account: payForm.account,
      note: payForm.note,
      idempotency_key: payForm.idempotency_key || undefined,
    })
    ElMessage.success('还款已记录')
    payDialog.value = false
    await loadCards()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

function showPeriods(plan: any) {
  periodRows.value = plan.period_rows || []
  periodsDialog.value = true
}

async function generateBills() {
  loading.value = true
  try {
    const response = await api.generateBills()
    ElMessage.success(`账单生成完成：${JSON.stringify(response.data)}`)
    await loadCards()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    loading.value = false
  }
}

onMounted(loadCards)
</script>

<style scoped>
.header-actions {
  display: flex;
  gap: 10px;
}
.card-item {
  background: linear-gradient(135deg, #111827, #1f2937);
  color: #f9fafb;
  border-radius: 14px;
  padding: 18px;
  cursor: pointer;
  border: 2px solid transparent;
  transition: transform 0.15s ease, border-color 0.15s ease;
}
.card-item:hover {
  transform: translateY(-2px);
}
.card-item.active {
  border-color: #60a5fa;
}
.card-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}
.card-name {
  font-weight: 700;
  font-size: 16px;
}
.card-bank {
  color: #cbd5e1;
  font-size: 12px;
  margin-top: 4px;
}
.card-limit {
  margin-top: 18px;
  color: #cbd5e1;
  font-size: 12px;
}
.card-row {
  display: flex;
  justify-content: space-between;
  color: #cbd5e1;
  font-size: 12px;
  margin-top: 6px;
}
.card-current {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.12);
  font-size: 13px;
}
.card-current .muted {
  color: #9ca3af;
  display: block;
  margin-bottom: 2px;
}
.current-desc {
  margin-bottom: 14px;
}
.form-hint {
  margin-left: 10px;
  font-size: 12px;
}
</style>
