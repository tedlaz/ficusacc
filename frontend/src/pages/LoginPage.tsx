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

const loginSchema = z.object({
  email: z.string().email('Invalid email address'),
  password: z.string().min(1, 'Password is required'),
})

type LoginFormData = z.infer<typeof loginSchema>

export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [isLoading, setIsLoading] = useState(false)

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
  })

  const onSubmit = async (data: LoginFormData) => {
    setIsLoading(true)
    try {
      await login(data)
      toast.success('Logged in successfully!')
      navigate('/')
    } catch (error) {
      const axiosError = error as AxiosError<ApiError>
      toast.error(axiosError.response?.data?.detail || 'Login failed')
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
          <p className='mt-2 text-gray-600'>Πολυεταιρικό λογιστικό σύστημα</p>
        </div>

        <Card>
          <h2 className='text-xl font-semibold text-gray-900 mb-6'>Είσοδος</h2>
          <form onSubmit={handleSubmit(onSubmit)} className='space-y-4'>
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
            <Button type='submit' className='w-full' isLoading={isLoading}>
              Είσοδος
            </Button>
          </form>
          <p className='mt-4 text-center text-sm text-gray-600'>
            Δεν έχετε λογαριασμό;{' '}
            <Link to='/register' className='text-blue-600 hover:text-blue-700 font-medium'>
              Δημιουργία Λογαριασμού
            </Link>
          </p>
        </Card>
      </div>
    </div>
  )
}
