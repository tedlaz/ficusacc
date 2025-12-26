import { X } from 'lucide-react'
import { type ReactNode, useEffect } from 'react'
import { Button } from './Button'

interface ModalProps {
  isOpen: boolean
  onClose: () => void
  title: string
  children: ReactNode
  footer?: ReactNode
  closeOnOutsideClick?: boolean
}

export function Modal({ isOpen, onClose, title, children, footer, closeOnOutsideClick = true }: ModalProps) {
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }

    if (isOpen) {
      document.addEventListener('keydown', handleEscape)
      document.body.style.overflow = 'hidden'
    }

    return () => {
      document.removeEventListener('keydown', handleEscape)
      document.body.style.overflow = 'unset'
    }
  }, [isOpen, onClose])

  if (!isOpen) return null

  return (
    <div className='fixed inset-0 z-50 overflow-y-auto'>
      <div className='flex min-h-screen items-center justify-center p-4'>
        <div className='fixed inset-0 bg-black bg-opacity-50 transition-opacity' onClick={closeOnOutsideClick ? onClose : undefined} />
        <div className='relative z-10 w-full max-w-lg rounded-xl bg-white shadow-xl'>
          <div className='flex items-center justify-between border-b border-gray-200 p-4'>
            <h2 className='text-lg font-semibold text-gray-900'>{title}</h2>
            <Button variant='secondary' onClick={onClose} className='p-1!'>
              <X className='h-5 w-5' />
            </Button>
          </div>
          <div className='p-4'>{children}</div>
          {footer && <div className='flex justify-end gap-2 border-t border-gray-200 p-4'>{footer}</div>}
        </div>
      </div>
    </div>
  )
}
