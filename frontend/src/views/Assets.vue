<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">资产管理</h2>
        <div class="page-subtitle">一笔资产可关联多笔流水，按关联金额或手工估值计算总价值</div>
      </div>
      <el-button type="primary" @click="openCreate">新增资产</el-button>
    </div>

    <div class="card-grid">
      <StatCard label="资产总价值" :value="`¥ ${money(totalValue)}`" :extra="`${assets.length} 项资产`" />
      <StatCard label="按流水汇总" :value="`${linkedCount} 项`" extra="关联流水的资产" />
      <StatCard label="手工估值" :value="`${manualCount} 项`" extra="以最近一次估值为准" />
    </div>

    <div class="panel">
      <el-table :data="assets" v-loading="loading" size="small" stripe>
        <el-table-column prop="name" label="资产名称" min-width="150" />
        <el-table-column prop="type_label" label="类型" width="100" />
        <el-table-column label="估值方式" width="130">
          <template #default="{ row }">
            <el-tag size="small" :type="row.valuation_mode === 'MANUAL' ? 'warning' : 'success'">
              {{ row.valuation_mode === 'MANUAL' ? '手工估值' : '流水汇总' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="当前价值" width="130" align="right">
          <template #default="{ row }"><strong>¥ {{ money(row.current_value) }}</strong></template>
        </el-table-column>
        <el-table-column prop="linked_count" label="关联流水" width="100" align="right" />
        <el-table-column prop="acquired_date" label="取得日期" width="110" />
        <el-table-column prop="status_label" label="状态" width="90" />
        <el-table-column prop="note" label="备注" min-width="150" show-overflow-tooltip />
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="showTransactions(row)">关联流水</el-button>
            <el-button link type="primary" @click="openValuation(row)">估值</el-button>
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!assets.length" description="暂无资产" :image-size="60" />
    </div>

    <el-dialog v-model="assetDialog" :title="editingAsset ? '编辑资产' : '新增资产'" width="560px" destroy-on-close>
      <el-form :model="assetForm" label-width="100px">
        <el-form-item label="资产名称">
          <el-input v-model="assetForm.name" />
        </el-form-item>
        <el-form-item label="资产类型">
          <el-select v-model="assetForm.type" style="width: 100%">
            <el-option label="房产" value="REAL_ESTATE" />
            <el-option label="车辆" value="VEHICLE" />
            <el-option label="数码" value="ELECTRONICS" />
            <el-option label="收藏" value="COLLECTIBLE" />
            <el-option label="贵金属" value="GOLD" />
            <el-option label="其他" value="OTHER" />
          </el-select>
        </el-form-item>
        <el-form-item label="估值方式">
          <el-radio-group v-model="assetForm.valuation_mode">
            <el-radio-button value="LINKED_SUM">按关联流水汇总</el-radio-button>
            <el-radio-button value="MANUAL">手工估值</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="assetForm.valuation_mode === 'MANUAL'" label="手工估值">
          <el-input-number v-model="assetForm.manual_value" :min="0" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="取得日期">
          <el-date-picker v-model="assetForm.acquired_date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="assetForm.status" style="width: 100%">
            <el-option label="持有" value="ACTIVE" />
            <el-option label="已处置" value="DISPOSED" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="assetForm.note" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="assetDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="transactionsDialog" :title="`${selectedAsset?.name} · 关联流水`" width="720px">
      <el-table :data="linkedTransactions" size="small">
        <el-table-column prop="occurred_at" label="时间" width="160" />
        <el-table-column prop="type" label="类型" width="100" />
        <el-table-column prop="category_name" label="分类" width="110" />
        <el-table-column label="流水金额" width="120" align="right">
          <template #default="{ row }">¥ {{ money(row.amount) }}</template>
        </el-table-column>
        <el-table-column label="计入资产" width="120" align="right">
          <template #default="{ row }">¥ {{ money(row.asset_amount) }}</template>
        </el-table-column>
        <el-table-column prop="note" label="备注" min-width="140" />
      </el-table>
      <el-empty v-if="!linkedTransactions.length" description="暂无关联流水" :image-size="60" />
    </el-dialog>

    <el-dialog v-model="valuationDialog" title="资产估值" width="520px">
      <el-form label-width="90px">
        <el-form-item label="估值金额">
          <el-input-number v-model="valuationForm.value" :min="0" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="估值日期">
          <el-date-picker v-model="valuationForm.valued_at" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="valuationForm.note" />
        </el-form-item>
      </el-form>
      <el-divider>历史估值</el-divider>
      <el-table :data="valuations" size="small" max-height="220">
        <el-table-column prop="valued_at" label="日期" width="120" />
        <el-table-column label="金额" width="140" align="right">
          <template #default="{ row }">¥ {{ money(row.value) }}</template>
        </el-table-column>
        <el-table-column prop="note" label="备注" />
      </el-table>
      <template #footer>
        <el-button @click="valuationDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveValuation">保存估值</el-button>
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

const assets = ref<any[]>([])
const loading = ref(false)
const saving = ref(false)
const assetDialog = ref(false)
const transactionsDialog = ref(false)
const valuationDialog = ref(false)
const editingAsset = ref<any>(null)
const selectedAsset = ref<any>(null)
const linkedTransactions = ref<any[]>([])
const valuations = ref<any[]>([])

const assetForm = reactive<any>({
  name: '',
  type: 'OTHER',
  valuation_mode: 'LINKED_SUM',
  manual_value: 0,
  acquired_date: new Date().toISOString().slice(0, 10),
  status: 'ACTIVE',
  note: '',
})

const valuationForm = reactive<any>({ value: 0, valued_at: new Date().toISOString().slice(0, 10), note: '' })

const totalValue = computed(() => assets.value.reduce((sum, item) => sum + Number(item.current_value || 0), 0))
const linkedCount = computed(() => assets.value.filter((item) => item.valuation_mode === 'LINKED_SUM').length)
const manualCount = computed(() => assets.value.filter((item) => item.valuation_mode === 'MANUAL').length)

async function load() {
  loading.value = true
  try {
    const response = await api.assets({ page_size: 200 })
    assets.value = unwrap(response)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingAsset.value = null
  Object.assign(assetForm, {
    name: '',
    type: 'OTHER',
    valuation_mode: 'LINKED_SUM',
    manual_value: 0,
    acquired_date: new Date().toISOString().slice(0, 10),
    status: 'ACTIVE',
    note: '',
  })
  assetDialog.value = true
}

function openEdit(asset: any) {
  editingAsset.value = asset
  Object.assign(assetForm, {
    name: asset.name,
    type: asset.type,
    valuation_mode: asset.valuation_mode,
    manual_value: Number(asset.manual_value),
    acquired_date: asset.acquired_date,
    status: asset.status,
    note: asset.note,
  })
  assetDialog.value = true
}

async function save() {
  saving.value = true
  try {
    if (editingAsset.value) await api.updateAsset(editingAsset.value.id, assetForm)
    else await api.createAsset(assetForm)
    ElMessage.success('已保存')
    assetDialog.value = false
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

async function showTransactions(asset: any) {
  selectedAsset.value = asset
  try {
    const response = await api.assetTransactions(asset.id)
    linkedTransactions.value = response.data
    transactionsDialog.value = true
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function openValuation(asset: any) {
  selectedAsset.value = asset
  valuationForm.value = Number(asset.current_value)
  valuationForm.valued_at = new Date().toISOString().slice(0, 10)
  valuationForm.note = ''
  try {
    const response = await api.assetValuations(asset.id)
    valuations.value = response.data
    valuationDialog.value = true
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function saveValuation() {
  saving.value = true
  try {
    await api.createValuation(selectedAsset.value.id, valuationForm)
    ElMessage.success('估值已记录')
    valuationDialog.value = false
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

async function remove(asset: any) {
  try {
    await ElMessageBox.confirm(`确定删除资产「${asset.name}」？关联流水会保留但不再计入资产。`, '删除资产', { type: 'warning' })
    await api.deleteAsset(asset.id)
    ElMessage.success('已删除')
    await load()
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(errorMessage(error))
  }
}

onMounted(load)
</script>
