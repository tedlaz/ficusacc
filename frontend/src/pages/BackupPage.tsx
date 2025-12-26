import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Button, Card, LoadingSpinner, Modal } from '@/components/ui'
import { Download, Upload, Trash2, RefreshCw, HardDrive, Clock } from 'lucide-react'
import toast from 'react-hot-toast'
import { format } from 'date-fns'
import { el } from 'date-fns/locale'
import { useAuth } from '@/contexts'
import type { AxiosError } from 'axios'
import type { ApiError } from '@/types'

interface BackupInfo {
  filename: string
  created_at: string
  size_bytes: number
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 Bytes'
  const k = 1024
  const sizes = ['Bytes', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

export function BackupPage() {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const [isRestoreModalOpen, setIsRestoreModalOpen] = useState(false)
  const [selectedBackup, setSelectedBackup] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { data: backupsData, isLoading } = useQuery({
    queryKey: ['backups'],
    queryFn: () => api.listBackups(),
    enabled: !!user?.is_superuser,
  })

  const createBackupMutation = useMutation({
    mutationFn: () => api.createServerBackup(),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['backups'] })
      toast.success(`Αντίγραφο ασφαλείας δημιουργήθηκε: ${data.filename}`)
    },
    onError: (error: AxiosError<ApiError>) => {
      toast.error(error.response?.data?.detail || 'Αποτυχία δημιουργίας αντιγράφου')
    },
  })

  const downloadBackupMutation = useMutation({
    mutationFn: () => api.downloadBackup(),
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `accounting_backup_${format(new Date(), 'yyyyMMdd_HHmmss')}.db`
      link.click()
      URL.revokeObjectURL(url)
      toast.success('Λήψη αντιγράφου ασφαλείας ξεκίνησε')
    },
    onError: (error: AxiosError<ApiError>) => {
      toast.error(error.response?.data?.detail || 'Αποτυχία λήψης αντιγράφου')
    },
  })

  const restoreFromServerMutation = useMutation({
    mutationFn: (filename: string) => api.restoreFromServerBackup(filename),
    onSuccess: (data) => {
      toast.success(data.message)
      setSelectedBackup(null)
      // Invalidate all queries since data has changed
      queryClient.invalidateQueries()
    },
    onError: (error: AxiosError<ApiError>) => {
      toast.error(error.response?.data?.detail || 'Αποτυχία επαναφοράς')
    },
  })

  const restoreFromUploadMutation = useMutation({
    mutationFn: (file: File) => api.restoreFromUpload(file),
    onSuccess: (data) => {
      toast.success(data.message)
      setIsRestoreModalOpen(false)
      queryClient.invalidateQueries()
    },
    onError: (error: AxiosError<ApiError>) => {
      toast.error(error.response?.data?.detail || 'Αποτυχία επαναφοράς')
    },
  })

  const deleteBackupMutation = useMutation({
    mutationFn: (filename: string) => api.deleteBackup(filename),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['backups'] })
      toast.success('Αντίγραφο διαγράφηκε')
    },
    onError: (error: AxiosError<ApiError>) => {
      toast.error(error.response?.data?.detail || 'Αποτυχία διαγραφής')
    },
  })

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (file) {
      if (
        confirm(
          'Είστε σίγουροι ότι θέλετε να επαναφέρετε τη βάση δεδομένων από αυτό το αρχείο; Αυτή η ενέργεια θα αντικαταστήσει όλα τα υπάρχοντα δεδομένα!'
        )
      ) {
        restoreFromUploadMutation.mutate(file)
      }
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const handleRestoreFromServer = (filename: string) => {
    if (
      confirm(
        'Είστε σίγουροι ότι θέλετε να επαναφέρετε τη βάση δεδομένων από αυτό το αντίγραφο; Αυτή η ενέργεια θα αντικαταστήσει όλα τα υπάρχοντα δεδομένα!'
      )
    ) {
      restoreFromServerMutation.mutate(filename)
    }
  }

  const handleDeleteBackup = (filename: string) => {
    if (confirm(`Είστε σίγουροι ότι θέλετε να διαγράψετε το αντίγραφο "${filename}";`)) {
      deleteBackupMutation.mutate(filename)
    }
  }

  if (!user?.is_superuser) {
    return (
      <div>
        <h1 className='text-xl sm:text-2xl font-bold text-gray-900 mb-6'>Αντίγραφα Ασφαλείας</h1>
        <Card>
          <p className='text-gray-600 text-center py-8'>
            Μόνο οι διαχειριστές έχουν πρόσβαση σε αυτήν τη σελίδα.
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
      <div className='mb-8'>
        <h1 className='text-2xl font-bold text-gray-900'>Αντίγραφα Ασφαλείας</h1>
        <p className='text-gray-600'>Δημιουργία και επαναφορά αντιγράφων ασφαλείας της βάσης δεδομένων</p>
      </div>

      {/* Action Buttons */}
      <Card className='mb-6'>
        <h2 className='text-lg font-semibold text-gray-900 mb-4'>Ενέργειες</h2>
        <div className='flex flex-wrap gap-3'>
          <Button onClick={() => createBackupMutation.mutate()} isLoading={createBackupMutation.isPending}>
            <HardDrive className='h-4 w-4 mr-2' />
            Δημιουργία Αντιγράφου στον Server
          </Button>
          <Button
            variant='secondary'
            onClick={() => downloadBackupMutation.mutate()}
            isLoading={downloadBackupMutation.isPending}
          >
            <Download className='h-4 w-4 mr-2' />
            Λήψη Αντιγράφου
          </Button>
          <Button variant='secondary' onClick={() => setIsRestoreModalOpen(true)}>
            <Upload className='h-4 w-4 mr-2' />
            Επαναφορά από Αρχείο
          </Button>
        </div>
      </Card>

      {/* Server Backups List */}
      <Card>
        <div className='flex items-center justify-between mb-4'>
          <h2 className='text-lg font-semibold text-gray-900'>Αντίγραφα στον Server</h2>
          <Button
            variant='secondary'
            onClick={() => queryClient.invalidateQueries({ queryKey: ['backups'] })}
          >
            <RefreshCw className='h-4 w-4' />
          </Button>
        </div>

        {backupsData?.backups.length === 0 ? (
          <p className='text-gray-500 text-center py-8'>Δεν υπάρχουν αντίγραφα ασφαλείας</p>
        ) : (
          <div className='space-y-3'>
            {backupsData?.backups.map((backup: BackupInfo) => (
              <div
                key={backup.filename}
                className='flex flex-col sm:flex-row sm:items-center justify-between p-4 bg-gray-50 rounded-lg gap-3'
              >
                <div className='flex-1 min-w-0'>
                  <p className='font-medium text-gray-900 truncate'>{backup.filename}</p>
                  <div className='flex items-center gap-4 text-sm text-gray-500'>
                    <span className='flex items-center gap-1'>
                      <Clock className='h-4 w-4' />
                      {format(new Date(backup.created_at), 'dd/MM/yyyy HH:mm', { locale: el })}
                    </span>
                    <span>{formatBytes(backup.size_bytes)}</span>
                  </div>
                </div>
                <div className='flex gap-2'>
                  <Button
                    variant='success'
                    onClick={() => handleRestoreFromServer(backup.filename)}
                    isLoading={restoreFromServerMutation.isPending && selectedBackup === backup.filename}
                  >
                    <RefreshCw className='h-4 w-4 mr-1' />
                    Επαναφορά
                  </Button>
                  <Button
                    variant='danger'
                    onClick={() => handleDeleteBackup(backup.filename)}
                    isLoading={deleteBackupMutation.isPending}
                  >
                    <Trash2 className='h-4 w-4' />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Upload Restore Modal */}
      <Modal
        isOpen={isRestoreModalOpen}
        onClose={() => setIsRestoreModalOpen(false)}
        title='Επαναφορά από Αρχείο'
      >
        <div className='space-y-4'>
          <div className='p-4 bg-yellow-50 border border-yellow-200 rounded-lg'>
            <p className='text-sm text-yellow-800'>
              <strong>Προσοχή:</strong> Η επαναφορά θα αντικαταστήσει όλα τα υπάρχοντα δεδομένα. Βεβαιωθείτε
              ότι έχετε δημιουργήσει αντίγραφο ασφαλείας πριν συνεχίσετε.
            </p>
          </div>
          <div className='border-2 border-dashed border-gray-300 rounded-lg p-6 text-center'>
            <input
              ref={fileInputRef}
              type='file'
              accept='.db'
              onChange={handleFileUpload}
              className='hidden'
              id='restore-upload'
            />
            <label htmlFor='restore-upload' className='cursor-pointer flex flex-col items-center gap-2'>
              <Upload className='h-8 w-8 text-gray-400' />
              <span className='text-sm text-gray-600'>Κάντε κλικ για να επιλέξετε αρχείο .db</span>
            </label>
          </div>
          {restoreFromUploadMutation.isPending && (
            <div className='flex items-center justify-center gap-2 text-sm text-gray-600'>
              <LoadingSpinner />
              <span>Επαναφορά βάσης δεδομένων...</span>
            </div>
          )}
        </div>
      </Modal>
    </div>
  )
}
