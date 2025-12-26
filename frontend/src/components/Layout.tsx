import { Link, useLocation, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard,
  BookOpen,
  Receipt,
  FileText,
  LogOut,
  Building2,
  ChevronDown,
  Menu,
  X,
  Plus,
  HardDrive,
} from 'lucide-react'
import { useState } from 'react'
import { useAuth } from '@/contexts'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { api } from '@/lib/api'
import { Modal, Input, Button } from '@/components/ui'
import toast from 'react-hot-toast'

interface LayoutProps {
  children: ReactNode
}

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'Chart of Accounts', href: '/accounts', icon: BookOpen },
  { name: 'Transactions', href: '/transactions', icon: Receipt },
  { name: 'Reports', href: '/reports', icon: FileText },
  { name: 'Backup', href: '/backup', icon: HardDrive },
]

export function Layout({ children }: LayoutProps) {
  const { user, companies, logout, switchCompany, refreshCompanies } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [showCompanyDropdown, setShowCompanyDropdown] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [showCreateCompanyModal, setShowCreateCompanyModal] = useState(false)
  const [isCreatingCompany, setIsCreatingCompany] = useState(false)
  const [newCompanyName, setNewCompanyName] = useState('')
  const [newCompanyCode, setNewCompanyCode] = useState('')

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const handleSwitchCompany = async (companyId: number) => {
    try {
      await switchCompany(companyId)
      setShowCompanyDropdown(false)
    } catch (error) {
      console.error('Failed to switch company:', error)
    }
  }

  const closeMobileMenu = () => {
    setMobileMenuOpen(false)
  }

  const handleCreateCompany = async () => {
    if (!newCompanyName.trim() || !newCompanyCode.trim()) {
      toast.error('Συμπληρώστε όνομα και κωδικό εταιρείας')
      return
    }

    setIsCreatingCompany(true)
    try {
      const company = await api.createCompany({
        name: newCompanyName.trim(),
        code: newCompanyCode.trim().toUpperCase(),
      })
      toast.success('Η εταιρεία δημιουργήθηκε επιτυχώς')
      setShowCreateCompanyModal(false)
      setNewCompanyName('')
      setNewCompanyCode('')
      // Refresh companies list and switch to new company
      await refreshCompanies()
      await switchCompany(company.id)
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } }
      toast.error(err.response?.data?.detail || 'Αποτυχία δημιουργίας εταιρείας')
    } finally {
      setIsCreatingCompany(false)
    }
  }

  return (
    <div className='min-h-screen bg-gray-50'>
      {/* Mobile header */}
      <header className='lg:hidden fixed top-0 left-0 right-0 z-40 bg-white border-b border-gray-200'>
        <div className='flex items-center justify-between h-14 px-4'>
          <div className='flex items-center'>
            <BookOpen className='h-6 w-6 text-blue-600' />
            <span className='ml-2 text-lg font-bold text-gray-900'>HomeAcct</span>
          </div>
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className='p-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg'
          >
            {mobileMenuOpen ? <X className='h-6 w-6' /> : <Menu className='h-6 w-6' />}
          </button>
        </div>
      </header>

      {/* Mobile menu overlay */}
      {mobileMenuOpen && (
        <div className='lg:hidden fixed inset-0 z-30 bg-black/50' onClick={closeMobileMenu} />
      )}

      {/* Sidebar - desktop always visible, mobile as slide-out */}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 w-64 bg-white border-r border-gray-200 transform transition-transform duration-300 ease-in-out',
          'lg:translate-x-0',
          mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        <div className='flex flex-col h-full'>
          {/* Logo */}
          <div className='flex items-center h-16 px-6 border-b border-gray-200'>
            <BookOpen className='h-8 w-8 text-blue-600' />
            <span className='ml-2 text-xl font-bold text-gray-900'>HomeAcct</span>
          </div>

          {/* Company Selector */}
          <div className='px-4 py-3 border-b border-gray-200'>
            <div className='relative'>
              <button
                onClick={() => setShowCompanyDropdown(!showCompanyDropdown)}
                className='flex items-center justify-between w-full px-3 py-2 text-sm bg-gray-50 rounded-lg hover:bg-gray-100'
              >
                <div className='flex items-center min-w-0'>
                  <Building2 className='h-4 w-4 text-gray-500 mr-2 shrink-0' />
                  <span className='font-medium text-gray-900 truncate'>
                    {user?.companyName || 'No Company'}
                  </span>
                </div>
                <ChevronDown className='h-4 w-4 text-gray-500 shrink-0' />
              </button>

              {showCompanyDropdown && (
                <div className='absolute z-10 w-full mt-1 bg-white rounded-lg shadow-lg border border-gray-200'>
                  {companies.map((company) => (
                    <button
                      key={company.id}
                      onClick={() => handleSwitchCompany(company.id)}
                      className={cn(
                        'block w-full px-3 py-2 text-left text-sm hover:bg-gray-50',
                        company.id === user?.companyId && 'bg-blue-50 text-blue-700'
                      )}
                    >
                      {company.name}
                    </button>
                  ))}
                  <div className='border-t border-gray-200'>
                    <button
                      onClick={() => {
                        setShowCompanyDropdown(false)
                        setShowCreateCompanyModal(true)
                      }}
                      className='flex items-center w-full px-3 py-2 text-left text-sm text-blue-600 hover:bg-blue-50'
                    >
                      <Plus className='h-4 w-4 mr-2' />
                      Νέα Εταιρεία
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Navigation */}
          <nav className='flex-1 px-4 py-4 space-y-1 overflow-y-auto'>
            {navigation.map((item) => {
              const isActive = location.pathname === item.href
              return (
                <Link
                  key={item.name}
                  to={item.href}
                  onClick={closeMobileMenu}
                  className={cn(
                    'flex items-center px-3 py-2 text-sm font-medium rounded-lg transition-colors',
                    isActive ? 'bg-blue-50 text-blue-700' : 'text-gray-700 hover:bg-gray-100'
                  )}
                >
                  <item.icon className='h-5 w-5 mr-3 shrink-0' />
                  {item.name}
                </Link>
              )
            })}
          </nav>

          {/* User section */}
          <div className='p-4 border-t border-gray-200'>
            <button
              onClick={handleLogout}
              className='flex items-center w-full px-3 py-2 text-sm font-medium text-gray-700 rounded-lg hover:bg-gray-100'
            >
              <LogOut className='h-5 w-5 mr-3' />
              Logout
            </button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className='lg:ml-64 min-h-screen pt-14 lg:pt-0'>
        <div className='p-4 sm:p-6 lg:p-8'>{children}</div>
      </main>

      {/* Create Company Modal */}
      <Modal
        isOpen={showCreateCompanyModal}
        onClose={() => setShowCreateCompanyModal(false)}
        title='Νέα Εταιρεία'
        footer={
          <>
            <Button variant='secondary' onClick={() => setShowCreateCompanyModal(false)}>
              Ακύρωση
            </Button>
            <Button onClick={handleCreateCompany} isLoading={isCreatingCompany}>
              Δημιουργία
            </Button>
          </>
        }
      >
        <div className='space-y-4'>
          <Input
            label='Όνομα Εταιρείας'
            value={newCompanyName}
            onChange={(e) => setNewCompanyName(e.target.value)}
            placeholder='π.χ. Εταιρεία Μου ΑΕ'
          />
          <Input
            label='Κωδικός'
            value={newCompanyCode}
            onChange={(e) => setNewCompanyCode(e.target.value.toUpperCase())}
            placeholder='π.χ. MYCO'
            maxLength={20}
          />
        </div>
      </Modal>
    </div>
  )
}
