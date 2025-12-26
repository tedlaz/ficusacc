import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { api } from '@/lib/api'
import {
  Button,
  Card,
  Input,
  LoadingSpinner,
  Modal,
  Select,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui'
import { getAccountTypeColor, getAccountTypeLabel } from '@/lib/utils'
import { Plus, Pencil, Trash2, Upload, Download } from 'lucide-react'
import toast from 'react-hot-toast'
import type { Account, AccountCreate, AccountUpdate } from '@/types'
import { AccountType } from '@/types'
import type { AxiosError } from 'axios'
import type { ApiError } from '@/types'
import { useAuth } from '@/contexts'

const accountSchema = z.object({
  code: z.string().min(1, 'Code is required').max(20),
  name: z.string().min(1, 'Name is required').max(200),
  account_type: z.string().min(1, 'Account type is required'),
  parent_id: z.string().optional(),
  description: z.string().optional(),
})

type AccountFormData = z.infer<typeof accountSchema>

export function AccountsPage() {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const hasCompany = !!user?.companyId
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingAccount, setEditingAccount] = useState<Account | null>(null)
  const [isImportModalOpen, setIsImportModalOpen] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { data: accounts, isLoading } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => api.getChartOfAccounts(),
    enabled: hasCompany,
  })

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<AccountFormData>({
    resolver: zodResolver(accountSchema),
  })

  const createMutation = useMutation({
    mutationFn: (data: AccountCreate) => api.createAccount(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
      toast.success('Account created successfully')
      closeModal()
    },
    onError: (error: AxiosError<ApiError>) => {
      toast.error(error.response?.data?.detail || 'Failed to create account')
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: AccountUpdate }) => api.updateAccount(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
      toast.success('Account updated successfully')
      closeModal()
    },
    onError: (error: AxiosError<ApiError>) => {
      toast.error(error.response?.data?.detail || 'Failed to update account')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.deleteAccount(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
      toast.success('Account deleted successfully')
    },
    onError: (error: AxiosError<ApiError>) => {
      toast.error(error.response?.data?.detail || 'Failed to delete account')
    },
  })

  const importMutation = useMutation({
    mutationFn: (accounts: Array<{ code: string; name: string; account_type: string }>) =>
      api.bulkCreateAccounts(accounts),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
      if (result.errors.length > 0) {
        toast.success(`Δημιουργήθηκαν ${result.created} λογαριασμοί`)
        result.errors.forEach((err) => toast.error(err))
      } else {
        toast.success(`Δημιουργήθηκαν ${result.created} λογαριασμοί επιτυχώς`)
      }
      setIsImportModalOpen(false)
    },
    onError: (error: AxiosError<ApiError>) => {
      toast.error(error.response?.data?.detail || 'Αποτυχία εισαγωγής λογαριασμών')
    },
  })

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = (e) => {
      const text = e.target?.result as string
      const lines = text.split('\n').filter((line) => line.trim())

      // Skip header row if present
      const dataLines = lines[0]?.toLowerCase().includes('code') ? lines.slice(1) : lines

      const accounts: Array<{ code: string; name: string; account_type: string }> = []
      const parseErrors: string[] = []

      dataLines.forEach((line, index) => {
        const parts = line.split(',').map((p) => p.trim().replace(/^"|"$/g, ''))
        if (parts.length >= 3) {
          const [code, name, account_type] = parts
          const validTypes = ['asset', 'liability', 'equity', 'revenue', 'expense']
          if (validTypes.includes(account_type.toLowerCase())) {
            accounts.push({ code, name, account_type: account_type.toLowerCase() })
          } else {
            parseErrors.push(`Γραμμή ${index + 1}: Μη έγκυρος τύπος λογαριασμού "${account_type}"`)
          }
        } else if (parts.length > 0 && parts[0]) {
          parseErrors.push(`Γραμμή ${index + 1}: Απαιτούνται 3 στήλες (code, name, account_type)`)
        }
      })

      if (parseErrors.length > 0) {
        parseErrors.slice(0, 5).forEach((err) => toast.error(err))
        if (parseErrors.length > 5) {
          toast.error(`...και ${parseErrors.length - 5} ακόμα σφάλματα`)
        }
      }

      if (accounts.length > 0) {
        importMutation.mutate(accounts)
      } else {
        toast.error('Δεν βρέθηκαν έγκυροι λογαριασμοί στο αρχείο')
      }
    }
    reader.readAsText(file)

    // Reset file input
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const handleExportCSV = () => {
    if (!accounts?.items.length) {
      toast.error('Δεν υπάρχουν λογαριασμοί για εξαγωγή')
      return
    }

    const header = 'code,name,account_type'
    const rows = accounts.items.map((acc) => `"${acc.code}","${acc.name}","${acc.account_type}"`)
    const csv = [header, ...rows].join('\n')

    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'chart_of_accounts.csv'
    link.click()
    URL.revokeObjectURL(url)

    toast.success('Το αρχείο CSV εξήχθη επιτυχώς')
  }

  const openCreateModal = () => {
    setEditingAccount(null)
    reset({
      code: '',
      name: '',
      account_type: '',
      parent_id: '',
      description: '',
    })
    setIsModalOpen(true)
  }

  const openEditModal = (account: Account) => {
    setEditingAccount(account)
    reset({
      code: account.code,
      name: account.name,
      account_type: account.account_type,
      parent_id: account.parent_id?.toString() || '',
      description: account.description || '',
    })
    setIsModalOpen(true)
  }

  const closeModal = () => {
    setIsModalOpen(false)
    setEditingAccount(null)
    reset()
  }

  const onSubmit = (data: AccountFormData) => {
    const accountData = {
      code: data.code,
      name: data.name,
      account_type: data.account_type as AccountType,
      parent_id: data.parent_id ? parseInt(data.parent_id) : null,
      description: data.description || null,
    }

    if (editingAccount) {
      updateMutation.mutate({ id: editingAccount.id, data: accountData })
    } else {
      createMutation.mutate(accountData)
    }
  }

  const handleDelete = (account: Account) => {
    if (confirm(`Are you sure you want to delete "${account.name}"?`)) {
      deleteMutation.mutate(account.id)
    }
  }

  const accountTypeOptions = [
    { value: '', label: 'Select type...' },
    { value: AccountType.ASSET, label: 'Asset' },
    { value: AccountType.LIABILITY, label: 'Liability' },
    { value: AccountType.EQUITY, label: 'Equity' },
    { value: AccountType.REVENUE, label: 'Revenue' },
    { value: AccountType.EXPENSE, label: 'Expense' },
  ]

  if (!hasCompany) {
    return (
      <div>
        <h1 className='text-xl sm:text-2xl font-bold text-gray-900 mb-6'>Λογιστικό Σχέδιο</h1>
        <Card>
          <p className='text-gray-600 text-center py-8'>
            Παρακαλώ επιλέξτε ή δημιουργήστε μια εταιρεία για να δείτε τους λογαριασμούς.
          </p>
        </Card>
      </div>
    )
  }

  if (isLoading) {
    return <LoadingSpinner />
  }

  return (
    <div>
      <div className='flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6'>
        <div>
          <h1 className='text-xl sm:text-2xl font-bold text-gray-900'>Λογιστικό Σχέδιο</h1>
          <p className='text-sm sm:text-base text-gray-600'>Διαχείρηση λογαριασμών της εταιρείας σας</p>
        </div>
        <div className='flex flex-wrap gap-2'>
          <Button variant='secondary' onClick={() => setIsImportModalOpen(true)} className='w-full sm:w-auto'>
            <Upload className='h-4 w-4 mr-2' />
            Εισαγωγή CSV
          </Button>
          <Button variant='secondary' onClick={handleExportCSV} className='w-full sm:w-auto'>
            <Download className='h-4 w-4 mr-2' />
            Εξαγωγή CSV
          </Button>
          <Button onClick={openCreateModal} className='w-full sm:w-auto'>
            <Plus className='h-4 w-4 mr-2' />
            Προσθήκη Λογαριασμού
          </Button>
        </div>
      </div>

      {/* Mobile Card View */}
      <div className='block lg:hidden space-y-4'>
        {accounts?.items.map((account) => (
          <Card key={account.id}>
            <div className='flex justify-between items-start'>
              <div className='flex-1 min-w-0'>
                <div className='flex items-center gap-2 mb-1'>
                  <span className='font-mono text-sm text-gray-500'>{account.code}</span>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full ${getAccountTypeColor(
                      account.account_type
                    )}`}
                  >
                    {getAccountTypeLabel(account.account_type)}
                  </span>
                </div>
                <p className='font-medium text-gray-900 truncate'>{account.name}</p>
                <span
                  className={`text-xs px-2 py-0.5 rounded-full inline-block mt-1 ${
                    account.is_active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'
                  }`}
                >
                  {account.is_active ? 'Active' : 'Inactive'}
                </span>
              </div>
              <div className='flex gap-2 ml-2'>
                <Button variant='secondary' onClick={() => openEditModal(account)} className='p-2!'>
                  <Pencil className='h-4 w-4' />
                </Button>
                <Button variant='danger' onClick={() => handleDelete(account)} className='p-2!'>
                  <Trash2 className='h-4 w-4' />
                </Button>
              </div>
            </div>
          </Card>
        ))}
        {accounts?.items.length === 0 && (
          <Card>
            <p className='text-center text-gray-500 py-4'>No accounts found. Create your first account.</p>
          </Card>
        )}
      </div>

      {/* Desktop Table View */}
      <Card className='hidden lg:block'>
        <Table>
          <TableHead>
            <TableRow>
              <TableHeader>Κωδικος</TableHeader>
              <TableHeader>Ονομασια</TableHeader>
              <TableHeader>Τυπος</TableHeader>
              <TableHeader>Κατασταση</TableHeader>
              <TableHeader className='text-right'>Ενεργειες</TableHeader>
            </TableRow>
          </TableHead>
          <TableBody>
            {accounts?.items.map((account) => (
              <TableRow key={account.id}>
                <TableCell className='font-mono'>{account.code}</TableCell>
                <TableCell className='font-medium'>{account.name}</TableCell>
                <TableCell>
                  <span
                    className={`text-xs px-2 py-1 rounded-full ${getAccountTypeColor(account.account_type)}`}
                  >
                    {getAccountTypeLabel(account.account_type)}
                  </span>
                </TableCell>
                <TableCell>
                  <span
                    className={`text-xs px-2 py-1 rounded-full ${
                      account.is_active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'
                    }`}
                  >
                    {account.is_active ? 'Active' : 'Inactive'}
                  </span>
                </TableCell>
                <TableCell className='text-right'>
                  <div className='flex justify-end gap-2'>
                    <Button variant='secondary' onClick={() => openEditModal(account)} className='p-2!'>
                      <Pencil className='h-4 w-4' />
                    </Button>
                    <Button variant='danger' onClick={() => handleDelete(account)} className='p-2!'>
                      <Trash2 className='h-4 w-4' />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {accounts?.items.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className='text-center text-gray-500 py-8'>
                  No accounts found. Create your first account.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>

      <Modal
        isOpen={isModalOpen}
        onClose={closeModal}
        closeOnOutsideClick={false}
        title={editingAccount ? 'Edit Account' : 'Create Account'}
        footer={
          <>
            <Button variant='secondary' onClick={closeModal}>
              Cancel
            </Button>
            <Button
              onClick={handleSubmit(onSubmit)}
              isLoading={createMutation.isPending || updateMutation.isPending}
            >
              {editingAccount ? 'Update' : 'Create'}
            </Button>
          </>
        }
      >
        <form className='space-y-4'>
          <Input
            label='Code'
            id='code'
            {...register('code')}
            error={errors.code?.message}
            placeholder='1000'
          />
          <Input
            label='Name'
            id='name'
            {...register('name')}
            error={errors.name?.message}
            placeholder='Cash'
          />
          <Select
            label='Account Type'
            id='account_type'
            {...register('account_type')}
            error={errors.account_type?.message}
            options={accountTypeOptions}
          />
          <Select
            label='Parent Account (optional)'
            id='parent_id'
            {...register('parent_id')}
            options={[
              { value: '', label: 'No parent' },
              ...(accounts?.items.map((a) => ({
                value: a.id.toString(),
                label: `${a.code} - ${a.name}`,
              })) || []),
            ]}
          />
          <Input
            label='Description (optional)'
            id='description'
            {...register('description')}
            error={errors.description?.message}
            placeholder='Account description...'
          />
        </form>
      </Modal>

      {/* Import CSV Modal */}
      <Modal
        isOpen={isImportModalOpen}
        onClose={() => setIsImportModalOpen(false)}
        title='Εισαγωγή Λογαριασμών από CSV'
      >
        <div className='space-y-4'>
          <p className='text-sm text-gray-600'>
            Επιλέξτε ένα αρχείο CSV με τις στήλες: <strong>code</strong>, <strong>name</strong>,{' '}
            <strong>account_type</strong>
          </p>
          <p className='text-sm text-gray-500'>
            Έγκυροι τύποι λογαριασμών: asset, liability, equity, revenue, expense
          </p>
          <div className='border-2 border-dashed border-gray-300 rounded-lg p-6 text-center'>
            <input
              ref={fileInputRef}
              type='file'
              accept='.csv'
              onChange={handleFileUpload}
              className='hidden'
              id='csv-upload'
            />
            <label htmlFor='csv-upload' className='cursor-pointer flex flex-col items-center gap-2'>
              <Upload className='h-8 w-8 text-gray-400' />
              <span className='text-sm text-gray-600'>Κάντε κλικ για να επιλέξετε αρχείο CSV</span>
            </label>
          </div>
          {importMutation.isPending && (
            <div className='flex items-center justify-center gap-2 text-sm text-gray-600'>
              <LoadingSpinner />
              <span>Εισαγωγή λογαριασμών...</span>
            </div>
          )}
        </div>
      </Modal>
    </div>
  )
}
