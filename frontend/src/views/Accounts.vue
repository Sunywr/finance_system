<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">账户管理</h2>
        <div class="page-subtitle">储蓄卡、公积金、股票、理财、支付宝、微信账户与互转</div>
      </div>
      <div class="header-actions">
        <el-button @click="openTransfer">账户互转</el-button>
        <el-button type="primary" @click="openCreate">新增账户</el-button>
      </div>
    </div>

    <div class="card-grid">
      <div v-for="account in accounts" :key="account.id" class="account-card">
        <div class="account-top">
          <div>
            <div class="account-name">{{ account.name }}</div>
            <div class="account-type">{{ account.type_label }} · {{ account.institution || '未填写机构' }}</div>
          </div>
          <el-dropdown @command="(command: string) => handleAccountCommand(command, account)">
            <el-button text circle><el-icon><MoreFilled /></el-icon></el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="detail">余额构成</el-dropdown-item>
                <el-dropdown-item command="edit">编辑</el-dropdown-item>
                <el-dropdown-item v-if="isPf(account)" command="pf">公积金配置</el-dropdown-item>
                <el-dropdown-item command="delete" divided>停用</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
        <div class="account-balance mono">¥ {{ money(account.current_balance) }}</div>
        <div class="account-foot">
          <span class="muted">{{ account.note || '—' }}</span>
          <el-tag v-if="!account.is_active" size="small" type="info">已停用</el-tag>
        </div>
      </div>
      <el-empty v-if="!accounts.length" description="暂无账户" />
    </div>

    <div class="panel">
      <div class="panel-header">
        <h3 class="panel-title">最近转账</h3>
        <span class="muted">每次转账自动生成转出/转入两条流水</span>
      </div>
      <el-table :data="transfers" size="small">
        <el-table-column prop="occurred_at" label="时间" width="160" />
        <el-table-column label="从" min-width="140">
          <template #default="{ row }">{{ row.from_account_name }}</template>
        </el-table-column>
        <el-table-column label="到" min-width="140">
          <template #default="{ row }">{{ row.to_account_name }}</template>
        </el-table-column>
        <el-table-column label="金额" width="130" align="right">
          <template #default="{ row }">¥ {{ money(row.amount) }}</template>
        </el-table-column>
        <el-table-column label="手续费" width="110" align="right">
          <template #default="{ row }">¥ {{ money(row.fee) }}</template>
        </el-table-column>
        <el-table-column prop="note" label="备注" min-width="160" />
      </el-table>
      <el-empty v-if="!transfers.length" description="暂无转账" :image-size="60" />
    </div>

    <el-dialog v-model="accountDialog" :title="editingAccount ? '编辑账户' : '新增账户'" width="560px" destroy-on-close>
      <el-form :model="accountForm" label-width="92px">
        <el-form-item label="账户名称">
          <el-input v-model="accountForm.name" />
        </el-form-item>
        <el-form-item label="账户类型">
          <el-select v-model="accountForm.type" style="width: 100%" :disabled="Boolean(editingAccount)">
            <el-option v-for="item in accountTypes" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="机构">
          <el-input v-model="accountForm.institution" />
        </el-form-item>
        <el-form-item label="期初余额">
          <el-input-number v-model="accountForm.opening_balance" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="期初日期">
          <el-date-picker v-model="accountForm.opening_date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="允许负余额">
          <el-switch v-model="accountForm.allow_negative" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="accountForm.note" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="accountDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveAccount">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="transferDialog" title="账户互转" width="520px" destroy-on-close>
      <el-form :model="transferForm" label-width="92px">
        <el-form-item label="转出账户">
          <el-select v-model="transferForm.from_account" filterable style="width: 100%">
            <el-option v-for="item in accounts.filter((a: any) => a.is_active)" :key="item.id" :label="`${item.name}（¥${money(item.current_balance)}）`" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="转入账户">
          <el-select v-model="transferForm.to_account" filterable style="width: 100%">
            <el-option v-for="item in accounts.filter((a: any) => a.is_active)" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="转账金额">
          <el-input-number v-model="transferForm.amount" :min="0.01" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="手续费">
          <el-input-number v-model="transferForm.fee" :min="0" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="时间">
          <el-date-picker v-model="transferForm.occurred_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="transferForm.note" />
        </el-form-item>
        <el-form-item label="幂等键">
          <el-input v-model="transferForm.idempotency_key" placeholder="可选，防止重复提交" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="transferDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitTransfer">确认转账</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="pfDialog" title="公积金配置" width="520px">
      <el-form :model="pfForm" label-width="110px">
        <el-form-item label="账户性质">
          <el-select v-model="pfForm.fund_type" style="width: 100%">
            <el-option label="主账户" value="MAIN" />
            <el-option label="补充账户" value="SUPPLEMENTARY" />
          </el-select>
        </el-form-item>
        <el-form-item label="个人月缴">
          <el-input-number v-model="pfForm.monthly_employee_amount" :min="0" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="单位月缴">
          <el-input-number v-model="pfForm.monthly_employer_amount" :min="0" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="每月缴存日">
          <el-input-number v-model="pfForm.contribution_day" :min="1" :max="28" style="width: 100%" />
        </el-form-item>
        <el-form-item label="自动生成流水">
          <el-switch v-model="pfForm.auto_contribute" />
        </el-form-item>
        <el-form-item label="城市">
          <el-input v-model="pfForm.city" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pfDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="savePf">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="detailDialog" title="余额构成" width="480px">
      <el-descriptions v-if="balanceDetail" :column="1" border size="small">
        <el-descriptions-item label="期初余额">¥ {{ money(balanceDetail.opening_balance) }}</el-descriptions-item>
        <el-descriptions-item label="收入">¥ {{ money(balanceDetail.income) }}</el-descriptions-item>
        <el-descriptions-item label="退款">¥ {{ money(balanceDetail.refund) }}</el-descriptions-item>
        <el-descriptions-item label="支出">¥ {{ money(balanceDetail.expense) }}</el-descriptions-item>
        <el-descriptions-item label="转入">¥ {{ money(balanceDetail.transfer_in) }}</el-descriptions-item>
        <el-descriptions-item label="转出">¥ {{ money(balanceDetail.transfer_out) }}</el-descriptions-item>
        <el-descriptions-item label="当前余额">
          <strong>¥ {{ money(balanceDetail.current_balance) }}</strong>
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import dayjs from 'dayjs'
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, unwrap } from '@/api'
import { errorMessage, money } from '@/api/client'

