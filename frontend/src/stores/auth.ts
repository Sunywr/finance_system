import { defineStore } from 'pinia'
import { api } from '@/api'
import { tokenStore } from '@/api/client'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as any,
    loading: false,
  }),
  getters: {
    isAuthenticated: () => Boolean(tokenStore.access),
    displayName: (state) => state.user?.display_name || state.user?.username || '用户',
  },
  actions: {
    async login(username: string, password: string) {
      this.loading = true
      try {
        const response = await api.login(username, password)
        tokenStore.set(response.data.access, response.data.refresh)
        await this.fetchMe()
      } finally {
        this.loading = false
      }
    },
    async fetchMe() {
      if (!tokenStore.access) return null
      const response = await api.me()
      this.user = response.data
      return this.user
    },
    logout() {
      tokenStore.clear()
      this.user = null
    },
  },
})
