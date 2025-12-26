import type { ReactNode, TdHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

interface TableProps {
  children: ReactNode
  className?: string
}

interface TableCellProps extends TdHTMLAttributes<HTMLTableCellElement> {
  children: ReactNode
  className?: string
}

export function Table({ children, className }: TableProps) {
  return (
    <div className='overflow-x-auto'>
      <table className={cn('min-w-full divide-y divide-gray-200', className)}>{children}</table>
    </div>
  )
}

export function TableHead({ children }: { children: ReactNode }) {
  return <thead className='bg-gray-50'>{children}</thead>
}

export function TableBody({ children }: { children: ReactNode }) {
  return <tbody className='bg-white divide-y divide-gray-200'>{children}</tbody>
}

export function TableRow({ children, className }: TableProps) {
  return <tr className={cn('hover:bg-gray-50', className)}>{children}</tr>
}

export function TableHeader({ children, className }: TableProps) {
  return <th className={cn('table-header', className)}>{children}</th>
}

export function TableCell({ children, className, ...props }: TableCellProps) {
  return (
    <td className={cn('table-cell', className)} {...props}>
      {children}
    </td>
  )
}
