import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import {
  Button,
  Card,
  Input,
  LoadingSpinner,
  Select,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui'
import { formatCurrency, formatDate, getAccountTypeColor, getAccountTypeLabel } from '@/lib/utils'
import {
  exportTrialBalanceToPDF,
  exportBalanceSheetToPDF,
  exportIncomeStatementToPDF,
  exportGeneralLedgerToPDF,
  exportJournalToPDF,
} from '@/lib/pdfExport'
import { format, subDays } from 'date-fns'
import { Download } from 'lucide-react'
import { useAuth } from '@/contexts'

type ReportType = 'trial-balance' | 'balance-sheet' | 'income-statement' | 'general-ledger' | 'journal'

export function ReportsPage() {
  const { user } = useAuth()
  const hasCompany = !!user?.companyId
  const [reportType, setReportType] = useState<ReportType>('trial-balance')
  const [asOfDate, setAsOfDate] = useState(format(new Date(), 'yyyy-MM-dd'))
  const [startDate, setStartDate] = useState(format(subDays(new Date(), 30), 'yyyy-MM-dd'))
  const [endDate, setEndDate] = useState(format(new Date(), 'yyyy-MM-dd'))
  const [selectedAccountId, setSelectedAccountId] = useState<string>('')

  const { data: accounts } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => api.getChartOfAccounts(),
    enabled: hasCompany,
  })

  const {
    data: trialBalance,
    isLoading: trialBalanceLoading,
    refetch: refetchTrialBalance,
  } = useQuery({
    queryKey: ['trialBalance', asOfDate],
    queryFn: () => api.getTrialBalance(asOfDate),
    enabled: hasCompany && reportType === 'trial-balance',
  })

  const {
    data: balanceSheet,
    isLoading: balanceSheetLoading,
    refetch: refetchBalanceSheet,
  } = useQuery({
    queryKey: ['balanceSheet', asOfDate],
    queryFn: () => api.getBalanceSheet(asOfDate),
    enabled: hasCompany && reportType === 'balance-sheet',
  })

  const {
    data: incomeStatement,
    isLoading: incomeStatementLoading,
    refetch: refetchIncomeStatement,
  } = useQuery({
    queryKey: ['incomeStatement', startDate, endDate],
    queryFn: () => api.getIncomeStatement(startDate, endDate),
    enabled: hasCompany && reportType === 'income-statement',
  })

  const {
    data: generalLedger,
    isLoading: generalLedgerLoading,
    refetch: refetchGeneralLedger,
  } = useQuery({
    queryKey: ['generalLedger', selectedAccountId, startDate, endDate],
    queryFn: () => api.getGeneralLedger(parseInt(selectedAccountId), startDate, endDate),
    enabled: hasCompany && reportType === 'general-ledger' && !!selectedAccountId,
  })

  const {
    data: journal,
    isLoading: journalLoading,
    refetch: refetchJournal,
  } = useQuery({
    queryKey: ['journal', startDate, endDate],
    queryFn: () => api.getJournal(startDate, endDate),
    enabled: hasCompany && reportType === 'journal',
  })

  const isLoading =
    trialBalanceLoading ||
    balanceSheetLoading ||
    incomeStatementLoading ||
    generalLedgerLoading ||
    journalLoading

  const handleGenerate = () => {
    switch (reportType) {
      case 'trial-balance':
        refetchTrialBalance()
        break
      case 'balance-sheet':
        refetchBalanceSheet()
        break
      case 'income-statement':
        refetchIncomeStatement()
        break
      case 'general-ledger':
        refetchGeneralLedger()
        break
      case 'journal':
        refetchJournal()
        break
    }
  }

  const handleExportPDF = async () => {
    try {
      switch (reportType) {
        case 'trial-balance':
          if (trialBalance) await exportTrialBalanceToPDF(trialBalance)
          break
        case 'balance-sheet':
          if (balanceSheet) await exportBalanceSheetToPDF(balanceSheet)
          break
        case 'income-statement':
          if (incomeStatement) await exportIncomeStatementToPDF(incomeStatement)
          break
        case 'general-ledger':
          if (generalLedger) await exportGeneralLedgerToPDF(generalLedger)
          break
        case 'journal':
          if (journal) await exportJournalToPDF(journal)
          break
      }
    } catch (error) {
      console.error('Error exporting PDF:', error)
    }
  }

  const canExport =
    (reportType === 'trial-balance' && trialBalance) ||
    (reportType === 'balance-sheet' && balanceSheet) ||
    (reportType === 'income-statement' && incomeStatement) ||
    (reportType === 'general-ledger' && generalLedger) ||
    (reportType === 'journal' && journal)

  const reportOptions = [
    { value: 'trial-balance', label: 'Trial Balance' },
    { value: 'balance-sheet', label: 'Balance Sheet' },
    { value: 'income-statement', label: 'Income Statement' },
    { value: 'general-ledger', label: 'General Ledger' },
    { value: 'journal', label: 'Journal' },
  ]

  const needsDateRange = ['income-statement', 'general-ledger', 'journal'].includes(reportType)
  const needsAsOfDate = ['trial-balance', 'balance-sheet'].includes(reportType)
  const needsAccount = reportType === 'general-ledger'

  if (!hasCompany) {
    return (
      <div>
        <h1 className='text-2xl font-bold text-gray-900 mb-6'>Αναφορές</h1>
        <Card>
          <p className='text-gray-600 text-center py-8'>
            Παρακαλώ επιλέξτε ή δημιουργήστε μια εταιρεία για να δείτε τις αναφορές.
          </p>
        </Card>
      </div>
    )
  }

  return (
    <div>
      <div className='mb-8'>
        <h1 className='text-2xl font-bold text-gray-900'>Αναφορές</h1>
        <p className='text-gray-600'>Δημιουργία οικονομικών αναφορών</p>
      </div>

      {/* Report Controls */}
      <Card className='mb-6'>
        <div className='grid grid-cols-1 sm:grid-cols-2 lg:flex lg:flex-wrap gap-4 items-end'>
          <div className='w-full sm:w-auto lg:w-48'>
            <Select
              label='Report Type'
              value={reportType}
              onChange={(e) => setReportType(e.target.value as ReportType)}
              options={reportOptions}
            />
          </div>

          {needsAsOfDate && (
            <div className='w-full sm:w-auto lg:w-40'>
              <Input
                label='As of Date'
                type='date'
                value={asOfDate}
                onChange={(e) => setAsOfDate(e.target.value)}
              />
            </div>
          )}

          {needsDateRange && (
            <>
              <div className='w-full sm:w-auto lg:w-40'>
                <Input
                  label='Start Date'
                  type='date'
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                />
              </div>
              <div className='w-full sm:w-auto lg:w-40'>
                <Input
                  label='End Date'
                  type='date'
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                />
              </div>
            </>
          )}

          {needsAccount && (
            <div className='w-full sm:w-auto lg:w-64'>
              <Select
                label='Account'
                value={selectedAccountId}
                onChange={(e) => setSelectedAccountId(e.target.value)}
                options={[
                  { value: '', label: 'Select account...' },
                  ...(accounts?.items.map((a) => ({
                    value: a.id.toString(),
                    label: `${a.code} - ${a.name}`,
                  })) || []),
                ]}
              />
            </div>
          )}

          <div className='flex gap-2 w-full sm:w-auto'>
            <Button onClick={handleGenerate} className='flex-1 sm:flex-none'>
              Δημιουργία
            </Button>
            {canExport && (
              <Button variant='secondary' onClick={handleExportPDF} className='flex-1 sm:flex-none'>
                <Download className='h-4 w-4 mr-1 sm:mr-2' />
                <span className='hidden sm:inline'>Σε_ </span>PDF
              </Button>
            )}
          </div>
        </div>
      </Card>

      {/* Report Content */}
      {isLoading ? (
        <LoadingSpinner />
      ) : (
        <>
          {/* Trial Balance */}
          {reportType === 'trial-balance' && trialBalance && (
            <Card title={`Ισοζύγιο έως ${formatDate(trialBalance.as_of_date)}`}>
              {/* Mobile Card View */}
              <div className='block lg:hidden space-y-3'>
                {trialBalance.accounts.map((item) => (
                  <div key={item.account.id} className='border border-gray-200 rounded-lg p-3'>
                    <div className='flex justify-between items-start mb-2'>
                      <div>
                        <span className='font-mono text-xs text-gray-500'>{item.account.code}</span>
                        <p className='font-medium text-gray-900'>{item.account.name}</p>
                      </div>
                      <span
                        className={`text-xs px-2 py-1 rounded-full ${getAccountTypeColor(
                          item.account.account_type
                        )}`}
                      >
                        {getAccountTypeLabel(item.account.account_type)}
                      </span>
                    </div>
                    <div className='grid grid-cols-3 gap-2 text-sm'>
                      <div className='bg-gray-50 p-2 rounded'>
                        <span className='text-gray-500 block text-xs'>Χρέωση</span>
                        <span className='font-medium'>
                          {parseFloat(item.debit_total) > 0 ? formatCurrency(item.debit_total) : '-'}
                        </span>
                      </div>
                      <div className='bg-gray-50 p-2 rounded'>
                        <span className='text-gray-500 block text-xs'>Πίστωση</span>
                        <span className='font-medium'>
                          {parseFloat(item.credit_total) > 0 ? formatCurrency(item.credit_total) : '-'}
                        </span>
                      </div>
                      <div className='bg-blue-50 p-2 rounded'>
                        <span className='text-gray-500 block text-xs'>Υπόλοιπο</span>
                        <span className='font-medium text-blue-700'>
                          {formatCurrency(parseFloat(item.debit_total) - parseFloat(item.credit_total))}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
                <div className='border-t-2 border-gray-300 pt-3 mt-3'>
                  <div className='grid grid-cols-3 gap-2 text-sm font-bold'>
                    <div className='bg-gray-100 p-2 rounded'>
                      <span className='text-gray-600 block text-xs'>Χρεώσεις</span>
                      <span>{formatCurrency(trialBalance.total_debits)}</span>
                    </div>
                    <div className='bg-gray-100 p-2 rounded'>
                      <span className='text-gray-600 block text-xs'>Πιστώσεις</span>
                      <span>{formatCurrency(trialBalance.total_credits)}</span>
                    </div>
                    <div className='bg-blue-100 p-2 rounded'>
                      <span className='text-gray-600 block text-xs'>Διαφορά</span>
                      <span className='text-blue-700'>
                        {formatCurrency(
                          parseFloat(trialBalance.total_debits) - parseFloat(trialBalance.total_credits)
                        )}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Desktop Table View */}
              <div className='hidden lg:block'>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableHeader>Κωδικος</TableHeader>
                      <TableHeader>Λογαριασμος</TableHeader>
                      <TableHeader>Τυπος</TableHeader>
                      <TableHeader className='text-right'>Χρεωση</TableHeader>
                      <TableHeader className='text-right'>Πιστωση</TableHeader>
                      <TableHeader className='text-right'>Υπολοιπο</TableHeader>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {trialBalance.accounts.map((item) => (
                      <TableRow key={item.account.id}>
                        <TableCell className='font-mono'>{item.account.code}</TableCell>
                        <TableCell className='font-medium'>{item.account.name}</TableCell>
                        <TableCell>
                          <span
                            className={`text-xs px-2 py-1 rounded-full ${getAccountTypeColor(
                              item.account.account_type
                            )}`}
                          >
                            {getAccountTypeLabel(item.account.account_type)}
                          </span>
                        </TableCell>
                        <TableCell className='text-right'>
                          {parseFloat(item.debit_total) > 0 ? formatCurrency(item.debit_total) : '-'}
                        </TableCell>
                        <TableCell className='text-right'>
                          {parseFloat(item.credit_total) > 0 ? formatCurrency(item.credit_total) : '-'}
                        </TableCell>
                        <TableCell className='text-right font-medium text-blue-700'>
                          {formatCurrency(parseFloat(item.debit_total) - parseFloat(item.credit_total))}
                        </TableCell>
                      </TableRow>
                    ))}
                    <TableRow className='font-bold bg-gray-50'>
                      <TableCell colSpan={3}>Total</TableCell>
                      <TableCell className='text-right'>
                        {formatCurrency(trialBalance.total_debits)}
                      </TableCell>
                      <TableCell className='text-right'>
                        {formatCurrency(trialBalance.total_credits)}
                      </TableCell>
                      <TableCell className='text-right text-blue-700'>
                        {formatCurrency(
                          parseFloat(trialBalance.total_debits) - parseFloat(trialBalance.total_credits)
                        )}
                      </TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </div>
            </Card>
          )}

          {/* Balance Sheet */}
          {reportType === 'balance-sheet' && balanceSheet && (
            <div className='grid grid-cols-1 lg:grid-cols-2 gap-6'>
              <Card title='Assets'>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableHeader>Account</TableHeader>
                      <TableHeader className='text-right'>Υπόλοιπο</TableHeader>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {balanceSheet.assets.map((item) => (
                      <TableRow key={item.account.id}>
                        <TableCell>{item.account.name}</TableCell>
                        <TableCell className='text-right'>{formatCurrency(item.balance)}</TableCell>
                      </TableRow>
                    ))}
                    <TableRow className='font-bold bg-gray-50'>
                      <TableCell>Total Assets</TableCell>
                      <TableCell className='text-right'>
                        {formatCurrency(balanceSheet.total_assets)}
                      </TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </Card>

              <div className='space-y-6'>
                <Card title='Liabilities'>
                  <Table>
                    <TableHead>
                      <TableRow>
                        <TableHeader>Λογαριασμός</TableHeader>
                        <TableHeader className='text-right'>Υπόλοιπο</TableHeader>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {balanceSheet.liabilities.map((item) => (
                        <TableRow key={item.account.id}>
                          <TableCell>{item.account.name}</TableCell>
                          <TableCell className='text-right'>
                            {formatCurrency(Math.abs(parseFloat(item.balance)))}
                          </TableCell>
                        </TableRow>
                      ))}
                      <TableRow className='font-bold bg-gray-50'>
                        <TableCell>Total Liabilities</TableCell>
                        <TableCell className='text-right'>
                          {formatCurrency(balanceSheet.total_liabilities)}
                        </TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </Card>

                <Card title='Equity'>
                  <Table>
                    <TableHead>
                      <TableRow>
                        <TableHeader>Λογαριασμός</TableHeader>
                        <TableHeader className='text-right'>Υπόλοιπο</TableHeader>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {balanceSheet.equity.map((item) => (
                        <TableRow key={item.account.id}>
                          <TableCell>{item.account.name}</TableCell>
                          <TableCell className='text-right'>
                            {formatCurrency(Math.abs(parseFloat(item.balance)))}
                          </TableCell>
                        </TableRow>
                      ))}
                      <TableRow className='font-bold bg-gray-50'>
                        <TableCell>Total Equity</TableCell>
                        <TableCell className='text-right'>
                          {formatCurrency(balanceSheet.total_equity)}
                        </TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </Card>
              </div>
            </div>
          )}

          {/* Income Statement */}
          {reportType === 'income-statement' && incomeStatement && (
            <div className='grid grid-cols-1 lg:grid-cols-2 gap-6'>
              <Card title='Revenue'>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableHeader>Λογαριασμός</TableHeader>
                      <TableHeader className='text-right'>Ποσό</TableHeader>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {incomeStatement.revenues.map((item) => (
                      <TableRow key={item.account.id}>
                        <TableCell>{item.account.name}</TableCell>
                        <TableCell className='text-right'>
                          {formatCurrency(Math.abs(parseFloat(item.balance)))}
                        </TableCell>
                      </TableRow>
                    ))}
                    <TableRow className='font-bold bg-green-50'>
                      <TableCell>Total Revenue</TableCell>
                      <TableCell className='text-right text-green-700'>
                        {formatCurrency(incomeStatement.total_revenue)}
                      </TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </Card>

              <Card title='Expenses'>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableHeader>Λογαριασμός</TableHeader>
                      <TableHeader className='text-right'>Ποσό</TableHeader>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {incomeStatement.expenses.map((item) => (
                      <TableRow key={item.account.id}>
                        <TableCell>{item.account.name}</TableCell>
                        <TableCell className='text-right'>{formatCurrency(item.balance)}</TableCell>
                      </TableRow>
                    ))}
                    <TableRow className='font-bold bg-red-50'>
                      <TableCell>Total Expenses</TableCell>
                      <TableCell className='text-right text-red-700'>
                        {formatCurrency(incomeStatement.total_expenses)}
                      </TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </Card>

              <Card className='lg:col-span-2'>
                <div
                  className={`text-center p-4 rounded-lg ${
                    parseFloat(incomeStatement.net_income) >= 0 ? 'bg-green-50' : 'bg-red-50'
                  }`}
                >
                  <p className='text-sm text-gray-600'>Net Income</p>
                  <p
                    className={`text-2xl font-bold ${
                      parseFloat(incomeStatement.net_income) >= 0 ? 'text-green-700' : 'text-red-700'
                    }`}
                  >
                    {formatCurrency(incomeStatement.net_income)}
                  </p>
                </div>
              </Card>
            </div>
          )}

          {/* General Ledger */}
          {reportType === 'general-ledger' && generalLedger && (
            <Card title={`Καρτέλα για: ${generalLedger.account.name}`}>
              <div className='mb-4 p-3 bg-gray-50 rounded-lg flex flex-col sm:flex-row justify-between gap-2'>
                <span className='text-sm text-gray-600'>
                  Άνοιγμα: <strong>{formatCurrency(generalLedger.opening_balance)}</strong>
                </span>
                <span className='text-sm text-gray-600'>
                  Κλείσιμο: <strong>{formatCurrency(generalLedger.closing_balance)}</strong>
                </span>
              </div>

              {/* Mobile Card View */}
              <div className='block lg:hidden space-y-3'>
                {generalLedger.entries.map((entry, index) => (
                  <div key={index} className='border border-gray-200 rounded-lg p-3'>
                    <div className='flex justify-between items-start mb-2'>
                      <div>
                        <p className='text-sm font-medium text-gray-900'>{entry.description}</p>
                        <p className='text-xs text-gray-500'>{formatDate(entry.date)}</p>
                        {entry.reference && <p className='text-xs text-gray-400'>Ref: {entry.reference}</p>}
                      </div>
                      <div className='text-right'>
                        <p className='text-sm font-bold'>{formatCurrency(entry.balance)}</p>
                        <p className='text-xs text-gray-500'>Υπόλοιπο</p>
                      </div>
                    </div>
                    <div className='grid grid-cols-2 gap-2 text-sm'>
                      <div className='bg-green-50 p-2 rounded'>
                        <span className='text-gray-500 block text-xs'>Χρέωση</span>
                        <span className='font-medium text-green-700'>
                          {parseFloat(entry.debit) > 0 ? formatCurrency(entry.debit) : '-'}
                        </span>
                      </div>
                      <div className='bg-red-50 p-2 rounded'>
                        <span className='text-gray-500 block text-xs'>Πίστωση</span>
                        <span className='font-medium text-red-700'>
                          {parseFloat(entry.credit) > 0 ? formatCurrency(entry.credit) : '-'}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
                {generalLedger.entries.length === 0 && (
                  <p className='text-center text-gray-500 py-8'>No entries found for this period.</p>
                )}
              </div>

              {/* Desktop Table View */}
              <div className='hidden lg:block'>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableHeader>ΗΜ/ΝΙΑ</TableHeader>
                      <TableHeader>Περιγραφη</TableHeader>
                      <TableHeader>Σχετικο</TableHeader>
                      <TableHeader className='text-right'>Χρεωση</TableHeader>
                      <TableHeader className='text-right'>Πιστωση</TableHeader>
                      <TableHeader className='text-right'>Υπολοιπο</TableHeader>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {generalLedger.entries.map((entry, index) => (
                      <TableRow key={index}>
                        <TableCell>{formatDate(entry.date)}</TableCell>
                        <TableCell>{entry.description}</TableCell>
                        <TableCell className='text-gray-500'>{entry.reference || '-'}</TableCell>
                        <TableCell className='text-right'>
                          {parseFloat(entry.debit) > 0 ? formatCurrency(entry.debit) : '-'}
                        </TableCell>
                        <TableCell className='text-right'>
                          {parseFloat(entry.credit) > 0 ? formatCurrency(entry.credit) : '-'}
                        </TableCell>
                        <TableCell className='text-right font-medium'>
                          {formatCurrency(entry.balance)}
                        </TableCell>
                      </TableRow>
                    ))}
                    {generalLedger.entries.length === 0 && (
                      <TableRow>
                        <TableCell colSpan={6} className='text-center text-gray-500 py-8'>
                          No entries found for this period.
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
            </Card>
          )}

          {/* Journal */}
          {reportType === 'journal' && journal && (
            <Card title={`Ημερολόγιο: ${formatDate(journal.start_date)} έως ${formatDate(journal.end_date)}`}>
              <div className='space-y-4 sm:space-y-6'>
                {journal.entries.map((entry) => (
                  <div key={entry.transaction.id} className='border border-gray-200 rounded-lg p-3 sm:p-4'>
                    <div className='flex flex-col sm:flex-row sm:justify-between sm:items-start gap-2 mb-3'>
                      <div>
                        <p className='font-medium text-gray-900 text-sm sm:text-base'>
                          {entry.transaction.description}
                        </p>
                        <p className='text-xs sm:text-sm text-gray-500'>
                          {formatDate(entry.transaction.transaction_date)}
                          {entry.transaction.reference && ` • Ref: ${entry.transaction.reference}`}
                        </p>
                      </div>
                      <span
                        className={`text-xs px-2 py-1 rounded-full self-start ${
                          entry.transaction.is_posted
                            ? 'bg-green-100 text-green-800'
                            : 'bg-yellow-100 text-yellow-800'
                        }`}
                      >
                        {entry.transaction.is_posted ? 'Posted' : 'Draft'}
                      </span>
                    </div>

                    {/* Mobile View - List style */}
                    <div className='block sm:hidden space-y-2'>
                      {entry.debits.map((debit, index) => (
                        <div
                          key={`debit-${index}`}
                          className='flex justify-between items-center bg-green-50 p-2 rounded'
                        >
                          <span className='text-sm font-medium'>{debit.account.name}</span>
                          <span className='text-sm text-green-700'>Χρ: {formatCurrency(debit.amount)}</span>
                        </div>
                      ))}
                      {entry.credits.map((credit, index) => (
                        <div
                          key={`credit-${index}`}
                          className='flex justify-between items-center bg-red-50 p-2 rounded ml-4'
                        >
                          <span className='text-sm font-medium'>{credit.account.name}</span>
                          <span className='text-sm text-red-700'>Πι: {formatCurrency(credit.amount)}</span>
                        </div>
                      ))}
                    </div>

                    {/* Desktop View - Table */}
                    <div className='hidden sm:block'>
                      <Table>
                        <TableHead>
                          <TableRow>
                            <TableHeader>Λογαριασμος</TableHeader>
                            <TableHeader className='text-right'>Χρεωση</TableHeader>
                            <TableHeader className='text-right'>Πιστωση</TableHeader>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {entry.debits.map((debit, index) => (
                            <TableRow key={`debit-${index}`}>
                              <TableCell>{debit.account.name}</TableCell>
                              <TableCell className='text-right'>{formatCurrency(debit.amount)}</TableCell>
                              <TableCell className='text-right'>-</TableCell>
                            </TableRow>
                          ))}
                          {entry.credits.map((credit, index) => (
                            <TableRow key={`credit-${index}`}>
                              <TableCell className='pl-8'>{credit.account.name}</TableCell>
                              <TableCell className='text-right'>-</TableCell>
                              <TableCell className='text-right'>{formatCurrency(credit.amount)}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  </div>
                ))}
                {journal.entries.length === 0 && (
                  <p className='text-center text-gray-500 py-8'>No journal entries found for this period.</p>
                )}
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