const accounts = ref<any[]>([])
const transfers = ref<any[]>([])
const saving = ref(false)

const accountDialog = ref(false)
const transferDialog = ref(false)
const pfDialog = ref(false)
const detailDialog = ref(false)
const editingAccount = ref<any>(null)
const balanceDetail = ref<any>(null)
const pfAccount = ref<any>(null)

const accountTypes = [
  { value: 'SAVINGS', label: '储蓄卡' },
  { value: 'PROVIDENT_FUND_MAIN', label: '公积金主账户' },
  { value: 'PROVIDENT_FUND_SUPP', label: '公积金补充账户' },
  { value: 'STOCK', label: '股票账户' },
  { value: 'WEALTH', label: '理财账户' },
  { value: 'ALIPAY', label: '支付宝' },
  { value: 'WECHAT', label: '微信' },
]

const accountForm = reactive<any>({
  name: '',
  type: 'SAVINGS',
  institution: '',
  opening_balance: 0,
  opening_date: dayjs().format('YYYY-MM-DD'),
  allow_negative: false,
  note: '',
})

const transferForm = reactive<any>({
  from_account: null,
  to_account: null,
  amount: undefined,
  fee: 0,
  occurred_at: dayjs().format('YYYY-MM-DDTHH:mm:ss'),
  note: '',
  idempotency_key: '',
})

