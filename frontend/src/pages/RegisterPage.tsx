import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '@/contexts'
import { Button, Card, Input } from '@/components/ui'
import { BookOpen } from 'lucide-react'
import toast from 'react-hot-toast'
import type { AxiosError } from 'axios'
import type { ApiError } from '@/types'

const registerSchema = z.object({
  email: z.email('Invalid email address'),
  password: z.string().min(6, 'Password must be at least 6 characters'),
  full_name: z.string().min(1, 'Full name is required'),
  company_name: z.string().optional(),
})

type RegisterFormData = z.infer<typeof registerSchema>

export function RegisterPage() {
  const { register: registerUser } = useAuth()
  const navigate = useNavigate()
  const [isLoading, setIsLoading] = useState(false)

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterFormData>({
    resolver: zodResolver(registerSchema),
  })

  const onSubmit = async (data: RegisterFormData) => {
    setIsLoading(true)
    try {
      await registerUser({
        email: data.email,
        password: data.password,
        full_name: data.full_name,
        company_name: data.company_name?.trim() || undefined,
      })
      toast.success('Account created successfully!')
      navigate('/')
    } catch (error) {
      const axiosError = error as AxiosError<ApiError>
      toast.error(axiosError.response?.data?.detail || 'Registration failed')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className='min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4'>
      <div className='max-w-md w-full'>
        <div className='text-center mb-8'>
          <div className='flex justify-center'>
            <BookOpen className='h-12 w-12 text-blue-600' />
          </div>
          <h1 className='mt-4 text-3xl font-bold text-gray-900'>HomeAcct</h1>
          <p className='mt-2 text-gray-600'>Multi-tenant Accounting System</p>
        </div>

        <Card>
          <h2 className='text-xl font-semibold text-gray-900 mb-6'>Create Account</h2>
          <form onSubmit={handleSubmit(onSubmit)} className='space-y-4'>
            <Input
              label='Full Name'
              type='text'
              id='full_name'
              {...register('full_name')}
              error={errors.full_name?.message}
              placeholder='John Doe'
            />
            <Input
              label='Email'
              type='email'
              id='email'
              {...register('email')}
              error={errors.email?.message}
              placeholder='you@example.com'
            />
            <Input
              label='Password'
              type='password'
              id='password'
              {...register('password')}
              error={errors.password?.message}
              placeholder='••••••••'
            />
            <Input
              label='Company Name (optional)'
              type='text'
              id='company_name'
              {...register('company_name')}
              error={errors.company_name?.message}
              placeholder='My Company'
            />
            <Button type='submit' className='w-full' isLoading={isLoading}>
              Δημιουργία Λογαριασμού
            </Button>
          </form>
          <p className='mt-4 text-center text-sm text-gray-600'>
            Έχετε ήδη λογαριασμό;{' '}
            <Link to='/login' className='text-blue-600 hover:text-blue-700 font-medium'>
              Είσοδος
            </Link>
          </p>
        </Card>
      </div>
    </div>
  )
}
