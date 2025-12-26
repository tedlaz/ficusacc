import { useState, useEffect, useCallback, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Company, TokenResponse } from '@/types'
import { AuthContext } from './AuthContextDef'

interface AuthUser {
  id: number
  is_superuser: boolean
  companyId: number | null
  companyName: string | null
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [user, setUser] = useState<AuthUser | null>(() => {
    // Initialize from localStorage synchronously
    const token = localStorage.getItem('token')
    const storedUser = localStorage.getItem('user')
    if (token && storedUser) {
      try {
        return JSON.parse(storedUser) as AuthUser
      } catch {
        return null
      }
    }
    return null
  })
  const [companies, setCompanies] = useState<Company[]>([])
  const [isLoading, setIsLoading] = useState(true)

  const setAuthFromToken = useCallback((token: TokenResponse) => {
    api.setToken(token.access_token)
    const authUser: AuthUser = {
      id: token.user_id,
      is_superuser: token.is_superuser,
      companyId: token.company_id,
      companyName: token.company_name,
    }
    setUser(authUser)
    localStorage.setItem('user', JSON.stringify(authUser))
  }, [])

  const refreshCompanies = useCallback(async () => {
    if (api.getToken()) {
      try {
        const userCompanies = await api.getUserCompanies()
        setCompanies(userCompanies)
      } catch {
        // Ignore errors
      }
    }
  }, [])

  useEffect(() => {
    // Load companies on mount if user exists
    let isMounted = true

    const loadCompanies = async () => {
      if (user && api.getToken()) {
        try {
          const userCompanies = await api.getUserCompanies()
          if (isMounted) {
            setCompanies(userCompanies)
          }
        } catch {
          // Ignore errors
        }
      }
      if (isMounted) {
        setIsLoading(false)
      }
    }

    loadCompanies()

    return () => {
      isMounted = false
    }
  }, [user])

  const login = async (data: { email: string; password: string; company_id?: number | null }) => {
    const token = await api.login(data)
    setAuthFromToken(token)
    await refreshCompanies()
  }

  const register = async (data: {
    email: string
    password: string
    full_name: string
    company_name?: string | null
  }) => {
    const token = await api.register(data)
    setAuthFromToken(token)
    await refreshCompanies()
  }

  const logout = () => {
    api.clearToken()
    setUser(null)
    setCompanies([])
  }

  const switchCompany = async (companyId: number) => {
    const token = await api.switchCompany({ company_id: companyId })
    setAuthFromToken(token)
    // Invalidate all queries to refresh data for the new company
    await queryClient.invalidateQueries()
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        companies,
        isLoading,
        isAuthenticated: !!user,
        login,
        register,
        logout,
        switchCompany,
        refreshCompanies,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}
