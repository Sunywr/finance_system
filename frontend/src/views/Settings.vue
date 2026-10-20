<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">设置</h2>
        <div class="page-subtitle">发薪日、工资、分类、标签与账号安全</div>
      </div>
      <div class="header-actions">
        <el-button @click="openApiDocs">API 文档</el-button>
      </div>
    </div>

    <div class="two-column">
      <div class="panel">
        <div class="panel-header">
          <h3 class="panel-title">发薪与工资</h3>
        </div>
        <el-form :model="settingForm" label-width="110px">
          <el-form-item label="发薪日">
            <el-input-number v-model="settingForm.payday" :min="1" :max="31" />
            <span class="muted form-hint">超过当月天数时按月末处理</span>
          </el-form-item>
          <el-form-item label="预计月薪">
            <el-input-number v-model="settingForm.salary_amount" :min="0" :precision="2" :controls="false" style="width: 100%" />
          </el-form-item>
          <el-form-item label="工资账户">
            <el-select v-model="settingForm.salary_account" clearable style="width: 100%">
              <el-option v-for="item in savingsAccounts" :key="item.id" :label="item.name" :value="item.id" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="saving" @click="saveSettings">保存设置</el-button>
          </el-form-item>
        </el-form>
      </div>

      <div class="panel">
        <div class="panel-header">
          <h3 class="panel-title">修改密码</h3>
        </div>
        <el-form :model="passwordForm" label-width="100px">
          <el-form-item label="原密码">
            <el-input v-model="passwordForm.old_password" type="password" show-password />
          </el-form-item>
          <el-form-item label="新密码">
            <el-input v-model="passwordForm.new_password" type="password" show-password />
          </el-form-item>
          <el-form-item>
            <el-button :loading="saving" @click="changePassword">修改密码</el-button>
          </el-form-item>
        </el-form>
        <el-divider />
        <div class="system-info">
          <div><span class="muted">后端 API</span><code>/api/v1</code></div>
          <div><span class="muted">接口文档</span><code>/api/docs</code></div>
          <div><span class="muted">货币</span><code>CNY</code></div>
          <div><span class="muted">时区</span><code>Asia/Shanghai</code></div>
        </div>
      </div>
    </div>

    <div class="two-column">
      <div class="panel">
        <div class="panel-header">
          <h3 class="panel-title">分类</h3>
          <el-button size="small" @click="openCategoryCreate">新增分类</el-button>
        </div>
        <el-table :data="categories" size="small" max-height="440">
          <el-table-column prop="name" label="名称" min-width="120">
            <template #default="{ row }">
              <span class="color-dot" :style="{ background: row.color }"></span>{{ row.name }}
            </template>
          </el-table-column>
          <el-table-column prop="kind_label" label="类型" width="90" />
          <el-table-column prop="parent_name" label="父分类" width="100" />
          <el-table-column label="系统" width="70">
            <template #default="{ row }">
              <el-tag v-if="row.is_system" size="small" type="warning">系统</el-tag>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openCategoryEdit(row)">编辑</el-button>
              <el-button link type="danger" :disabled="row.is_system" @click="removeCategory(row)">停用</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="panel">
        <div class="panel-header">
          <h3 class="panel-title">标签</h3>
          <el-button size="small" @click="openTagCreate">新增标签</el-button>
        </div>
        <el-table :data="tags" size="small" max-height="440">
          <el-table-column prop="name" label="名称" min-width="140">
            <template #default="{ row }">
              <el-tag :color="row.color" effect="plain">{{ row.name }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="90">
            <template #default="{ row }">
              <el-button link type="danger" @click="removeTag(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <el-dialog v-model="categoryDialog" :title="editingCategory ? '编辑分类' : '新增分类'" width="480px">
      <el-form :model="categoryForm" label-width="90px">
        <el-form-item label="名称">
          <el-input v-model="categoryForm.name" />
        </el-form-item>
        <el-form-item label="父分类">
          <el-select v-model="categoryForm.parent" clearable filterable style="width: 100%">
            <el-option v-for="item in categories.filter((c: any) => c.kind === 'GENERAL' && c.id !== editingCategory?.id)" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="颜色">
          <el-color-picker v-model="categoryForm.color" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="categoryForm.sort_order" :min="0" :max="999" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="categoryDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveCategory">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="tagDialog" title="新增标签" width="420px">
      <el-form :model="tagForm" label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="tagForm.name" />
        </el-form-item>
        <el-form-item label="颜色">
          <el-color-picker v-model="tagForm.color" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="tagDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveTag">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, unwrap } from '@/api'
