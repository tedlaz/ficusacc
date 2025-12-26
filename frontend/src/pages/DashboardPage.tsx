import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Card, LoadingSpinner } from '@/components/ui'
import { useAuth } from '@/contexts'
import { formatCurrency } from '@/lib/utils'
import { BookOpen, Receipt, TrendingUp, TrendingDown } from 'lucide-react'
import { format } from 'date-fns'

export function DashboardPage() {
  const { user } = useAuth()
  const today = format(new Date(), 'yyyy-MM-dd')
  const hasCompany = !!user?.companyId

  const { data: accounts, isLoading: accountsLoading } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => api.getChartOfAccounts(),
    enabled: hasCompany,
  })

  const { data: transactions, isLoading: transactionsLoading } = useQuery({
    queryKey: ['transactions'],
    queryFn: () => api.getTransactions({ limit: 5 }),
    enabled: hasCompany,
  })

  const { data: trialBalance, isLoading: trialBalanceLoading } = useQuery({
    queryKey: ['trialBalance', today],
    queryFn: () => api.getTrialBalance(today),
    enabled: hasCompany,
  })

  const isLoading = hasCompany && (accountsLoading || transactionsLoading || trialBalanceLoading)

  if (!hasCompany) {
    return (
      <div className='flex flex-col items-center justify-center py-12'>
        <Card className='max-w-md text-center'>
          <h2 className='text-xl font-semibold text-gray-900 mb-2'>Καλωσήρθατε!</h2>
          <p className='text-gray-600 mb-4'>
            Δεν έχετε ενεργή εταιρεία. Επιλέξτε ή δημιουργήστε μια εταιρεία από το μενού στα αριστερά.
          </p>
        </Card>
      </div>
    )
  }

  if (isLoading) {
    return <LoadingSpinner />
  }

  // Calculate totals from trial balance
  const totalAssets =
    trialBalance?.accounts
      .filter((a) => a.account.account_type === 'asset')
      .reduce((sum, a) => sum + parseFloat(a.balance), 0) || 0

  const totalLiabilities =
    trialBalance?.accounts
      .filter((a) => a.account.account_type === 'liability')
      .reduce((sum, a) => sum + Math.abs(parseFloat(a.balance)), 0) || 0

  const totalRevenue =
    trialBalance?.accounts
      .filter((a) => a.account.account_type === 'revenue')
      .reduce((sum, a) => sum + Math.abs(parseFloat(a.balance)), 0) || 0

  const totalExpenses =
    trialBalance?.accounts
      .filter((a) => a.account.account_type === 'expense')
      .reduce((sum, a) => sum + parseFloat(a.balance), 0) || 0

  return (
    <div>
      <div className='mb-8'>
        <h1 className='text-2xl font-bold text-gray-900'>Πίνακας Ελέγχου</h1>
        <p className='text-gray-600'>Εταιρία: {user?.companyName || 'your company'}</p>
      </div>

      {/* Stats Grid */}
      <div className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8'>
        <Card>
          <div className='flex items-center'>
            <div className='p-3 bg-blue-100 rounded-lg'>
              <TrendingUp className='h-6 w-6 text-blue-600' />
            </div>
            <div className='ml-4'>
              <p className='text-sm text-gray-600'>Αποθέματα</p>
              <p className='text-xl font-semibold text-gray-900'>{formatCurrency(totalAssets)}</p>
            </div>
          </div>
        </Card>

        <Card>
          <div className='flex items-center'>
            <div className='p-3 bg-red-100 rounded-lg'>
              <TrendingDown className='h-6 w-6 text-red-600' />
            </div>
            <div className='ml-4'>
              <p className='text-sm text-gray-600'>Υποχρεώσεις</p>
              <p className='text-xl font-semibold text-gray-900'>{formatCurrency(totalLiabilities)}</p>
            </div>
          </div>
        </Card>

        <Card>
          <div className='flex items-center'>
            <div className='p-3 bg-green-100 rounded-lg'>
              <TrendingUp className='h-6 w-6 text-green-600' />
            </div>
            <div className='ml-4'>
              <p className='text-sm text-gray-600'>Έσοδα</p>
              <p className='text-xl font-semibold text-gray-900'>{formatCurrency(totalRevenue)}</p>
            </div>
          </div>
        </Card>

        <Card>
          <div className='flex items-center'>
            <div className='p-3 bg-orange-100 rounded-lg'>
              <TrendingDown className='h-6 w-6 text-orange-600' />
            </div>
            <div className='ml-4'>
              <p className='text-sm text-gray-600'>Έξοδα</p>
              <p className='text-xl font-semibold text-gray-900'>{formatCurrency(totalExpenses)}</p>
            </div>
          </div>
        </Card>
      </div>

      <div className='grid grid-cols-1 lg:grid-cols-2 gap-6'>
        {/* Account Summary */}
        <Card title='Λογιστικό Σχέδιο'>
          <div className='space-y-3'>
            {accounts?.items.slice(0, 8).map((account) => (
              <div key={account.id} className='flex items-center justify-between py-2'>
                <div className='flex items-center'>
                  <BookOpen className='h-4 w-4 text-gray-400 mr-2' />
                  <div>
                    <p className='text-sm font-medium text-gray-900'>{account.name}</p>
                    <p className='text-xs text-gray-500'>{account.code}</p>
                  </div>
                </div>
                <span
                  className={`text-xs px-2 py-1 rounded-full ${
                    account.account_type === 'asset'
                      ? 'bg-blue-100 text-blue-800'
                      : account.account_type === 'liability'
                      ? 'bg-red-100 text-red-800'
                      : account.account_type === 'equity'
                      ? 'bg-purple-100 text-purple-800'
                      : account.account_type === 'revenue'
                      ? 'bg-green-100 text-green-800'
                      : 'bg-orange-100 text-orange-800'
                  }`}
                >
                  {account.account_type}
                </span>
              </div>
            ))}
            {accounts?.total === 0 && (
              <p className='text-sm text-gray-500 text-center py-4'>No accounts yet</p>
            )}
          </div>
        </Card>

        {/* Recent Transactions */}
        <Card title='Νέες Εγγραφές'>
          <div className='space-y-3'>
            {transactions?.items.map((transaction) => (
              <div key={transaction.id} className='flex items-center justify-between py-2'>
                <div className='flex items-center'>
                  <Receipt className='h-4 w-4 text-gray-400 mr-2' />
                  <div>
                    <p className='text-sm font-medium text-gray-900'>{transaction.description}</p>
                    <p className='text-xs text-gray-500'>{transaction.transaction_date}</p>
                  </div>
                </div>
                <span
                  className={`text-xs px-2 py-1 rounded-full ${
                    transaction.is_posted ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'
                  }`}
                >
                  {transaction.is_posted ? 'Posted' : 'Draft'}
                </span>
              </div>
            ))}
            {transactions?.total === 0 && (
              <p className='text-sm text-gray-500 text-center py-4'>No transactions yet</p>
            )}
          </div>
        </Card>
      </div>
    </div>
  )
}
