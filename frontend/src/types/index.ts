// Enums matching backend (using const objects for compatibility)
export const AccountType = {
  ASSET: 'asset',
  LIABILITY: 'liability',
  EQUITY: 'equity',
  REVENUE: 'revenue',
  EXPENSE: 'expense',
} as const

export type AccountType = (typeof AccountType)[keyof typeof AccountType]

export const UserRole = {
  ADMIN: 'admin',
  ACCOUNTANT: 'accountant',
  VIEWER: 'viewer',
} as const

export type UserRole = (typeof UserRole)[keyof typeof UserRole]

// Auth types
export interface LoginRequest {
  email: string
  password: string
  company_id?: number | null
}

export interface RegisterRequest {
  email: string
  password: string
  full_name: string
  company_name?: string | null
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user_id: number
  is_superuser: boolean
  company_id: number | null
  company_name: string | null
}

export interface SwitchCompanyRequest {
  company_id: number
}

// User types
export interface User {
  id: number
  email: string
  full_name: string
  is_active: boolean
  created_at: string
  updated_at: string
}

// Company types
export interface Company {
  id: number
  name: string
  code: string
  fiscal_year_start_month: number
  currency: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface CompanyCreate {
  name: string
  code: string
  fiscal_year_start_month?: number
  currency?: string
}

export interface CompanyUpdate {
  name?: string
  code?: string
  fiscal_year_start_month?: number
  currency?: string
  is_active?: boolean
}

// Account types
export interface Account {
  id: number
  company_id: number
  code: string
  name: string
  account_type: AccountType
  parent_id: number | null
  is_active: boolean
  description: string | null
  created_at: string
  updated_at: string
}

export interface AccountCreate {
  code: string
  name: string
  account_type: AccountType
  parent_id?: number | null
  description?: string | null
}

export interface AccountUpdate {
  code?: string
  name?: string
  account_type?: AccountType
  parent_id?: number | null
  is_active?: boolean
  description?: string | null
}

export interface AccountListResponse {
  items: Account[]
  total: number
}

// Transaction types
export interface TransactionLine {
  id: number
  transaction_id: number
  account_id: number
  amount: string // Decimal as string
  description: string | null
  line_order: number
}

export interface TransactionLineCreate {
  account_id: number
  amount: string
  description?: string | null
}

export interface Transaction {
  id: number
  company_id: number
  transaction_date: string
  description: string
  reference: string | null
  is_posted: boolean
  created_by_id: number
  created_at: string
  updated_at: string
  lines: TransactionLine[]
}

export interface TransactionCreate {
  transaction_date: string
  description: string
  reference?: string | null
  lines: TransactionLineCreate[]
  is_posted?: boolean
}

export interface TransactionUpdate {
  transaction_date?: string
  description?: string
  reference?: string | null
  lines?: TransactionLineCreate[]
}

export interface TransactionListResponse {
  items: Transaction[]
  total: number
}

// Report types
export interface AccountBalance {
  account: Account
  debit_total: string
  credit_total: string
  balance: string
}

export interface TrialBalanceResponse {
  as_of_date: string
  accounts: AccountBalance[]
  total_debits: string
  total_credits: string
}

export interface BalanceSheetResponse {
  as_of_date: string
  assets: AccountBalance[]
  liabilities: AccountBalance[]
  equity: AccountBalance[]
  total_assets: string
  total_liabilities: string
  total_equity: string
}

export interface IncomeStatementResponse {
  start_date: string
  end_date: string
  revenues: AccountBalance[]
  expenses: AccountBalance[]
  total_revenue: string
  total_expenses: string
  net_income: string
}

export interface LedgerEntry {
  date: string
  description: string
  reference: string | null
  debit: string
  credit: string
  balance: string
}

export interface GeneralLedgerResponse {
  account: Account
  start_date: string
  end_date: string
  opening_balance: string
  entries: LedgerEntry[]
  closing_balance: string
}

export interface JournalDebitCredit {
  account: Account
  amount: string
  description: string | null
}

export interface JournalEntry {
  transaction: Transaction
  debits: JournalDebitCredit[]
  credits: JournalDebitCredit[]
}

export interface JournalResponse {
  start_date: string
  end_date: string
  entries: JournalEntry[]
}

// API Error
export interface ApiError {
  detail: string
}
