import { forwardRef, type SelectHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  error?: string
  options: { value: string; label: string }[]
}

const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, label, error, options, id, ...props }, ref) => {
    return (
      <div className='w-full'>
        {label && (
          <label htmlFor={id} className='label'>
            {label}
          </label>
        )}
        <select id={id} ref={ref} className={cn(error ? 'input-error' : 'input', className)} {...props}>
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        {error && <p className='mt-1 text-sm text-red-600'>{error}</p>}
      </div>
    )
  }
)

Select.displayName = 'Select'

export { Select }
