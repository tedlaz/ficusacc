import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

interface CardProps {
  children: ReactNode
  className?: string
  title?: string
  actions?: ReactNode
}

export function Card({ children, className, title, actions }: CardProps) {
  return (
    <div className={cn('card', className)}>
      {(title || actions) && (
        <div className='flex items-center justify-between mb-4'>
          {title && <h3 className='text-lg font-semibold text-gray-900'>{title}</h3>}
          {actions && <div className='flex items-center gap-2'>{actions}</div>}
        </div>
      )}
      {children}
    </div>
  )
}