const pfForm = reactive<any>({
  fund_type: 'MAIN',
  monthly_employee_amount: 0,
  monthly_employer_amount: 0,
  contribution_day: 10,
  auto_contribute: false,
  city: '',
})

function isPf(account: any) {
  return ['PROVIDENT_FUND_MAIN', 'PROVIDENT_FUND_SUPP'].includes(account.type)
}

async function load() {
  try {
    const [accountRes, transferRes] = await Promise.all([
      api.accounts({ page_size: 200 }),
      api.transfers({ page_size: 20 }),
    ])
    accounts.value = unwrap(accountRes)
    transfers.value = unwrap(transferRes)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

function openCreate() {
  editingAccount.value = null
  Object.assign(accountForm, {
    name: '',
    type: 'SAVINGS',
    institution: '',
    opening_balance: 0,
    opening_date: dayjs().format('YYYY-MM-DD'),
    allow_negative: false,
    note: '',
  })
  accountDialog.value = true
}

function openEdit(account: any) {
  editingAccount.value = account
  Object.assign(accountForm, {
    name: account.name,
    type: account.type,
    institution: account.institution,
    opening_balance: Number(account.opening_balance),
    opening_date: account.opening_date,
    allow_negative: account.allow_negative,
    note: account.note,
  })
  accountDialog.value = true
}

async function saveAccount() {
  saving.value = true
  try {
    if (editingAccount.value) {
      await api.updateAccount(editingAccount.value.id, accountForm)
    } else {
      await api.createAccount(accountForm)
    }
    ElMessage.success('已保存')
    accountDialog.value = false
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

function openTransfer() {
  Object.assign(transferForm, {
    from_account: accounts.value.find((a: any) => a.type === 'SAVINGS')?.id || null,
    to_account: null,
    amount: undefined,
    fee: 0,
    occurred_at: dayjs().format('YYYY-MM-DDTHH:mm:ss'),
    note: '',
    idempotency_key: '',
  })
  transferDialog.value = true
}

async function submitTransfer() {
  if (!transferForm.from_account || !transferForm.to_account || !transferForm.amount) {
    ElMessage.warning('请选择账户并填写金额')
    return
  }
  saving.value = true
  try {
    await api.createTransfer({ ...transferForm, idempotency_key: transferForm.idempotency_key || undefined })
    ElMessage.success('转账成功')
    transferDialog.value = false
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

async function openPf(account: any) {
  pfAccount.value = account
  try {
    const response = await api.pfProfile(account.id)
    Object.assign(pfForm, response.data)
    pfDialog.value = true
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function savePf() {
  saving.value = true
  try {
    await api.savePfProfile(pfAccount.value.id, pfForm)
    ElMessage.success('公积金配置已保存')
    pfDialog.value = false
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

async function showDetail(account: any) {
  try {
    const response = await api.accountBalance(account.id)
    balanceDetail.value = response.data
    detailDialog.value = true
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function removeAccount(account: any) {
  try {
    await ElMessageBox.confirm(`确定停用账户「${account.name}」？历史流水会保留。`, '停用账户', { type: 'warning' })
    await api.deleteAccount(account.id)
    ElMessage.success('已停用')
    await load()
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(errorMessage(error))
  }
}

function handleAccountCommand(command: string, account: any) {
  if (command === 'edit') openEdit(account)
  else if (command === 'detail') showDetail(account)
  else if (command === 'pf') openPf(account)
  else if (command === 'delete') removeAccount(account)
}

onMounted(load)
</script>

<style scoped>
.header-actions {
  display: flex;
  gap: 10px;
}
.account-card {
  background: #fff;
  border: 1px solid #eef2f7;
  border-radius: 12px;
  padding: 16px 18px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}
.account-top {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}
.account-name {
  font-weight: 700;
  font-size: 15px;
}
.account-type {
  color: #6b7280;
  font-size: 12px;
  margin-top: 4px;
}
.account-balance {
  font-size: 26px;
  font-weight: 700;
  margin: 18px 0 12px;
  letter-spacing: -0.02em;
}
.account-foot {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
}
</style>