import { errorMessage } from '@/api/client'

const categories = ref<any[]>([])
const tags = ref<any[]>([])
const accounts = ref<any[]>([])
const saving = ref(false)
const categoryDialog = ref(false)
const tagDialog = ref(false)
const editingCategory = ref<any>(null)

const settingForm = reactive<any>({ payday: 10, salary_amount: null, salary_account: null })
const passwordForm = reactive({ old_password: '', new_password: '' })
const categoryForm = reactive<any>({ name: '', parent: null, color: '#409EFF', sort_order: 0 })
const tagForm = reactive<any>({ name: '', color: '#909399' })

const savingsAccounts = computed(() => accounts.value.filter((item: any) => item.type === 'SAVINGS' && item.is_active))

async function load() {
  try {
    const [settingRes, categoryRes, tagRes, accountRes] = await Promise.all([
      api.getSettings(),
      api.categories({ page_size: 300 }),
      api.tags({ page_size: 200 }),
      api.accounts({ page_size: 200 }),
    ])
    Object.assign(settingForm, {
      payday: settingRes.data.payday,
      salary_amount: settingRes.data.salary_amount === null ? null : Number(settingRes.data.salary_amount),
      salary_account: settingRes.data.salary_account,
    })
    categories.value = unwrap(categoryRes)
    tags.value = unwrap(tagRes)
    accounts.value = unwrap(accountRes)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function saveSettings() {
  saving.value = true
  try {
    await api.updateSettings(settingForm)
    ElMessage.success('设置已保存')
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

async function changePassword() {
  if (!passwordForm.old_password || !passwordForm.new_password) {
    ElMessage.warning('请填写原密码和新密码')
    return
  }
  saving.value = true
  try {
    await api.changePassword(passwordForm)
    ElMessage.success('密码已修改，请重新登录')
    passwordForm.old_password = ''
    passwordForm.new_password = ''
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

function openCategoryCreate() {
  editingCategory.value = null
  Object.assign(categoryForm, { name: '', parent: null, color: '#409EFF', sort_order: 0 })
  categoryDialog.value = true
}

function openCategoryEdit(category: any) {
  editingCategory.value = category
  Object.assign(categoryForm, {
    name: category.name,
    parent: category.parent,
    color: category.color,
    sort_order: category.sort_order,
  })
  categoryDialog.value = true
}

async function saveCategory() {
  saving.value = true
  try {
    if (editingCategory.value) await api.updateCategory(editingCategory.value.id, categoryForm)
    else await api.createCategory(categoryForm)
    ElMessage.success('已保存')
    categoryDialog.value = false
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

async function removeCategory(category: any) {
  try {
    await ElMessageBox.confirm(`确定停用分类「${category.name}」？`, '停用分类', { type: 'warning' })
    await api.deleteCategory(category.id)
    ElMessage.success('已停用')
    await load()
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(errorMessage(error))
  }
}

function openTagCreate() {
  Object.assign(tagForm, { name: '', color: '#909399' })
  tagDialog.value = true
}

async function saveTag() {
  if (!tagForm.name) {
    ElMessage.warning('请输入标签名称')
    return
  }
  saving.value = true
  try {
    await api.createTag(tagForm)
    ElMessage.success('已保存')
    tagDialog.value = false
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

async function removeTag(tag: any) {
  try {
    await ElMessageBox.confirm(`确定删除标签「${tag.name}」？`, '删除标签', { type: 'warning' })
    await api.deleteTag(tag.id)
    ElMessage.success('已删除')
    await load()
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(errorMessage(error))
  }
}

function openApiDocs() {
  window.open('/api/docs', '_blank')
}

onMounted(load)
</script>

<style scoped>
.header-actions {
  display: flex;
  gap: 10px;
}
.two-column {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
}
.form-hint {
  margin-left: 10px;
  font-size: 12px;
}
.system-info {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  font-size: 13px;
}
.system-info .muted {
  display: inline-block;
  width: 74px;
}
code {
  background: #f1f5f9;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
}
.color-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 6px;
}
@media (max-width: 1100px) {
  .two-column {
    grid-template-columns: 1fr;
  }
}
</style>
