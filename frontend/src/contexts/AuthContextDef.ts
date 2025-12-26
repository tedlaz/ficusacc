import { createContext } from 'react'
import type { Company, LoginRequest, RegisterRequest } from '@/types'

interface AuthUser {
  id: number
  companyId: number | null
  companyName: string | null
}

export interface AuthContextType {
  user: AuthUser | null
  companies: Company[]
  isLoading: boolean
  isAuthenticated: boolean
  login: (data: LoginRequest) => Promise<void>
  register: (data: RegisterRequest) => Promise<void>
  logout: () => void
  switchCompany: (companyId: number) => Promise<void>
  refreshCompanies: () => Promise<void>
}

export const AuthContext = createContext<AuthContextType | null>(null)
