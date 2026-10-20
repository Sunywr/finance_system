<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">记账流水</h2>
        <div class="page-subtitle">支持现金、信用卡、转账、退款、分期与资产关联</div>
      </div>
      <div class="header-actions">
        <el-button @click="$router.push('/accounts')">账户</el-button>
        <el-button type="primary" @click="openCreate">记一笔</el-button>
      </div>
    </div>

    <div class="panel">
      <div class="filters">
        <el-date-picker
          v-model="filters.dates"
          type="daterange"
          value-format="YYYY-MM-DD"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          style="width: 250px"
        />
        <el-select v-model="filters.type" clearable placeholder="类型" style="width: 120px">
          <el-option label="支出" value="EXPENSE" />
          <el-option label="收入" value="INCOME" />
          <el-option label="退款" value="REFUND" />
          <el-option label="转账" value="TRANSFER_OUT" />
        </el-select>
        <el-select v-model="filters.category" clearable filterable placeholder="分类" style="width: 150px">
          <el-option v-for="item in categoryOptions" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
        <el-select v-model="filters.account" clearable placeholder="账户" style="width: 150px">
          <el-option v-for="item in accounts" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
        <el-select v-model="filters.credit_card" clearable placeholder="信用卡" style="width: 150px">
          <el-option v-for="item in cards" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
        <el-input v-model="filters.search" clearable placeholder="搜索备注/流水号" style="width: 190px" @keyup.enter="load" />
        <el-button @click="load">查询</el-button>
        <el-button text @click="resetFilters">重置</el-button>
      </div>

      <el-table :data="rows" v-loading="loading" size="small" stripe>
        <el-table-column prop="occurred_at" label="时间" width="150" />
        <el-table-column label="类型" width="84">
          <template #default="{ row }">
            <el-tag :type="typeTag(row.type)" size="small">{{ row.type_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="分类" min-width="120">
          <template #default="{ row }">
            <span>{{ row.category_name }}</span>
            <el-tag v-if="row.operation_label && row.operation !== 'NONE'" size="small" class="ml-4" type="warning">
              {{ row.operation_label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="130" align="right">
          <template #default="{ row }">
            <span :class="row.type === 'INCOME' || row.type === 'REFUND' ? 'amount-positive' : 'amount-negative'" class="mono">
              {{ row.type === 'INCOME' || row.type === 'REFUND' ? '+' : '-' }}{{ money(row.amount) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="支付方式" width="170">
          <template #default="{ row }">
            <span v-if="row.credit_card_name">💳 {{ row.credit_card_name }}</span>
            <span v-else>{{ row.account_name || row.channel_label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="标签" min-width="120">
          <template #default="{ row }">
            <el-tag v-for="tag in row.tags" :key="tag.id" size="small" :color="tag.color" class="tag-item" effect="plain">
              {{ tag.name }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="note" label="备注" min-width="150" show-overflow-tooltip />
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" :disabled="row.source !== 'MANUAL'" @click="openEdit(row)">编辑</el-button>
            <el-button link type="warning" :disabled="row.type !== 'EXPENSE' || row.status !== 'POSTED'" @click="openRefund(row)">退款</el-button>
            <el-button link type="danger" :disabled="row.source !== 'MANUAL' || row.status !== 'POSTED'" @click="voidRow(row)">作废</el-button>
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
    </div>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑流水' : '记一笔'" width="720px" destroy-on-close>
      <el-form :model="form" label-width="96px" class="form-grid">
        <el-form-item label="类型">
          <el-radio-group v-model="form.type" :disabled="Boolean(editingId)">
            <el-radio-button value="EXPENSE">支出</el-radio-button>
            <el-radio-button value="INCOME">收入</el-radio-button>
            <el-radio-button value="REFUND">退款</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="金额">
          <el-input-number v-model="form.amount" :min="0.01" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="时间">
          <el-date-picker v-model="form.occurred_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" style="width: 100%" />
        </el-form-item>
        <el-form-item v-if="form.type === 'REFUND'" label="原支出">
          <el-select v-model="form.refund_of" filterable placeholder="选择原支出流水" style="width: 100%">
            <el-option
              v-for="item in refundableTransactions"
              :key="item.id"
              :label="`${item.occurred_at} ${item.category_name} ¥${money(item.amount)}`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.type !== 'REFUND'" label="分类">
          <el-select v-model="form.category" filterable placeholder="选择分类" style="width: 100%" @change="onCategoryChange">
            <el-option v-for="item in categoryOptions" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.type !== 'REFUND' && isSpecialCategory" label="投资操作">
          <el-select v-model="form.operation" style="width: 100%">
            <el-option label="建仓" value="OPEN" />
            <el-option label="加仓" value="ADD" />
            <el-option label="减仓" value="REDUCE" />
            <el-option label="分红" value="DIVIDEND" />
          </el-select>
        </el-form-item>
        <template v-if="form.type !== 'REFUND'">
          <el-form-item label="支付方式">
            <el-select v-model="form.settlement_channel" style="width: 100%" @change="onChannelChange">
              <el-option v-for="item in channelOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="form.settlement_channel === 'CREDIT_CARD'" label="信用卡">
            <el-select v-model="form.credit_card" filterable placeholder="选择信用卡" style="width: 100%">
              <el-option v-for="item in cards" :key="item.id" :label="item.name" :value="item.id" />
            </el-select>
          </el-form-item>
          <el-form-item v-else label="资金账户">
            <el-select v-model="form.account" filterable placeholder="选择账户" style="width: 100%">
              <el-option v-for="item in paymentAccounts" :key="item.id" :label="`${item.name}（¥${money(item.current_balance)}）`" :value="item.id" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="form.type === 'EXPENSE' && !editingId" label="信用卡分期">
            <el-switch v-model="form.installments_enabled" />
            <span class="muted switch-tip">开启后按月生成分期账单，原消费不重复计入账单</span>
          </el-form-item>
          <template v-if="form.installments_enabled">
            <el-form-item label="分期期数">
              <el-input-number v-model="form.installment.periods" :min="1" :max="60" />
              <el-select v-model="form.installment.fee_mode" style="width: 160px; margin-left: 12px">
                <el-option label="免手续费" value="NONE" />
                <el-option label="一次性手续费" value="FLAT" />
                <el-option label="每期手续费" value="PER_PERIOD" />
              </el-select>
            </el-form-item>
            <el-form-item v-if="form.installment.fee_mode !== 'NONE'" label="费率(%)">
              <el-input-number v-model="form.installment.fee_rate" :min="0" :precision="4" :controls="false" />
            </el-form-item>
            <el-form-item label="每期预览">
              <el-button :loading="previewing" @click="previewInstallment">试算</el-button>
              <span v-if="preview.total" class="preview-text">
                每期约 ¥{{ money(preview.rows?.[0]?.amount) }}，共 {{ preview.rows?.length }} 期，手续费 ¥{{ money(preview.total_fee) }}
              </span>
            </el-form-item>
          </template>
          <el-form-item label="标签">
            <el-select v-model="form.tags" multiple filterable placeholder="选择标签" style="width: 100%">
              <el-option v-for="item in tags" :key="item.id" :label="item.name" :value="item.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="新标签">
            <el-input v-model="form.tag_names" placeholder="逗号分隔，例如：报销,大额" />
          </el-form-item>
          <el-form-item label="关联资产">
            <el-select v-model="form.asset" clearable filterable placeholder="关联已有资产" style="width: 100%">
              <el-option v-for="item in assets" :key="item.id" :label="item.name" :value="item.id" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="!form.asset" label="或新建资产">
            <el-input v-model="form.asset_name" placeholder="资产名称（可选）" style="width: 60%" />
            <el-input-number v-model="form.asset_amount" :min="0" :precision="2" :controls="false" placeholder="计入金额" style="width: 35%; margin-left: 8px" />
          </el-form-item>
        </template>
        <el-form-item label="备注">
          <el-input v-model="form.note" type="textarea" :rows="2" maxlength="500" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="refundVisible" title="退款" width="440px">
      <el-form label-width="96px">
        <el-form-item label="原流水">{{ refundRow?.occurred_at }} / {{ refundRow?.category_name }} / ¥{{ money(refundRow?.amount) }}</el-form-item>
        <el-form-item label="退款金额">
          <el-input-number v-model="refundForm.amount" :min="0.01" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item v-if="refundRow?.installment_plan_id" label="分期处理">
          <el-checkbox v-model="refundForm.cancel_installment">取消后续未出账分期</el-checkbox>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="refundForm.note" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="refundVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitRefund">确认退款</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="editVisible" title="编辑流水" width="520px">
      <el-form label-width="92px">
        <el-form-item label="金额">
          <el-input-number v-model="editForm.amount" :min="0.01" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="时间">
          <el-date-picker v-model="editForm.occurred_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" style="width: 100%" />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="editForm.category" filterable style="width: 100%">
            <el-option v-for="item in categoryOptions" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="editForm.note" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import dayjs from 'dayjs'
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, unwrap } from '@/api'
import { errorMessage, money } from '@/api/client'

const rows = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const saving = ref(false)
const previewing = ref(false)

const accounts = ref<any[]>([])
const cards = ref<any[]>([])
const categories = ref<any[]>([])
const tags = ref<any[]>([])
const assets = ref<any[]>([])
const refundableTransactions = ref<any[]>([])

const filters = reactive({ dates: [] as string[], type: '', category: '', account: '', credit_card: '', search: '' })

const dialogVisible = ref(false)
const refundVisible = ref(false)
const editVisible = ref(false)
const editingId = ref<number | null>(null)
const refundRow = ref<any>(null)
const preview = reactive<any>({ total: 0, total_fee: 0, rows: [] })

const channelOptions = [
  { value: 'CASH', label: '现金（储蓄卡）', types: ['SAVINGS'] },
  { value: 'ALIPAY', label: '支付宝', types: ['ALIPAY'] },
  { value: 'WECHAT', label: '微信', types: ['WECHAT'] },
  { value: 'PROVIDENT_FUND', label: '公积金', types: ['PROVIDENT_FUND_MAIN', 'PROVIDENT_FUND_SUPP'] },
  { value: 'CREDIT_CARD', label: '信用卡', types: [] },
  { value: 'STOCK', label: '股票账户', types: ['STOCK'] },
  { value: 'WEALTH', label: '理财账户', types: ['WEALTH'] },
]

function emptyForm() {
  return {
    type: 'EXPENSE',
    amount: undefined as number | undefined,
    occurred_at: dayjs().format('YYYY-MM-DDTHH:mm:ss'),
    category: null as number | null,
    settlement_channel: 'CASH',
    account: null as number | null,
    credit_card: null as number | null,
    operation: 'NONE',
    note: '',
    tags: [] as number[],
    tag_names: '',
    refund_of: null as number | null,
    cancel_installment: false,
    asset: null as number | null,
    asset_amount: null as number | null,
    asset_name: '',
    asset_type: 'OTHER',
    installments_enabled: false,
    installment: { periods: 6, fee_mode: 'NONE', fee_rate: 0 },
  }
}

const form = reactive<any>(emptyForm())
const refundForm = reactive<any>({ amount: 0, note: '', cancel_installment: false })
const editForm = reactive<any>({ amount: 0, occurred_at: '', category: null, note: '' })

const categoryOptions = computed(() => categories.value)
const selectedCategory = computed(() => categories.value.find((item) => item.id === form.category))
const isSpecialCategory = computed(() =>
  ['INVESTMENT', 'STOCK'].includes(selectedCategory.value?.kind),
)
const paymentAccounts = computed(() => {
  const channel = channelOptions.find((item) => item.value === form.settlement_channel)
  if (!channel) return accounts.value
  return accounts.value.filter((item) => channel.types.includes(item.type))
})

async function loadOptions() {
  const [accountRes, cardRes, categoryRes, tagRes, assetRes] = await Promise.all([
    api.accounts({ page_size: 200 }),
    api.cards({ page_size: 100 }),
    api.categories({ page_size: 300, is_active: true }),
    api.tags({ page_size: 200 }),
    api.assets({ page_size: 200, status: 'ACTIVE' }),
  ])
  accounts.value = unwrap(accountRes)
  cards.value = unwrap(cardRes)
  categories.value = unwrap(categoryRes)
  tags.value = unwrap(tagRes)
  assets.value = unwrap(assetRes)
}

async function load() {
  loading.value = true
  try {
    const params: any = {
      page: page.value,
      page_size: pageSize.value,
      ordering: '-occurred_at',
      search: filters.search || undefined,
      type: filters.type || undefined,
      category: filters.category || undefined,
      account: filters.account || undefined,
      credit_card: filters.credit_card || undefined,
    }
    if (filters.dates?.length === 2) {
      params.date_from = filters.dates[0]
      params.date_to = filters.dates[1]
    }
    const response = await api.transactions(params)
    rows.value = unwrap(response)
    total.value = response.data.count ?? rows.value.length
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    loading.value = false
  }
}

async function loadRefundable() {
  try {
    const response = await api.transactions({ page_size: 200, type: 'EXPENSE', status: 'POSTED', ordering: '-occurred_at' })
    refundableTransactions.value = unwrap(response)
  } catch {
    refundableTransactions.value = []
  }
}

function resetFilters() {
  filters.dates = []
  filters.type = ''
  filters.category = ''
  filters.account = ''
  filters.credit_card = ''
  filters.search = ''
  page.value = 1
  load()
}

function openCreate() {
  Object.assign(form, emptyForm())
  preview.total = 0
  preview.total_fee = 0
  preview.rows = []
  dialogVisible.value = true
  loadRefundable()
}

function openEdit(row: any) {
  editingId.value = row.id
  editForm.amount = Number(row.amount)
  editForm.occurred_at = String(row.occurred_at).replace(' ', 'T').slice(0, 19)
  editForm.category = row.category
  editForm.note = row.note
  editVisible.value = true
}

function openRefund(row: any) {
  refundRow.value = row
  refundForm.amount = Number(row.amount)
  refundForm.note = ''
  refundForm.cancel_installment = false
  refundVisible.value = true
}

function onChannelChange() {
  form.account = null
  form.credit_card = null
  if (form.settlement_channel === 'CREDIT_CARD') form.account = null
}

function onCategoryChange() {
  if (isSpecialCategory.value && form.operation === 'NONE') form.operation = 'OPEN'
  if (!isSpecialCategory.value) form.operation = 'NONE'
}

async function previewInstallment() {
  if (!form.credit_card || !form.amount) {
    ElMessage.warning('请先选择信用卡并填写金额')
    return
  }
  previewing.value = true
  try {
    const response = await api.previewInstallment({
      credit_card: form.credit_card,
      principal: form.amount,
      periods: form.installment.periods,
      fee_mode: form.installment.fee_mode,
      fee_rate: form.installment.fee_rate,
      purchase_at: form.occurred_at,
    })
    Object.assign(preview, response.data)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    previewing.value = false
  }
}

async function submit() {
  if (!form.amount || form.amount <= 0) {
    ElMessage.warning('请填写金额')
    return
  }
  saving.value = true
  try {
    if (form.type === 'REFUND') {
      if (!form.refund_of) {
        ElMessage.warning('请选择原支出流水')
        return
      }
      await api.createTransaction({
        type: 'REFUND',
        amount: form.amount,
        occurred_at: form.occurred_at,
        refund_of: form.refund_of,
        note: form.note,
        cancel_installment: form.cancel_installment,
      })
    } else {
      const payload: any = {
        type: form.type,
        amount: form.amount,
        occurred_at: form.occurred_at,
        category: form.category,
        settlement_channel: form.settlement_channel,
        operation: form.operation,
        note: form.note,
        tags: form.tags,
        tag_names: form.tag_names ? form.tag_names.split(',').map((item: string) => item.trim()).filter(Boolean) : [],
        asset: form.asset || null,
        asset_amount: form.asset_amount,
        asset_name: form.asset_name,
        asset_type: form.asset_type,
      }
      if (form.settlement_channel === 'CREDIT_CARD') payload.credit_card = form.credit_card
      else payload.account = form.account
      if (form.installments_enabled) {
        if (!form.credit_card) {
          ElMessage.warning('分期必须选择信用卡')
          return
        }
        payload.type = 'EXPENSE'
        payload.installment = { ...form.installment }
      }
      await api.createTransaction(payload)
    }
    ElMessage.success('已保存')
    dialogVisible.value = false
    page.value = 1
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

async function submitEdit() {
  saving.value = true
  try {
    await api.updateTransaction(editingId.value as number, {
      amount: editForm.amount,
      occurred_at: editForm.occurred_at,
      category: editForm.category,
      note: editForm.note,
    })
    ElMessage.success('已更新')
    editVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

async function submitRefund() {
  saving.value = true
  try {
    await api.refundTransaction(refundRow.value.id, { ...refundForm })
    ElMessage.success('退款已记录')
    refundVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

async function voidRow(row: any) {
  try {
    await ElMessageBox.confirm('作废后不参与余额和统计，确定继续？', '作废流水', { type: 'warning' })
    await api.voidTransaction(row.id, '手工作废')
    ElMessage.success('已作废')
    await load()
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(errorMessage(error))
  }
}

function typeTag(type: string) {
  const map: any = { EXPENSE: 'danger', INCOME: 'success', REFUND: 'warning', TRANSFER_OUT: 'info', TRANSFER_IN: 'info' }
  return map[type] || 'info'
}

onMounted(async () => {
  await loadOptions()
  await load()
})
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
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  column-gap: 18px;
}
.form-grid :deep(.el-form-item:last-child) {
  grid-column: span 2;
}
.tag-item {
  margin-right: 4px;
  margin-bottom: 2px;
  border: none;
}
.ml-4 {
  margin-left: 4px;
}
.switch-tip {
  margin-left: 10px;
  font-size: 12px;
}
.preview-text {
  margin-left: 12px;
  color: #2563eb;
  font-size: 13px;
}
@media (max-width: 760px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
  .form-grid :deep(.el-form-item:last-child) {
    grid-column: span 1;
  }
}
</style>
