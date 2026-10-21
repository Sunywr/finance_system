import { createRouter, createWebHistory } from 'vue-router'
import { tokenStore } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/Login.vue'),
      meta: { public: true, title: '登录' },
    },
    {
      path: '/',
      component: () => import('@/layouts/MainLayout.vue'),
      children: [
        { path: '', redirect: '/dashboard' },
        { path: 'dashboard', name: 'dashboard', component: () => import('@/views/Dashboard.vue'), meta: { title: '总览' } },
        { path: 'transactions', name: 'transactions', component: () => import('@/views/Transactions.vue'), meta: { title: '记账流水' } },
        { path: 'accounts', name: 'accounts', component: () => import('@/views/Accounts.vue'), meta: { title: '账户管理' } },
        { path: 'credit-cards', name: 'credit-cards', component: () => import('@/views/CreditCards.vue'), meta: { title: '信用卡' } },
        { path: 'debts', name: 'debts', component: () => import('@/views/Debts.vue'), meta: { title: '债务管理' } },
        { path: 'mortgages', name: 'mortgages', component: () => import('@/views/Mortgages.vue'), meta: { title: '房贷管理' } },
        { path: 'assets', name: 'assets', component: () => import('@/views/Assets.vue'), meta: { title: '资产管理' } },
        { path: 'investments', name: 'investments', component: () => import('@/views/Investments.vue'), meta: { title: '投资管理' } },
        { path: 'investments/:id', name: 'instrument-detail', component: () => import('@/views/InstrumentDetail.vue'), meta: { title: '标的详情' } },
        { path: 'intelligence', name: 'intelligence', component: () => import('@/views/Intelligence.vue'), meta: { title: '投资智能' } },
        { path: 'ai', name: 'ai', component: () => import('@/views/AI.vue'), meta: { title: 'AI 分析' } },
        { path: 'settings', name: 'settings', component: () => import('@/views/Settings.vue'), meta: { title: '设置' } },
        { path: 'history', name: 'history', component: () => import('@/views/History.vue'), meta: { title: '家庭与历史资料' } },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
  ],
})

router.beforeEach(async (to) => {
  const authenticated = Boolean(tokenStore.access)
  if (to.meta.public) {
    if (authenticated && to.name === 'login') return { name: 'dashboard' }
    return true
  }
  if (!authenticated) return { name: 'login', query: { redirect: to.fullPath } }
  const auth = useAuthStore()
  if (!auth.user) {
    try {
      await auth.fetchMe()
    } catch {
      auth.logout()
      return { name: 'login', query: { redirect: to.fullPath } }
    }
  }
  return true
})

export default router
