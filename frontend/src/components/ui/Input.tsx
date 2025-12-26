import { forwardRef, type InputHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
}

const Input = forwardRef<HTMLInputElement, InputProps>(({ className, label, error, id, ...props }, ref) => {
  return (
    <div className='w-full'>
      {label && (
        <label htmlFor={id} className='label'>
          {label}
        </label>
      )}
      <input id={id} ref={ref} className={cn(error ? 'input-error' : 'input', className)} {...props} />
      {error && <p className='mt-1 text-sm text-red-600'>{error}</p>}
    </div>
  )
})

Input.displayName = 'Input'

export { Input }
