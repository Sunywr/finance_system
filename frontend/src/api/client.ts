import axios from 'axios'
import { ElMessage } from 'element-plus'

const ACCESS_KEY = 'finance_access'
const REFRESH_KEY = 'finance_refresh'

export const tokenStore = {
  get access() {
    return localStorage.getItem(ACCESS_KEY) || ''
  },
  get refresh() {
    return localStorage.getItem(REFRESH_KEY) || ''
  },
  set(access: string, refresh?: string) {
    localStorage.setItem(ACCESS_KEY, access)
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh)
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')

export const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 90000,
})

let refreshPromise: Promise<string> | null = null

client.interceptors.request.use((config) => {
  const token = tokenStore.access
  if (token) {
    config.headers = (config.headers || {}) as any
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config || {}
    const status = error.response?.status
    if (status === 401 && !original._retry) {
      original._retry = true
      if (tokenStore.refresh) {
        try {
          refreshPromise =
            refreshPromise ||
            axios
              .post(`${API_BASE_URL}/auth/token/refresh`, { refresh: tokenStore.refresh })
              .then((response) => {
                tokenStore.set(response.data.access, response.data.refresh)
                return response.data.access
              })
              .finally(() => {
                refreshPromise = null
              })
          const access = await refreshPromise
          original.headers = original.headers || {}
          original.headers.Authorization = `Bearer ${access}`
          return client(original)
        } catch {
          tokenStore.clear()
        }
      }
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  },
)

export function errorMessage(error: any): string {
  const data = error?.response?.data
  if (!data) return error?.message || '请求失败'
  if (typeof data === 'string') return data
  if (data.detail) return data.detail
  if (data.errors) {
    const errors = data.errors
    if (typeof errors === 'string') return errors
    if (Array.isArray(errors)) return errors.join('；')
    const first = Object.entries(errors)[0]
    if (first) return `${first[0]}: ${Array.isArray(first[1]) ? first[1].join('；') : first[1]}`
  }
  const first = Object.entries(data)[0]
  if (first) return `${first[0]}: ${Array.isArray(first[1]) ? first[1].join('；') : first[1]}`
  return '请求失败'
}

export function toastError(error: any) {
  ElMessage.error(errorMessage(error))
}

export function money(value: any): string {
  if (value === null || value === undefined || value === '') return '0.00'
  const number = Number(value)
  if (Number.isNaN(number)) return String(value)
  return number.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function percent(value: any): string {
  if (value === null || value === undefined || value === '') return '-'
  const number = Number(value)
  if (Number.isNaN(number)) return '-'
  return `${number.toFixed(2)}%`
}
