import { client } from './client'

export const api = {
  // auth & settings
  login: (username: string, password: string) =>
    client.post('/auth/token', { username, password }),
  me: () => client.get('/auth/me'),
  changePassword: (data: any) => client.post('/auth/change-password', data),
  getSettings: () => client.get('/settings'),
  updateSettings: (data: any) => client.patch('/settings', data),
  meta: () => client.get('/meta/enums'),
  health: () => client.get('/health'),

  // accounts
  accounts: (params?: any) => client.get('/accounts/', { params }),
  account: (id: number) => client.get(`/accounts/${id}/`),
  createAccount: (data: any) => client.post('/accounts/', data),
  updateAccount: (id: number, data: any) => client.patch(`/accounts/${id}/`, data),
  deleteAccount: (id: number) => client.delete(`/accounts/${id}/`),
  accountBalance: (id: number, params?: any) => client.get(`/accounts/${id}/balance/`, { params }),
  pfProfile: (id: number) => client.get(`/accounts/${id}/pf-profile/`),
  savePfProfile: (id: number, data: any) => client.put(`/accounts/${id}/pf-profile/`, data),
  transfers: (params?: any) => client.get('/transfers/', { params }),
  createTransfer: (data: any) => client.post('/transfers/', data),

  // categories & tags
  categories: (params?: any) => client.get('/categories/', { params }),
  categoryTree: () => client.get('/categories/tree/'),
  createCategory: (data: any) => client.post('/categories/', data),
  updateCategory: (id: number, data: any) => client.patch(`/categories/${id}/`, data),
  deleteCategory: (id: number) => client.delete(`/categories/${id}/`),
  tags: (params?: any) => client.get('/tags/', { params }),
  createTag: (data: any) => client.post('/tags/', data),
  deleteTag: (id: number) => client.delete(`/tags/${id}/`),

  // transactions
  transactions: (params?: any) => client.get('/transactions/', { params }),
  transaction: (id: number) => client.get(`/transactions/${id}/`),
  createTransaction: (data: any) => client.post('/transactions/', data),
  updateTransaction: (id: number, data: any) => client.patch(`/transactions/${id}/`, data),
  deleteTransaction: (id: number) => client.delete(`/transactions/${id}/`),
  voidTransaction: (id: number, reason = '') => client.post(`/transactions/${id}/void/`, { reason }),
  refundTransaction: (id: number, data: any) => client.post(`/transactions/${id}/refund/`, data),
  previewInstallment: (data: any) => client.post('/transactions/installment-preview/', data),

  // cards, bills, debts
  cards: (params?: any) => client.get('/credit-cards/', { params }),
  createCard: (data: any) => client.post('/credit-cards/', data),
  updateCard: (id: number, data: any) => client.patch(`/credit-cards/${id}/`, data),
  deleteCard: (id: number) => client.delete(`/credit-cards/${id}/`),
  cardCurrent: (id: number) => client.get(`/credit-cards/${id}/current/`),
  cardBills: (id: number) => client.get(`/credit-cards/${id}/bills/`),
  cardInstallments: (id: number) => client.get(`/credit-cards/${id}/installments/`),
  generateBills: () => client.post('/credit-cards/generate/'),
  bills: (params?: any) => client.get('/bills/', { params }),
  payBill: (id: number, data: any) => client.post(`/bills/${id}/pay/`, data),
  debts: (params?: any) => client.get('/debts/', { params }),
  debtSummary: () => client.get('/debts/summary/'),
  payDebt: (id: number, data: any) => client.post(`/debts/${id}/pay/`, data),
  cancelDebt: (id: number) => client.post(`/debts/${id}/cancel/`),
  generateDebts: () => client.post('/debts/generate/'),
  recurringDebts: (params?: any) => client.get('/recurring-debts/', { params }),
  createRecurringDebt: (data: any) => client.post('/recurring-debts/', data),
  updateRecurringDebt: (id: number, data: any) => client.patch(`/recurring-debts/${id}/`, data),
  deleteRecurringDebt: (id: number) => client.delete(`/recurring-debts/${id}/`),
  debtPayments: (params?: any) => client.get('/debt-payments/', { params }),

  // mortgages
  loans: () => client.get('/loans/'),
  createLoan: (data: any) => client.post('/loans/', data),
  updateLoan: (id: number, data: any) => client.patch(`/loans/${id}/`, data),
  deleteLoan: (id: number) => client.delete(`/loans/${id}/`),
  loanSchedule: (id: number) => client.get(`/loans/${id}/schedule/`),
  loanSummary: (id: number) => client.get(`/loans/${id}/summary/`),
  offsetPlan: (id: number) => client.get(`/loans/${id}/offset-plan/`),
  saveOffsetPlan: (id: number, data: any) => client.put(`/loans/${id}/offset-plan/`, data),
  offsetSimulation: (id: number, data?: any) =>
    client.post(`/loans/${id}/offset-simulation/`, data || {}),

  // assets
  assets: (params?: any) => client.get('/assets/', { params }),
  createAsset: (data: any) => client.post('/assets/', data),
  updateAsset: (id: number, data: any) => client.patch(`/assets/${id}/`, data),
  deleteAsset: (id: number) => client.delete(`/assets/${id}/`),
  assetTransactions: (id: number) => client.get(`/assets/${id}/transactions/`),
  assetValuations: (id: number) => client.get(`/assets/${id}/valuations/`),
  createValuation: (id: number, data: any) => client.post(`/assets/${id}/valuations/`, data),

  // investments
  instruments: (params?: any) => client.get('/instruments/', { params }),
  instrument: (id: number) => client.get(`/instruments/${id}/`),
  createInstrument: (data: any) => client.post('/instruments/', data),
  updateInstrument: (id: number, data: any) => client.patch(`/instruments/${id}/`, data),
  deleteInstrument: (id: number) => client.delete(`/instruments/${id}/`),
  instrumentQuote: (id: number) => client.get(`/instruments/${id}/quote/`),
  instrumentBars: (id: number, params?: any) => client.get(`/instruments/${id}/bars/`, { params }),
  instrumentIndicators: (id: number, params?: any) =>
    client.get(`/instruments/${id}/indicators/`, { params }),
  syncInstrument: (id: number) => client.post(`/instruments/${id}/sync/`),
  syncMarket: () => client.post('/market/sync'),
  trades: (params?: any) => client.get('/trades/', { params }),
  createTrade: (data: any) => client.post('/trades/', data),
  holdings: (params?: any) => client.get('/holdings', { params }),
  watchlist: () => client.get('/watchlist/'),
  createWatch: (data: any) => client.post('/watchlist/', data),
  deleteWatch: (id: number) => client.delete(`/watchlist/${id}/`),
  instrumentReports: (id: number) => client.get(`/instruments/${id}/reports/`),
  syncInstrumentReports: (id: number) => client.post(`/instruments/${id}/sync-reports/`),
  instrumentSignals: (id: number) => client.get(`/instruments/${id}/signals/`),
  analyzeInstrumentSignals: (id: number) => client.post(`/instruments/${id}/signals/`),
  gridPlan: (id: number) => client.get(`/instruments/${id}/grid-plan/`),
  marketRegime: () => client.get('/market/regime'),
  refreshMarketRegime: () => client.post('/market/regime'),
  screenerPresets: () => client.get('/screener/presets/'),
  createScreenerPreset: (data: any) => client.post('/screener/presets/', data),
  screenerRuns: () => client.get('/screener/runs/'),
  runScreener: (data: any) => client.post('/screener/runs/', data),
  signals: (params?: any) => client.get('/signals/', { params }),
  ipo: () => client.get('/ipo'),
  syncIpo: () => client.post('/ipo'),

  // ai
  aiProviders: () => client.get('/ai/providers/'),
  createAiProvider: (data: any) => client.post('/ai/providers/', data),
  updateAiProvider: (id: number, data: any) => client.patch(`/ai/providers/${id}/`, data),
  deleteAiProvider: (id: number) => client.delete(`/ai/providers/${id}/`),
  testAiProvider: (id: number) => client.post(`/ai/providers/${id}/test/`, {}, { timeout: 240000 }),
  analyses: () => client.get('/ai/analyses/'),
  analysis: (id: number) => client.get(`/ai/analyses/${id}/`),
  createAnalysis: (data: any) => client.post('/ai/analyses/', data, { timeout: 240000 }),

  // dashboard
  dashboard: (params?: any) => client.get('/dashboard/overview', { params }),
  cashflow: (params?: any) => client.get('/dashboard/cashflow', { params }),
}

export function unwrap<T = any>(response: any): T {
  return (response?.data?.results ?? response?.data) as T
}
