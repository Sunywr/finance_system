<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">房贷管理</h2>
        <div class="page-subtitle">商贷/公积金贷款、还款计划与公积金冲还模拟</div>
      </div>
      <el-button type="primary" @click="openCreate">新增贷款</el-button>
    </div>

    <div class="card-grid">
      <div v-for="loan in loans" :key="loan.id" class="loan-card" @click="openSchedule(loan)">
        <div class="loan-head">
          <div>
            <div class="loan-name">{{ loan.name }}</div>
            <div class="loan-meta">{{ loan.loan_type_label }} · {{ loan.repayment_method_label }}</div>
          </div>
          <el-dropdown @command="(command: string) => handleCommand(command, loan)">
            <el-button text circle @click.stop><el-icon><MoreFilled /></el-icon></el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="schedule">还款计划</el-dropdown-item>
                <el-dropdown-item command="simulation">冲还模拟</el-dropdown-item>
                <el-dropdown-item command="offset">冲还配置</el-dropdown-item>
                <el-dropdown-item command="edit">编辑</el-dropdown-item>
                <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
        <div class="loan-amount mono">¥ {{ money(loan.principal) }}</div>
        <div class="loan-grid">
          <div><span class="muted">年利率</span><strong>{{ loan.annual_rate }}%</strong></div>
          <div><span class="muted">期数</span><strong>{{ loan.term_months }} 期</strong></div>
          <div><span class="muted">剩余本金</span><strong>¥ {{ money(loan.stats?.remaining_principal) }}</strong></div>
          <div><span class="muted">已还期数</span><strong>{{ loan.stats?.paid_periods }} 期</strong></div>
        </div>
        <div class="loan-foot">
          <span>下次还款 {{ loan.stats?.next_due?.due_date || '—' }}</span>
          <span>¥ {{ money(loan.stats?.next_due?.total_due) }}</span>
        </div>
      </div>
      <el-empty v-if="!loans.length" description="暂无贷款" />
    </div>

    <el-dialog v-model="loanDialog" :title="editingLoan ? '编辑贷款' : '新增贷款'" width="620px" destroy-on-close>
      <el-form :model="loanForm" label-width="110px">
        <el-form-item label="贷款名称">
          <el-input v-model="loanForm.name" />
        </el-form-item>
        <el-form-item label="贷款类型">
          <el-select v-model="loanForm.loan_type" style="width: 100%">
            <el-option label="商业贷款" value="COMMERCIAL" />
            <el-option label="公积金贷款" value="PROVIDENT_FUND" />
          </el-select>
        </el-form-item>
        <el-form-item label="贷款机构">
          <el-input v-model="loanForm.lender" />
        </el-form-item>
        <el-form-item label="贷款本金">
          <el-input-number v-model="loanForm.principal" :min="0.01" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="年利率(%)">
          <el-input-number v-model="loanForm.annual_rate" :min="0" :precision="4" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="期数(月)">
          <el-input-number v-model="loanForm.term_months" :min="1" :max="600" style="width: 100%" />
        </el-form-item>
        <el-form-item label="还款方式">
          <el-select v-model="loanForm.repayment_method" style="width: 100%">
            <el-option label="等额本息" value="EQUAL_INSTALLMENT" />
            <el-option label="等额本金" value="EQUAL_PRINCIPAL" />
          </el-select>
        </el-form-item>
        <el-form-item label="首次还款日">
          <el-date-picker v-model="loanForm.first_due_date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="每月还款日">
          <el-input-number v-model="loanForm.payment_day" :min="1" :max="31" />
        </el-form-item>
        <el-form-item label="现金还款账户">
          <el-select v-model="loanForm.repayment_account" clearable style="width: 100%">
            <el-option v-for="item in savingsAccounts" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="自动结清现金">
          <el-switch v-model="loanForm.auto_settle" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="loanForm.note" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="loanDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveLoan">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="scheduleDialog" :title="`${selectedLoan?.name} · 还款计划`" width="900px">
      <el-table :data="schedule" size="small" max-height="520">
        <el-table-column prop="period_no" label="期数" width="70" />
        <el-table-column prop="due_date" label="还款日" width="110" />
        <el-table-column label="应还本金" width="120" align="right">
          <template #default="{ row }">¥ {{ money(row.principal_due) }}</template>
        </el-table-column>
        <el-table-column label="应还利息" width="120" align="right">
          <template #default="{ row }">¥ {{ money(row.interest_due) }}</template>
        </el-table-column>
        <el-table-column label="合计" width="120" align="right">
          <template #default="{ row }">¥ {{ money(row.total_due) }}</template>
        </el-table-column>
        <el-table-column label="剩余本金" width="130" align="right">
          <template #default="{ row }">¥ {{ money(row.remaining_principal) }}</template>
        </el-table-column>
        <el-table-column prop="status_label" label="状态" width="90" />
      </el-table>
    </el-dialog>

    <el-dialog v-model="offsetDialog" title="公积金冲还配置" width="580px">
      <el-form :model="offsetForm" label-width="130px">
        <el-form-item label="启用冲还">
          <el-switch v-model="offsetForm.enabled" />
        </el-form-item>
        <el-form-item label="公积金账户">
          <el-select v-model="offsetForm.pf_account" style="width: 100%">
            <el-option v-for="item in pfAccounts" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="冲还方式">
          <el-radio-group v-model="offsetForm.mode">
            <el-radio-button value="FULL">全额冲还</el-radio-button>
            <el-radio-button value="PARTIAL">部分冲还</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="每月冲还上限">
          <el-input-number v-model="offsetForm.monthly_cap" :min="0" :precision="2" :controls="false" style="width: 100%" placeholder="部分冲还时生效" />
        </el-form-item>
        <el-form-item label="计入未来月缴">
          <el-switch v-model="offsetForm.use_new_contributions" />
        </el-form-item>
        <el-form-item label="现金差额自动扣">
          <el-switch v-model="offsetForm.auto_pay_cash" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="offsetDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveOffset">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="simulationDialog" title="公积金冲还模拟" width="820px">
      <div v-if="simulation" class="card-grid">
        <StatCard label="可支撑月数" :value="`${simulation.months_supported} 个月`" :extra="simulation.enabled ? '连续无需现金的期数' : '未启用冲还'" />
        <StatCard label="首笔现金日期" :value="simulation.first_cash_due_date || '暂无'" extra="公积金不足时需现金补足" />
        <StatCard label="当前公积金余额" :value="`¥ ${money(simulation.pf_balance)}`" :extra="`月缴 ¥${money(simulation.monthly_contribution)}`" />
        <StatCard label="未来现金缺口" :value="`¥ ${money(simulation.cash_total)}`" extra="未折现" />
      </div>
      <el-table v-if="simulation" :data="simulation.rows" size="small" max-height="380">
        <el-table-column prop="period_no" label="期数" width="70" />
        <el-table-column prop="due_date" label="还款日" width="110" />
        <el-table-column label="应还" width="110" align="right">
          <template #default="{ row }">¥ {{ money(row.total_due) }}</template>
        </el-table-column>
        <el-table-column label="公积金冲还" width="120" align="right">
          <template #default="{ row }">¥ {{ money(row.pf_offset) }}</template>
        </el-table-column>
        <el-table-column label="现金差额" width="120" align="right">
          <template #default="{ row }">
            <span :class="Number(row.cash_due) > 0 ? 'amount-negative' : 'amount-positive'">¥ {{ money(row.cash_due) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="冲还后公积金余额" min-width="150" align="right">
          <template #default="{ row }">¥ {{ money(row.pf_balance_after) }}</template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import StatCard from '@/components/StatCard.vue'
import { api, unwrap } from '@/api'
import { errorMessage, money } from '@/api/client'

const loans = ref<any[]>([])
const accounts = ref<any[]>([])
const saving = ref(false)
const loanDialog = ref(false)
const scheduleDialog = ref(false)
const offsetDialog = ref(false)
const simulationDialog = ref(false)
const editingLoan = ref<any>(null)
const selectedLoan = ref<any>(null)
const schedule = ref<any[]>([])
const simulation = ref<any>(null)

const loanForm = reactive<any>({
  name: '',
  loan_type: 'COMMERCIAL',
  lender: '',
  principal: 0,
  annual_rate: 4.2,
  term_months: 360,
  repayment_method: 'EQUAL_INSTALLMENT',
  first_due_date: '',
  payment_day: 10,
  repayment_account: null,
  auto_settle: false,
  note: '',
})

const offsetForm = reactive<any>({
  pf_account: null,
  enabled: true,
  mode: 'FULL',
  start_date: new Date().toISOString().slice(0, 10),
  monthly_cap: null,
  use_new_contributions: true,
  auto_pay_cash: false,
})

const savingsAccounts = computed(() => accounts.value.filter((item: any) => item.type === 'SAVINGS'))
const pfAccounts = computed(() =>
  accounts.value.filter((item: any) => ['PROVIDENT_FUND_MAIN', 'PROVIDENT_FUND_SUPP'].includes(item.type)),
)

async function load() {
  try {
    const [loanRes, accountRes] = await Promise.all([api.loans(), api.accounts({ page_size: 200 })])
    loans.value = unwrap(loanRes)
    accounts.value = unwrap(accountRes)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

function openCreate() {
  editingLoan.value = null
  Object.assign(loanForm, {
    name: '',
    loan_type: 'COMMERCIAL',
    lender: '',
    principal: 0,
    annual_rate: 4.2,
    term_months: 360,
    repayment_method: 'EQUAL_INSTALLMENT',
    first_due_date: '',
    payment_day: 10,
    repayment_account: savingsAccounts.value[0]?.id || null,
    auto_settle: false,
    note: '',
  })
  loanDialog.value = true
}

function openEdit(loan: any) {
  editingLoan.value = loan
  Object.assign(loanForm, {
    name: loan.name,
    loan_type: loan.loan_type,
    lender: loan.lender,
    principal: Number(loan.principal),
    annual_rate: Number(loan.annual_rate),
    term_months: loan.term_months,
    repayment_method: loan.repayment_method,
    first_due_date: loan.first_due_date,
    payment_day: loan.payment_day,
    repayment_account: loan.repayment_account,
    auto_settle: loan.auto_settle,
    note: loan.note,
  })
  loanDialog.value = true
}

async function saveLoan() {
  saving.value = true
  try {
    if (editingLoan.value) await api.updateLoan(editingLoan.value.id, loanForm)
    else await api.createLoan(loanForm)
    ElMessage.success('已保存')
    loanDialog.value = false
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

async function openSchedule(loan: any) {
  selectedLoan.value = loan
  try {
    const response = await api.loanSchedule(loan.id)
    schedule.value = response.data
    scheduleDialog.value = true
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function openOffset(loan: any) {
  selectedLoan.value = loan
  try {
    const response = await api.offsetPlan(loan.id)
    if (response.data?.detail) {
      Object.assign(offsetForm, {
        pf_account: pfAccounts.value[0]?.id || null,
        enabled: true,
        mode: 'FULL',
        start_date: new Date().toISOString().slice(0, 10),
        monthly_cap: null,
        use_new_contributions: true,
        auto_pay_cash: false,
      })
    } else {
      Object.assign(offsetForm, response.data)
    }
    offsetDialog.value = true
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function saveOffset() {
  saving.value = true
  try {
    await api.saveOffsetPlan(selectedLoan.value.id, offsetForm)
    ElMessage.success('冲还配置已保存')
    offsetDialog.value = false
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

async function openSimulation(loan: any) {
  selectedLoan.value = loan
  try {
    const response = await api.offsetSimulation(loan.id, {})
    simulation.value = response.data
    simulationDialog.value = true
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function removeLoan(loan: any) {
  try {
    await ElMessageBox.confirm(`确定删除贷款「${loan.name}」及其还款计划？`, '删除贷款', { type: 'warning' })
    await api.deleteLoan(loan.id)
    ElMessage.success('已删除')
    await load()
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(errorMessage(error))
  }
}

function handleCommand(command: string, loan: any) {
  if (command === 'schedule') openSchedule(loan)
  else if (command === 'offset') openOffset(loan)
  else if (command === 'simulation') openSimulation(loan)
  else if (command === 'edit') openEdit(loan)
  else if (command === 'delete') removeLoan(loan)
}

onMounted(load)
</script>

<style scoped>
.loan-card {
  background: #fff;
  border: 1px solid #eef2f7;
  border-radius: 12px;
  padding: 18px;
  cursor: pointer;
  transition: transform 0.15s ease;
}
.loan-card:hover {
  transform: translateY(-2px);
}
.loan-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}
.loan-name {
  font-weight: 700;
  font-size: 16px;
}
.loan-meta {
  color: #6b7280;
  font-size: 12px;
  margin-top: 4px;
}
.loan-amount {
  font-size: 26px;
  font-weight: 700;
  margin: 16px 0 14px;
}
.loan-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 16px;
  font-size: 13px;
}
.loan-grid .muted {
  display: block;
  font-size: 12px;
  margin-bottom: 2px;
}
.loan-foot {
  display: flex;
  justify-content: space-between;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #f1f5f9;
  color: #6b7280;
  font-size: 12px;
}
</style>
