<template>
  <div class="login-page">
    <div class="login-card">
      <div class="hero">
        <div class="logo">F</div>
        <h1>财务系统</h1>
        <p>记账、债务、房贷、投资与现金流总览</p>
      </div>
      <el-form :model="form" label-position="top" @submit.prevent="submit">
        <el-form-item label="用户名">
          <el-input v-model="form.username" size="large" placeholder="admin" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            size="large"
            placeholder="请输入密码"
            autocomplete="current-password"
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-button type="primary" size="large" class="login-button" :loading="loading" @click="submit">
          登录
        </el-button>
      </el-form>
      <p class="hint">首次使用请先执行 seed_system_data 初始化账号，再登录修改密码。</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { errorMessage } from '@/api/client'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const loading = ref(false)
const form = reactive({ username: 'admin', password: '' })

async function submit() {
  if (!form.username || !form.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/dashboard'
    router.push(redirect)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: radial-gradient(circle at 20% 10%, #dbeafe 0, #f8fafc 42%, #eef2ff 100%);
  padding: 24px;
}
.login-card {
  width: 420px;
  max-width: 100%;
  background: #fff;
  border-radius: 18px;
  padding: 36px 36px 28px;
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.14);
}
.hero {
  text-align: center;
  margin-bottom: 26px;
}
.logo {
  width: 54px;
  height: 54px;
  margin: 0 auto 12px;
  border-radius: 16px;
  background: linear-gradient(135deg, #2563eb, #22d3ee);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  font-weight: 800;
}
h1 {
  margin: 0;
  font-size: 24px;
}
.hero p {
  color: #6b7280;
  margin: 8px 0 0;
  font-size: 13px;
}
.login-button {
  width: 100%;
  margin-top: 6px;
}
.hint {
  color: #9ca3af;
  font-size: 12px;
  margin-top: 18px;
  line-height: 1.6;
}
</style>
