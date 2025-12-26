import axios, { type AxiosError, type AxiosInstance } from 'axios'
import type {
  Account,
  AccountCreate,
  AccountListResponse,
  AccountType,
  AccountUpdate,
  BalanceSheetResponse,
  Company,
  CompanyCreate,
  GeneralLedgerResponse,
  IncomeStatementResponse,
  JournalResponse,
  LoginRequest,
  RegisterRequest,
  SwitchCompanyRequest,
  TokenResponse,
  Transaction,
  TransactionCreate,
  TransactionListResponse,
  TransactionUpdate,
  TrialBalanceResponse,
} from '@/types'

const API_BASE_URL = '/api/v1'

class ApiClient {
  private client: AxiosInstance
  private token: string | null = null

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      headers: {
        'Content-Type': 'application/json',
      },
    })

    // Load token from localStorage
    this.token = localStorage.getItem('token')

    // Add auth header interceptor
    this.client.interceptors.request.use((config) => {
      if (this.token) {
        config.headers.Authorization = `Bearer ${this.token}`
      }
      return config
    })

    // Add error interceptor
    this.client.interceptors.response.use(
      (response) => response,
      (error: AxiosError) => {
        if (error.response?.status === 401) {
          this.clearToken()
          window.location.href = '/login'
        }
        return Promise.reject(error)
      }
    )
  }

  setToken(token: string) {
    this.token = token
    localStorage.setItem('token', token)
  }

  clearToken() {
    this.token = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }

  getToken() {
    return this.token
  }

  // Auth endpoints
  async register(data: RegisterRequest): Promise<TokenResponse> {
    const response = await this.client.post<TokenResponse>('/auth/register', data)
    return response.data
  }

  async login(data: LoginRequest): Promise<TokenResponse> {
    const response = await this.client.post<TokenResponse>('/auth/login', data)
    return response.data
  }

  async getUserCompanies(): Promise<Company[]> {
    const response = await this.client.get<Company[]>('/auth/companies')
    return response.data
  }

  async switchCompany(data: SwitchCompanyRequest): Promise<TokenResponse> {
    const response = await this.client.post<TokenResponse>('/auth/switch-company', data)
    return response.data
  }

  async createCompany(data: CompanyCreate): Promise<Company> {
    const response = await this.client.post<Company>('/companies/', data)
    return response.data
  }

  // Account endpoints
  async createAccount(data: AccountCreate): Promise<Account> {
    const response = await this.client.post<Account>('/accounts/', data)
    return response.data
  }

  async getAccounts(params?: {
    skip?: number
    limit?: number
    account_type?: AccountType
    active_only?: boolean
  }): Promise<AccountListResponse> {
    const response = await this.client.get<AccountListResponse>('/accounts/', { params })
    return response.data
  }

  async getChartOfAccounts(): Promise<AccountListResponse> {
    const response = await this.client.get<AccountListResponse>('/accounts/chart')
    return response.data
  }

  async getAccount(id: number): Promise<Account> {
    const response = await this.client.get<Account>(`/accounts/${id}`)
    return response.data
  }

  async updateAccount(id: number, data: AccountUpdate): Promise<Account> {
    const response = await this.client.patch<Account>(`/accounts/${id}`, data)
    return response.data
  }

  async deleteAccount(id: number): Promise<void> {
    await this.client.delete(`/accounts/${id}`)
  }

  async bulkCreateAccounts(
    accounts: Array<{ code: string; name: string; account_type: string }>
  ): Promise<{ created: number; errors: string[] }> {
    const response = await this.client.post<{ created: number; errors: string[] }>('/accounts/bulk', {
      accounts,
    })
    return response.data
  }

  // Transaction endpoints
  async createTransaction(data: TransactionCreate): Promise<Transaction> {
    const response = await this.client.post<Transaction>('/transactions/', data)
    return response.data
  }

  async getTransactions(params?: {
    skip?: number
    limit?: number
    start_date?: string
    end_date?: string
    account_id?: number
    posted_only?: boolean
    draft_only?: boolean
  }): Promise<TransactionListResponse> {
    const response = await this.client.get<TransactionListResponse>('/transactions/', { params })
    return response.data
  }

  async getTransaction(id: number): Promise<Transaction> {
    const response = await this.client.get<Transaction>(`/transactions/${id}`)
    return response.data
  }

  async updateTransaction(id: number, data: TransactionUpdate): Promise<Transaction> {
    const response = await this.client.patch<Transaction>(`/transactions/${id}`, data)
    return response.data
  }

  async postTransaction(id: number): Promise<Transaction> {
    const response = await this.client.post<Transaction>(`/transactions/${id}/post`)
    return response.data
  }

  async unpostTransaction(id: number): Promise<Transaction> {
    const response = await this.client.post<Transaction>(`/transactions/${id}/unpost`)
    return response.data
  }

  async deleteTransaction(id: number): Promise<void> {
    await this.client.delete(`/transactions/${id}`)
  }

  // Report endpoints
  async getTrialBalance(asOfDate: string): Promise<TrialBalanceResponse> {
    const response = await this.client.get<TrialBalanceResponse>('/reports/trial-balance', {
      params: { as_of_date: asOfDate },
    })
    return response.data
  }

  async getBalanceSheet(asOfDate: string): Promise<BalanceSheetResponse> {
    const response = await this.client.get<BalanceSheetResponse>('/reports/balance-sheet', {
      params: { as_of_date: asOfDate },
    })
    return response.data
  }

  async getIncomeStatement(startDate: string, endDate: string): Promise<IncomeStatementResponse> {
    const response = await this.client.get<IncomeStatementResponse>('/reports/income-statement', {
      params: { start_date: startDate, end_date: endDate },
    })
    return response.data
  }

  async getGeneralLedger(
    accountId: number,
    startDate: string,
    endDate: string
  ): Promise<GeneralLedgerResponse> {
    const response = await this.client.get<GeneralLedgerResponse>(`/reports/general-ledger/${accountId}`, {
      params: { start_date: startDate, end_date: endDate },
    })
    return response.data
  }

  async getJournal(startDate: string, endDate: string): Promise<JournalResponse> {
    const response = await this.client.get<JournalResponse>('/reports/journal', {
      params: { start_date: startDate, end_date: endDate },
    })
    return response.data
  }
}

export const api = new ApiClient()
