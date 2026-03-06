import axios from 'axios'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const api = axios.create({
  baseURL: `${API_BASE}/api/v1`,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

// Attach token from localStorage if present
api.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token')
    if (token) config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Redirect to login on 401
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401 && typeof window !== 'undefined') {
      localStorage.removeItem('access_token')
      localStorage.removeItem('user')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default api

// Typed API methods
export const authApi = {
  login: (username: string, password: string) =>
    api.post('/auth/login', { username, password }),
  logout: () => api.post('/auth/logout'),
  me: () => api.get('/auth/me'),
}

export const jobsApi = {
  list: (params?: any) => api.get('/jobs/', { params }),
  create: (data: any) => api.post('/jobs/', data),
  get: (id: number) => api.get(`/jobs/${id}`),
  update: (id: number, data: any) => api.put(`/jobs/${id}`, data),
  advanceStage: (id: number, data: any) => api.post(`/jobs/${id}/advance-stage`, data),
  stats: () => api.get('/jobs/stats'),
  getBarcode: (id: number) => api.get(`/jobs/${id}/barcode-image`),
  getByBarcode: (barcode: string) => api.get(`/jobs/barcode/${barcode}`),
}

export const scaleApi = {
  readWeight: (expected?: number) => api.post('/scale/read-weight', null, { params: { expected_weight: expected || 10 } }),
  status: () => api.get('/scale/status'),
  logWeight: (data: any) => api.post('/scale/log-weight', null, { params: data }),
}

export const metalApi = {
  stock: () => api.get('/metal/stock'),
  ledger: (params?: any) => api.get('/metal/ledger', { params }),
  issue: (data: any) => api.post('/metal/issue', data),
  return: (data: any) => api.post('/metal/return', data),
  reconciliation: () => api.get('/metal/reconciliation'),
}

export const karigarApi = {
  list: () => api.get('/karigar/'),
  create: (data: any) => api.post('/karigar/', data),
  allocate: (data: any) => api.post('/karigar/allocate-work', data),
  performance: () => api.get('/karigar/performance'),
}

export const scrapApi = {
  list: (status?: string) => api.get('/scrap/', { params: { status } }),
  collect: (data: any) => api.post('/scrap/collect', data),
  report: () => api.get('/scrap/scrap-report'),
}

export const refineryApi = {
  list: () => api.get('/refinery/'),
  dispatch: (data: any) => api.post('/refinery/dispatch', data),
  settle: (data: any) => api.post('/refinery/settle', data),
}

export const inventoryApi = {
  list: (params?: any) => api.get('/inventory/', { params }),
  create: (data: any) => api.post('/inventory/', data),
  adjust: (data: any) => api.post('/inventory/adjust', data),
}

export const costingApi = {
  getJob: (jobId: number) => api.get(`/costing/job/${jobId}`),
  calculate: (data: any) => api.post('/costing/calculate', data),
  profitability: () => api.get('/costing/profitability'),
}

export const reportsApi = {
  dashboard: () => api.get('/reports/dashboard'),
  reconciliation: () => api.get('/reports/reconciliation'),
  wages: () => api.get('/reports/wages'),
  auditTrail: (params?: any) => api.get('/reports/audit-trail', { params }),
}

export const productionApi = {
  scan: (data: any) => api.post('/production/scan', data),
  stageLogs: (jobId: number) => api.get(`/production/stage-update/${jobId}`),
}
