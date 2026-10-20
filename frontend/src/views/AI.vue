<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">AI 财务分析</h2>
        <div class="page-subtitle">配置 OpenAI 兼容服务，对账务、债务与投资状况生成建议</div>
      </div>
      <div class="header-actions">
        <el-button @click="openProviderCreate">新增服务</el-button>
        <el-button type="primary" :loading="generating" @click="openAnalysisCreate">生成分析</el-button>
      </div>
    </div>

    <div class="two-column">
      <div class="panel">
        <div class="panel-header">
          <h3 class="panel-title">AI 服务</h3>
          <span class="muted">Key 加密存储，接口只返回掩码</span>
        </div>
        <div v-if="providers.length" class="provider-list">
          <div v-for="provider in providers" :key="provider.id" class="provider-card">
            <div class="provider-head">
              <div>
                <div class="provider-name">
                  {{ provider.name }}
                  <el-tag v-if="provider.is_default" size="small" type="success">默认</el-tag>
                  <el-tag v-if="!provider.enabled" size="small" type="info">停用</el-tag>
                </div>
                <div class="muted small">{{ provider.model }} · {{ provider.base_url }}</div>
              </div>
              <el-dropdown @command="(command: string) => handleProviderCommand(command, provider)">
                <el-button text circle><el-icon><MoreFilled /></el-icon></el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="test">测试连接</el-dropdown-item>
                    <el-dropdown-item command="edit">编辑</el-dropdown-item>
                    <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
            <div class="provider-meta">
              <span>Key: {{ provider.api_key_masked || '未配置' }}</span>
              <span>温度 {{ provider.temperature }}</span>
              <span>超时 {{ provider.timeout_seconds }}s</span>
              <span v-if="testingId === provider.id" class="testing">测试中…</span>
            </div>
          </div>
        </div>
        <el-empty v-else description="尚未配置 AI 服务" :image-size="60" />
        <el-alert
          type="info"
          :closable="false"
          title="隐私说明"
          description="系统只发送聚合后的财务数据（月度收支、债务、投资盈亏等），默认不发送流水备注原文。"
          class="privacy"
        />
      </div>

      <div class="panel">
        <div class="panel-header">
          <h3 class="panel-title">生成分析</h3>
        </div>
        <el-form :model="analysisForm" label-width="100px">
          <el-form-item label="分析类型">
            <el-select v-model="analysisForm.analysis_type" style="width: 100%">
              <el-option label="月度总结" value="MONTHLY" />
              <el-option label="季度总结" value="QUARTERLY" />
              <el-option label="债务健康" value="DEBT" />
              <el-option label="投资复盘" value="INVESTMENT" />
              <el-option label="自定义" value="CUSTOM" />
            </el-select>
          </el-form-item>
          <el-form-item label="服务">
            <el-select v-model="analysisForm.provider" clearable placeholder="默认服务" style="width: 100%">
              <el-option v-for="item in providers" :key="item.id" :label="item.name" :value="item.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="区间">
            <el-date-picker
              v-model="analysisForm.period"
              type="daterange"
              value-format="YYYY-MM-DD"
              start-placeholder="开始"
              end-placeholder="结束"
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item label="额外要求">
            <el-input v-model="analysisForm.custom_prompt" type="textarea" :rows="3" placeholder="可选，例如重点分析信用卡负债" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="generating" @click="generateAnalysis">开始分析</el-button>
            <span class="muted generate-tip">同步调用，可能需要几十秒</span>
          </el-form-item>
        </el-form>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header">
        <h3 class="panel-title">分析历史</h3>
        <el-button link type="primary" @click="loadAnalyses">刷新</el-button>
      </div>
      <el-table :data="analyses" v-loading="loading" size="small" stripe>
        <el-table-column prop="created_at" label="时间" width="170" />
        <el-table-column prop="analysis_type_label" label="类型" width="110" />
        <el-table-column label="区间" width="210">
          <template #default="{ row }">{{ row.period_start }} ~ {{ row.period_end }}</template>
        </el-table-column>
        <el-table-column prop="provider_name" label="服务" width="130" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 'SUCCESS' ? 'success' : row.status === 'FAILED' ? 'danger' : 'info'">
              {{ row.status_label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="tokens" label="Token" width="90" align="right" />
        <el-table-column prop="error" label="错误" min-width="160" show-overflow-tooltip />
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="showAnalysis(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!analyses.length" description="暂无分析记录" :image-size="60" />
    </div>

    <el-dialog v-model="providerDialog" :title="editingProvider ? '编辑 AI 服务' : '新增 AI 服务'" width="620px" destroy-on-close>
      <el-form :model="providerForm" label-width="110px">
        <el-form-item>
          <el-button size="small" type="primary" plain @click="fillSenseNova">填充商汤 DeepSeek V4.1 Flash</el-button>
          <span class="muted form-tip">Base URL: token.sensenova.cn/v1，模型: deepseek-flash</span>
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="providerForm.name" />
        </el-form-item>
        <el-form-item label="Base URL">
          <el-input v-model="providerForm.base_url" placeholder="https://api.deepseek.com 或 http://localhost:11434/v1" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="providerForm.api_key" type="password" show-password placeholder="留空则不修改" />
        </el-form-item>
        <el-form-item label="模型">
          <el-input v-model="providerForm.model" placeholder="deepseek-chat / gpt-4o-mini / llama3" />
        </el-form-item>
        <el-form-item label="温度">
          <el-input-number v-model="providerForm.temperature" :min="0" :max="2" :precision="2" :step="0.1" />
        </el-form-item>
        <el-form-item label="最大输出">
          <el-input-number v-model="providerForm.max_tokens" :min="100" :max="32000" :step="100" />
        </el-form-item>
        <el-form-item label="超时秒数">
          <el-input-number v-model="providerForm.timeout_seconds" :min="5" :max="300" />
        </el-form-item>
        <el-form-item label="限流重试">
          <el-input-number v-model="providerForm.max_retries" :min="0" :max="5" />
          <span class="muted form-tip">429/5xx 自动重试次数</span>
        </el-form-item>
        <el-form-item label="重试等待秒">
          <el-input-number v-model="providerForm.retry_wait_seconds" :min="1" :max="300" />
        </el-form-item>
        <el-form-item label="额外请求体">
          <el-input
            v-model="providerForm.extra_body_text"
            type="textarea"
            :rows="4"
            placeholder='例如 {"thinking":{"type":"disabled"}}'
          />
          <div class="muted form-tip">JSON 对象，会合并到 Chat Completions 请求体；商汤 DeepSeek V4.1 Flash 建议关闭 thinking。</div>
        </el-form-item>
        <el-form-item label="默认服务">
          <el-switch v-model="providerForm.is_default" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="providerForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="providerDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveProvider">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="analysisDialog" title="分析结果" width="820px">
      <div v-if="selectedAnalysis">
        <el-descriptions :column="3" border size="small" class="analysis-desc">
          <el-descriptions-item label="类型">{{ selectedAnalysis.analysis_type_label }}</el-descriptions-item>
          <el-descriptions-item label="区间">{{ selectedAnalysis.period_start }} ~ {{ selectedAnalysis.period_end }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ selectedAnalysis.status_label }}</el-descriptions-item>
        </el-descriptions>
        <el-alert v-if="selectedAnalysis.error" type="error" :closable="false" :title="selectedAnalysis.error" class="analysis-error" />
        <MarkdownView v-if="selectedAnalysis.response_text" :content="selectedAnalysis.response_text" />
        <div v-else class="analysis-empty">暂无内容</div>
      </div>
    </el-dialog>

    <el-dialog v-model="resultDialog" title="连接测试" width="480px">
      <pre class="test-result">{{ testResult }}</pre>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import dayjs from 'dayjs'
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import MarkdownView from '@/components/MarkdownView.vue'
import { api, unwrap } from '@/api'
import { errorMessage } from '@/api/client'

const providers = ref<any[]>([])
const analyses = ref<any[]>([])
const loading = ref(false)
const saving = ref(false)
const generating = ref(false)
const testingId = ref<number | null>(null)
const providerDialog = ref(false)
const analysisDialog = ref(false)
const resultDialog = ref(false)
const editingProvider = ref<any>(null)
const selectedAnalysis = ref<any>(null)
const testResult = ref('')

const providerForm = reactive<any>({
  name: '',
  base_url: 'https://api.deepseek.com',
  api_key: '',
  model: 'deepseek-chat',
  temperature: 0.3,
  max_tokens: 2048,
  timeout_seconds: 90,
  max_retries: 2,
  retry_wait_seconds: 60,
  is_default: true,
  enabled: true,
  extra_headers: {},
  extra_body_text: '{}',
})

const analysisForm = reactive<any>({
  analysis_type: 'MONTHLY',
  provider: null,
  period: [dayjs().startOf('month').format('YYYY-MM-DD'), dayjs().format('YYYY-MM-DD')],
  custom_prompt: '',
})

async function loadProviders() {
  const response = await api.aiProviders()
  providers.value = unwrap(response)
}

async function loadAnalyses() {
  const response = await api.analyses()
  analyses.value = unwrap(response)
}

async function loadAll() {
  loading.value = true
  try {
    await Promise.all([loadProviders(), loadAnalyses()])
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    loading.value = false
  }
}

function openProviderCreate() {
  editingProvider.value = null
  Object.assign(providerForm, {
    name: '',
    base_url: 'https://api.deepseek.com',
    api_key: '',
    model: 'deepseek-chat',
    temperature: 0.3,
    max_tokens: 2048,
    timeout_seconds: 90,
    max_retries: 2,
    retry_wait_seconds: 60,
    is_default: true,
    enabled: true,
    extra_headers: {},
    extra_body_text: '{}',
  })
  providerDialog.value = true
}

function openProviderEdit(provider: any) {
  editingProvider.value = provider
  Object.assign(providerForm, {
    name: provider.name,
    base_url: provider.base_url,
    api_key: '',
    model: provider.model,
    temperature: Number(provider.temperature),
    max_tokens: provider.max_tokens,
    timeout_seconds: provider.timeout_seconds,
    max_retries: provider.max_retries ?? 2,
    retry_wait_seconds: provider.retry_wait_seconds ?? 60,
    is_default: provider.is_default,
    enabled: provider.enabled,
    extra_headers: provider.extra_headers || {},
    extra_body_text: JSON.stringify(provider.extra_body || {}, null, 2),
  })
  providerDialog.value = true
}

function fillSenseNova() {
  Object.assign(providerForm, {
    name: '商汤 DeepSeek V4.1 Flash',
    base_url: 'https://token.sensenova.cn/v1',
    model: 'deepseek-flash',
    max_tokens: 2048,
    timeout_seconds: 90,
    max_retries: 2,
    retry_wait_seconds: 60,
    extra_body_text: JSON.stringify({ thinking: { type: 'disabled' } }, null, 2),
  })
}

async function saveProvider() {
  saving.value = true
  try {
    let extraBody: any = {}
    if (providerForm.extra_body_text?.trim()) {
      try {
        extraBody = JSON.parse(providerForm.extra_body_text)
      } catch {
        ElMessage.warning('额外请求体不是合法 JSON')
        saving.value = false
        return
      }
      if (typeof extraBody !== 'object' || Array.isArray(extraBody)) {
        ElMessage.warning('额外请求体必须是 JSON 对象')
        saving.value = false
        return
      }
    }
    const payload = { ...providerForm, extra_body: extraBody }
    delete payload.extra_body_text
    if (editingProvider.value) await api.updateAiProvider(editingProvider.value.id, payload)
    else await api.createAiProvider(payload)
    ElMessage.success('已保存')
    providerDialog.value = false
    await loadProviders()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

async function testProvider(provider: any) {
  testingId.value = provider.id
  try {
    const response = await api.testAiProvider(provider.id)
    if (response.data.ok) {
      testResult.value = `连接成功\n${response.data.content}`
    } else {
      testResult.value = `连接失败\n${response.data.error}`
    }
    resultDialog.value = true
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    testingId.value = null
  }
}

async function removeProvider(provider: any) {
  try {
    await ElMessageBox.confirm(`确定删除 AI 服务「${provider.name}」？`, '删除服务', { type: 'warning' })
    await api.deleteAiProvider(provider.id)
    ElMessage.success('已删除')
    await loadProviders()
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(errorMessage(error))
  }
}

function handleProviderCommand(command: string, provider: any) {
  if (command === 'test') testProvider(provider)
  else if (command === 'edit') openProviderEdit(provider)
  else if (command === 'delete') removeProvider(provider)
}

function openAnalysisCreate() {
  analysisForm.period = [dayjs().startOf('month').format('YYYY-MM-DD'), dayjs().format('YYYY-MM-DD')]
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

async function generateAnalysis() {
  generating.value = true
  try {
    const payload: any = {
      analysis_type: analysisForm.analysis_type,
      provider: analysisForm.provider || undefined,
      custom_prompt: analysisForm.custom_prompt,
    }
    if (analysisForm.period?.length === 2) {
      payload.period_start = analysisForm.period[0]
      payload.period_end = analysisForm.period[1]
    }
    const response = await api.createAnalysis(payload)
    selectedAnalysis.value = response.data
    analysisDialog.value = true
    await loadAnalyses()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    generating.value = false
  }
}

async function showAnalysis(row: any) {
  try {
    const response = await api.analysis(row.id)
    selectedAnalysis.value = response.data
    analysisDialog.value = true
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

onMounted(loadAll)
</script>

<style scoped>
.header-actions {
  display: flex;
  gap: 10px;
}
.two-column {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 18px;
}
.provider-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.provider-card {
  border: 1px solid #eef2f7;
  border-radius: 10px;
  padding: 12px 14px;
}
.provider-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}
.provider-name {
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 6px;
}
.provider-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  color: #6b7280;
  font-size: 12px;
  margin-top: 8px;
}
.small {
  font-size: 12px;
}
.testing {
  color: #b45309;
}
.privacy {
  margin-top: 16px;
}
.generate-tip {
  margin-left: 12px;
  font-size: 12px;
}
.form-tip {
  margin-left: 10px;
  font-size: 12px;
  line-height: 1.5;
}
.analysis-desc {
  margin-bottom: 14px;
}
.analysis-error {
  margin-bottom: 14px;
}
.analysis-empty {
  color: #9ca3af;
  font-size: 14px;
  padding: 12px 2px;
}
.test-result {
  white-space: pre-wrap;
  font-size: 13px;
  background: #f8fafc;
  padding: 12px;
  border-radius: 8px;
}
@media (max-width: 1100px) {
  .two-column {
    grid-template-columns: 1fr;
  }
}
</style>
