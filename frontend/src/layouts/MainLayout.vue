<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <div class="brand">
        <div class="brand-mark">F</div>
        <div>
          <div class="brand-name">财务系统</div>
          <div class="brand-sub">Personal Finance</div>
        </div>
      </div>
      <el-menu :default-active="activePath" router class="menu">
        <el-menu-item index="/dashboard"><el-icon><DataBoard /></el-icon><span>总览</span></el-menu-item>
        <el-menu-item index="/transactions"><el-icon><Tickets /></el-icon><span>记账流水</span></el-menu-item>
        <el-menu-item index="/accounts"><el-icon><Wallet /></el-icon><span>账户管理</span></el-menu-item>
        <el-menu-item index="/credit-cards"><el-icon><CreditCard /></el-icon><span>信用卡</span></el-menu-item>
        <el-menu-item index="/debts"><el-icon><Money /></el-icon><span>债务管理</span></el-menu-item>
        <el-menu-item index="/mortgages"><el-icon><House /></el-icon><span>房贷管理</span></el-menu-item>
        <el-menu-item index="/assets"><el-icon><Box /></el-icon><span>资产管理</span></el-menu-item>
        <el-menu-item index="/investments"><el-icon><TrendCharts /></el-icon><span>投资管理</span></el-menu-item>
        <el-menu-item index="/intelligence"><el-icon><Aim /></el-icon><span>投资智能</span></el-menu-item>
        <el-menu-item index="/ai"><el-icon><MagicStick /></el-icon><span>AI 分析</span></el-menu-item>
        <el-menu-item index="/settings"><el-icon><Setting /></el-icon><span>设置</span></el-menu-item>
      </el-menu>
    </el-aside>
    <el-container class="content">
      <el-header class="header">
        <div>
          <span class="page-title">{{ route.meta.title || '财务系统' }}</span>
        </div>
        <div class="header-right">
          <el-dropdown @command="handleCommand">
            <span class="user">
              <el-avatar :size="28">{{ auth.displayName.slice(0, 1) }}</el-avatar>
              <span>{{ auth.displayName }}</span>
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="settings">设置</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      <el-main ref="mainRef" class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ComponentPublicInstance } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const activePath = computed(() => route.path)
const mainRef = ref<ComponentPublicInstance | null>(null)

// 切页时把右侧内容区滚回顶部（滚动容器已由 window 改为 .main）
watch(
  () => route.fullPath,
  () => {
    const el = mainRef.value?.$el as HTMLElement | undefined
    if (el) el.scrollTop = 0
  },
)

function handleCommand(command: string) {
  if (command === 'logout') {
    auth.logout()
    router.push('/login')
  } else if (command === 'settings') {
    router.push('/settings')
  }
}
</script>

<style scoped>
.layout {
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
}
.content {
  height: 100%;
  overflow: hidden;
}
.aside {
  height: 100%;
  background: #111827;
  color: #e5e7eb;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px 18px 16px;
  color: #fff;
}
.brand-mark {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: linear-gradient(135deg, #3b82f6, #22d3ee);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  font-size: 20px;
}
.brand-name {
  font-weight: 700;
  letter-spacing: 0.02em;
}
.brand-sub {
  font-size: 11px;
  color: #9ca3af;
  margin-top: 2px;
}
.menu {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: #374151 transparent;
  border-right: none;
  background: transparent;
  --el-menu-text-color: #cbd5e1;
  --el-menu-hover-bg-color: #1f2937;
  --el-menu-active-color: #fff;
  --el-menu-bg-color: transparent;
}
.menu :deep(.el-menu-item.is-active) {
  background: #1d4ed8;
  border-radius: 8px;
  margin: 2px 10px;
}
.menu :deep(.el-menu-item) {
  margin: 2px 10px;
  border-radius: 8px;
  height: 44px;
}
.header {
  height: 64px;
  flex-shrink: 0;
  background: #fff;
  border-bottom: 1px solid #eef2f7;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}
.user {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  color: #374151;
  outline: none;
}
.main {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0;
  background: var(--finance-bg);
}
@media (max-width: 900px) {
  .aside {
    width: 72px !important;
  }
  .brand-name,
  .brand-sub,
  .menu span {
    display: none;
  }
  .brand {
    justify-content: center;
    padding: 14px 0;
  }
  .menu :deep(.el-menu-item) {
    justify-content: center;
    margin: 4px;
  }
}
</style>
