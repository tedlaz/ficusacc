import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm, useFieldArray } from 'react-hook-form'
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
import { formatCurrency, formatDate } from '@/lib/utils'
import { Plus, Trash2, Check, X, Pencil, Undo2, Eye } from 'lucide-react'
import toast from 'react-hot-toast'
import { format } from 'date-fns'
import type { Transaction, TransactionCreate, TransactionUpdate } from '@/types'
import type { AxiosError } from 'axios'
import type { ApiError } from '@/types'
import { useAuth } from '@/contexts'

const lineSchema = z.object({
  account_id: z.string().min(1, 'Απαιτείται λογαριασμός'),
  amount: z.string().min(1, 'Απαιτείται Ποσό'),
  description: z.string().optional(),
})

const transactionSchema = z.object({
  transaction_date: z.string().min(1, 'Απαιτείται Ημερομηνία'),
  description: z.string().min(1, 'Απαιτείται Περιγραφή'),
  reference: z.string().optional(),
  lines: z.array(lineSchema).min(2, 'Απαιτούνται τουλάχιστον 2 γραμμές'),
})

type TransactionFormData = z.infer<typeof transactionSchema>

export function TransactionsPage() {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const hasCompany = !!user?.companyId
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingTransaction, setEditingTransaction] = useState<Transaction | null>(null)
  const [viewingTransaction, setViewingTransaction] = useState<Transaction | null>(null)

  const { data: transactions, isLoading } = useQuery({
    queryKey: ['transactions'],
    queryFn: () => api.getTransactions(),
    enabled: hasCompany,
  })

  const { data: accounts } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => api.getChartOfAccounts(),
    enabled: hasCompany,
  })

  const {
    register,
    handleSubmit,
    control,
    reset,
    watch,
    formState: { errors },
  } = useForm<TransactionFormData>({
    resolver: zodResolver(transactionSchema),
    defaultValues: {
      lines: [
        { account_id: '', amount: '', description: '' },
        { account_id: '', amount: '', description: '' },
      ],
    },
  })

  const { fields, append, remove } = useFieldArray({
    control,
    name: 'lines',
  })

  const watchedLines = watch('lines')

  const createMutation = useMutation({
    mutationFn: (data: TransactionCreate) => api.createTransaction(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transactions'] })
      toast.success('Transaction created successfully')
      closeModal()
    },
    onError: (error: AxiosError<ApiError>) => {
      toast.error(error.response?.data?.detail || 'Failed to create transaction')
    },
  })

  const postMutation = useMutation({
    mutationFn: (id: number) => api.postTransaction(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transactions'] })
      toast.success('Transaction posted successfully')
    },
    onError: (error: AxiosError<ApiError>) => {
      toast.error(error.response?.data?.detail || 'Failed to post transaction')
    },
  })

  const unpostMutation = useMutation({
    mutationFn: (id: number) => api.unpostTransaction(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transactions'] })
      toast.success('Transaction unposted successfully')
    },
    onError: (error: AxiosError<ApiError>) => {
      toast.error(error.response?.data?.detail || 'Failed to unpost transaction')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.deleteTransaction(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transactions'] })
      toast.success('Transaction deleted successfully')
    },
    onError: (error: AxiosError<ApiError>) => {
      toast.error(error.response?.data?.detail || 'Failed to delete transaction')
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: TransactionUpdate }) => api.updateTransaction(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transactions'] })
      toast.success('Transaction updated successfully')
      closeModal()
    },
    onError: (error: AxiosError<ApiError>) => {
      toast.error(error.response?.data?.detail || 'Failed to update transaction')
    },
  })

  const openCreateModal = () => {
    setEditingTransaction(null)
    reset({
      transaction_date: format(new Date(), 'yyyy-MM-dd'),
      description: '',
      reference: '',
      lines: [
        { account_id: '', amount: '', description: '' },
        { account_id: '', amount: '', description: '' },
      ],
    })
    setIsModalOpen(true)
  }

  const openEditModal = (transaction: Transaction) => {
    setEditingTransaction(transaction)
    reset({
      transaction_date: transaction.transaction_date,
      description: transaction.description,
      reference: transaction.reference || '',
      lines: transaction.lines.map((line) => ({
        account_id: line.account_id.toString(),
        amount: line.amount.toString(),
        description: line.description || '',
      })),
    })
    setIsModalOpen(true)
  }

  const closeModal = () => {
    setIsModalOpen(false)
    setEditingTransaction(null)
    reset()
  }

  const onSubmit = (data: TransactionFormData) => {
    const lines = data.lines.map((line) => ({
      account_id: parseInt(line.account_id),
      amount: line.amount,
      description: line.description || null,
    }))

    if (editingTransaction) {
      const updateData: TransactionUpdate = {
        transaction_date: data.transaction_date,
        description: data.description,
        reference: data.reference || null,
        lines,
      }
      updateMutation.mutate({ id: editingTransaction.id, data: updateData })
    } else {
      const transactionData: TransactionCreate = {
        transaction_date: data.transaction_date,
        description: data.description,
        reference: data.reference || null,
        lines,
      }
      createMutation.mutate(transactionData)
    }
  }

  const handlePost = (transaction: Transaction) => {
    if (confirm('Are you sure you want to post this transaction? Posted transactions cannot be edited.')) {
      postMutation.mutate(transaction.id)
    }
  }

  const handleUnpost = (transaction: Transaction) => {
    if (confirm('Are you sure you want to unpost this transaction? It will become editable again.')) {
      unpostMutation.mutate(transaction.id)
    }
  }

  const handleDelete = (transaction: Transaction) => {
    if (confirm(`Are you sure you want to delete this transaction?`)) {
      deleteMutation.mutate(transaction.id)
    }
  }

  const handleView = (transaction: Transaction) => {
    setViewingTransaction(transaction)
  }

  const getAccountName = (accountId: number) => {
    const account = accounts?.items.find((a) => a.id === accountId)
    return account ? `${account.code} - ${account.name}` : `Account #${accountId}`
  }

  // Calculate total debits and credits
  const totalDebits = watchedLines
    .filter((line) => parseFloat(line.amount || '0') > 0)
    .reduce((sum, line) => sum + parseFloat(line.amount || '0'), 0)

  const totalCredits = watchedLines
    .filter((line) => parseFloat(line.amount || '0') < 0)
    .reduce((sum, line) => sum + Math.abs(parseFloat(line.amount || '0')), 0)

  const isBalanced = Math.abs(totalDebits - totalCredits) < 0.01

  const accountOptions = [
    { value: '', label: 'Επιλογή Λογαριασμού...' },
    ...(accounts?.items.map((a) => ({
      value: a.id.toString(),
      label: `${a.code} - ${a.name}`,
    })) || []),
  ]

  if (!hasCompany) {
    return (
      <div>
        <h1 className='text-xl sm:text-2xl font-bold text-gray-900 mb-6'>Κινήσεις</h1>
        <Card>
          <p className='text-gray-600 text-center py-8'>
            Παρακαλώ επιλέξτε ή δημιουργήστε μια εταιρεία για να δείτε τις κινήσεις.
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
          <h1 className='text-xl sm:text-2xl font-bold text-gray-900'>Κινήσεις</h1>
          <p className='text-sm sm:text-base text-gray-600'>Διαχείρηση εγγραφών ημερολογίου</p>
        </div>
        <Button onClick={openCreateModal} className='w-full sm:w-auto'>
          <Plus className='h-4 w-4 mr-2' />
          Νέα Εγγραφή
        </Button>
      </div>

      {/* Mobile Card View */}
      <div className='block lg:hidden space-y-4'>
        {transactions?.items.map((transaction) => (
          <Card key={transaction.id}>
            <div className='flex justify-between items-start'>
              <div className='flex-1 min-w-0'>
                <div className='flex items-center gap-2 mb-1'>
                  <span className='text-sm text-gray-500'>{formatDate(transaction.transaction_date)}</span>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full ${
                      transaction.is_posted ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'
                    }`}
                  >
                    {transaction.is_posted ? 'Posted' : 'Draft'}
                  </span>
                </div>
                <p className='font-medium text-gray-900'>{transaction.description}</p>
                <div className='flex items-center gap-2 mt-1 text-sm text-gray-500'>
                  {transaction.reference && <span>Ref: {transaction.reference}</span>}
                  <span className='font-medium text-gray-700'>
                    {formatCurrency(
                      transaction.lines
                        .filter((line) => parseFloat(line.amount) > 0)
                        .reduce((sum, line) => sum + parseFloat(line.amount), 0)
                    )}
                  </span>
                </div>
              </div>
              {!transaction.is_posted && (
                <div className='flex gap-2 ml-2'>
                  <Button
                    variant='secondary'
                    onClick={() => openEditModal(transaction)}
                    className='p-2!'
                    title='Edit transaction'
                  >
                    <Pencil className='h-4 w-4' />
                  </Button>
                  <Button
                    variant='success'
                    onClick={() => handlePost(transaction)}
                    className='p-2!'
                    title='Post transaction'
                  >
                    <Check className='h-4 w-4' />
                  </Button>
                  <Button variant='danger' onClick={() => handleDelete(transaction)} className='p-2!'>
                    <Trash2 className='h-4 w-4' />
                  </Button>
                </div>
              )}
              {transaction.is_posted && (
                <div className='flex gap-2 ml-2'>
                  <Button
                    variant='secondary'
                    onClick={() => handleView(transaction)}
                    className='p-2!'
                    title='View transaction'
                  >
                    <Eye className='h-4 w-4' />
                  </Button>
                  <Button
                    variant='secondary'
                    onClick={() => handleUnpost(transaction)}
                    className='p-2!'
                    title='Unpost transaction'
                  >
                    <Undo2 className='h-4 w-4' />
                  </Button>
                </div>
              )}
            </div>
          </Card>
        ))}
        {transactions?.items.length === 0 && (
          <Card>
            <p className='text-center text-gray-500 py-4'>
              No transactions found. Create your first transaction.
            </p>
          </Card>
        )}
      </div>

      {/* Desktop Table View */}
      <Card className='hidden lg:block'>
        <Table>
          <TableHead>
            <TableRow>
              <TableHeader>Ημ/νια</TableHeader>
              <TableHeader>Περιγραφη</TableHeader>
              <TableHeader>Σχετικο</TableHeader>
              <TableHeader className='text-right'>Ποσο</TableHeader>
              <TableHeader>Κατάσταση</TableHeader>
              <TableHeader className='text-right'>Ενεργειες</TableHeader>
            </TableRow>
          </TableHead>
          <TableBody>
            {transactions?.items.map((transaction) => (
              <TableRow key={transaction.id}>
                <TableCell>{formatDate(transaction.transaction_date)}</TableCell>
                <TableCell className='font-medium'>{transaction.description}</TableCell>
                <TableCell className='text-gray-500'>{transaction.reference || '-'}</TableCell>
                <TableCell className='text-right font-medium'>
                  {formatCurrency(
                    transaction.lines
                      .filter((line) => parseFloat(line.amount) > 0)
                      .reduce((sum, line) => sum + parseFloat(line.amount), 0)
                  )}
                </TableCell>
                <TableCell>
                  <span
                    className={`text-xs px-2 py-1 rounded-full ${
                      transaction.is_posted ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'
                    }`}
                  >
                    {transaction.is_posted ? 'Posted' : 'Draft'}
                  </span>
                </TableCell>
                <TableCell className='text-right'>
                  <div className='flex justify-end gap-2'>
                    {!transaction.is_posted && (
                      <>
                        <Button
                          variant='secondary'
                          onClick={() => openEditModal(transaction)}
                          className='p-2!'
                          title='Edit transaction'
                        >
                          <Pencil className='h-4 w-4' />
                        </Button>
                        <Button
                          variant='success'
                          onClick={() => handlePost(transaction)}
                          className='p-2!'
                          title='Post transaction'
                        >
                          <Check className='h-4 w-4' />
                        </Button>
                        <Button variant='danger' onClick={() => handleDelete(transaction)} className='p-2!'>
                          <Trash2 className='h-4 w-4' />
                        </Button>
                      </>
                    )}
                    {transaction.is_posted && (
                      <>
                        <Button
                          variant='secondary'
                          onClick={() => handleView(transaction)}
                          className='p-2!'
                          title='View transaction'
                        >
                          <Eye className='h-4 w-4' />
                        </Button>
                        <Button
                          variant='secondary'
                          onClick={() => handleUnpost(transaction)}
                          className='p-2!'
                          title='Unpost transaction'
                        >
                          <Undo2 className='h-4 w-4' />
                        </Button>
                      </>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {transactions?.items.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className='text-center text-gray-500 py-8'>
                  No transactions found. Create your first transaction.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>

      <Modal
        isOpen={isModalOpen}
        onClose={closeModal}
        title={editingTransaction ? 'Επεξεργασία Εγγραφής' : 'Νέα Εγγραφή'}
        footer={
          <>
            <Button variant='secondary' onClick={closeModal}>
              Ακύρωση
            </Button>
            <Button
              onClick={handleSubmit(onSubmit)}
              isLoading={createMutation.isPending || updateMutation.isPending}
              disabled={!isBalanced}
            >
              Αποθήκευση
            </Button>
          </>
        }
      >
        <form className='space-y-4'>
          <div className='grid grid-cols-2 gap-4'>
            <Input
              label='Ημερομηνία'
              type='date'
              id='transaction_date'
              {...register('transaction_date')}
              error={errors.transaction_date?.message}
            />
            <Input
              label='Σχετικό'
              id='reference'
              {...register('reference')}
              error={errors.reference?.message}
              placeholder='ΤΔΑ-001'
            />
          </div>
          <Input
            label='Περιγραφή'
            id='description'
            {...register('description')}
            error={errors.description?.message}
            placeholder='Περιγραφή Εγγραφής...'
          />

          <div className='space-y-2'>
            <div className='flex items-center justify-between'>
              <label className='label'>Αναλυτικές Γραμμές</label>
              <Button
                type='button'
                variant='secondary'
                onClick={() => append({ account_id: '', amount: '', description: '' })}
                className='py-1! px-2! text-xs'
              >
                <Plus className='h-3 w-3 mr-1' />
                Νέα Γραμμή
              </Button>
            </div>

            <div className='space-y-2 max-h-60 overflow-y-auto'>
              {fields.map((field, index) => (
                <div key={field.id} className='flex gap-2 items-start'>
                  <div className='flex-1'>
                    <Select
                      {...register(`lines.${index}.account_id`)}
                      options={accountOptions}
                      error={errors.lines?.[index]?.account_id?.message}
                    />
                  </div>
                  <div className='w-28'>
                    <Input
                      {...register(`lines.${index}.amount`)}
                      placeholder='100.00'
                      error={errors.lines?.[index]?.amount?.message}
                    />
                  </div>
                  {fields.length > 2 && (
                    <Button type='button' variant='secondary' onClick={() => remove(index)} className='p-2!'>
                      <X className='h-4 w-4' />
                    </Button>
                  )}
                </div>
              ))}
            </div>

            <p className='text-xs text-gray-500'>
              Θετικές τιμές είναι χρεώσεις, αρνητικές τιμές είναι πιστώσεις.
            </p>
          </div>

          <div className='flex justify-between p-3 bg-gray-50 rounded-lg'>
            <div className='text-sm'>
              <span className='text-gray-600'>Χρεώσεις: </span>
              <span className='font-medium text-gray-900'>{formatCurrency(totalDebits)}</span>
            </div>
            <div className='text-sm'>
              <span className='text-gray-600'>Πιστώσεις: </span>
              <span className='font-medium text-gray-900'>{formatCurrency(totalCredits)}</span>
            </div>
            <div className={`text-sm font-medium ${isBalanced ? 'text-green-600' : 'text-red-600'}`}>
              {isBalanced ? '✓ Balanced' : '✗ Not balanced'}
            </div>
          </div>
        </form>
      </Modal>

      {/* View Transaction Modal */}
      <Modal
        isOpen={!!viewingTransaction}
        onClose={() => setViewingTransaction(null)}
        title='Προβολή Εγγραφής'
        footer={
          <Button variant='secondary' onClick={() => setViewingTransaction(null)}>
            Κλείσιμο
          </Button>
        }
      >
        {viewingTransaction && (
          <div className='space-y-4'>
            <div className='grid grid-cols-2 gap-4'>
              <div>
                <label className='text-sm text-gray-500'>Ημερομηνία</label>
                <p className='font-medium'>{formatDate(viewingTransaction.transaction_date)}</p>
              </div>
              <div>
                <label className='text-sm text-gray-500'>Σχετικό</label>
                <p className='font-medium'>{viewingTransaction.reference || '-'}</p>
              </div>
            </div>
            <div>
              <label className='text-sm text-gray-500'>Περιγραφή</label>
              <p className='font-medium'>{viewingTransaction.description}</p>
            </div>
            <div>
              <label className='text-sm text-gray-500 block mb-2'>Γραμμές Εγγραφής</label>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableHeader>Λογαριασμός</TableHeader>
                    <TableHeader className='text-right'>Χρέωση</TableHeader>
                    <TableHeader className='text-right'>Πίστωση</TableHeader>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {viewingTransaction.lines.map((line) => (
                    <TableRow key={line.id}>
                      <TableCell>{getAccountName(line.account_id)}</TableCell>
                      <TableCell className='text-right'>
                        {parseFloat(line.amount) > 0 ? formatCurrency(parseFloat(line.amount)) : ''}
                      </TableCell>
                      <TableCell className='text-right'>
                        {parseFloat(line.amount) < 0 ? formatCurrency(Math.abs(parseFloat(line.amount))) : ''}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <div className='flex justify-between p-3 bg-gray-50 rounded-lg'>
              <div className='text-sm'>
                <span className='text-gray-600'>Σύνολο Χρεώσεων: </span>
                <span className='font-medium text-gray-900'>
                  {formatCurrency(
                    viewingTransaction.lines
                      .filter((l) => parseFloat(l.amount) > 0)
                      .reduce((sum, l) => sum + parseFloat(l.amount), 0)
                  )}
                </span>
              </div>
              <div className='text-sm'>
                <span className='text-gray-600'>Σύνολο Πιστώσεων: </span>
                <span className='font-medium text-gray-900'>
                  {formatCurrency(
                    viewingTransaction.lines
                      .filter((l) => parseFloat(l.amount) < 0)
                      .reduce((sum, l) => sum + Math.abs(parseFloat(l.amount)), 0)
                  )}
                </span>
              </div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
