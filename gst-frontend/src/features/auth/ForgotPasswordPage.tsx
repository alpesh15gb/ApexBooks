import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Link } from 'react-router-dom';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { api } from '@/lib/api';
import { apiErrorToString } from '@/utils/validation';
import toast from 'react-hot-toast';
import { useState } from 'react';

const schema = z.object({ email: z.string().email('Enter a valid email') });

type Form = z.infer<typeof schema>;

export function ForgotPasswordPage() {
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);

  const { register, handleSubmit, formState: { errors } } = useForm<Form>({
    resolver: zodResolver(schema),
  });

  const onSubmit = async (data: Form) => {
    setLoading(true);
    try {
      await api.forgotPassword(data.email);
      setSent(true);
      toast.success('OTP sent to your email');
    } catch (err) {
      toast.error(apiErrorToString(err));
    } finally {
      setLoading(false);
    }
  };

  if (sent) {
    return (
      <div className="text-center py-4">
        <h2 className="text-lg font-semibold text-gray-900 mb-2">Check your email</h2>
        <p className="text-sm text-gray-600 mb-6">
          We've sent an OTP to your email. Please use it to reset your password.
        </p>
        <Link to="/reset-password" className="link text-sm">
          Enter OTP
        </Link>
      </div>
    );
  }

  return (
    <div>
      <h2 className="text-lg font-semibold text-gray-900 mb-2">Forgot password</h2>
      <p className="text-sm text-gray-600 mb-6">
        Enter your email and we'll send you an OTP to reset your password.
      </p>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <Input
          label="Email"
          type="email"
          placeholder="you@company.com"
          error={errors.email?.message}
          {...register('email')}
        />
        <Button type="submit" loading={loading} className="w-full">
          Send OTP
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-gray-500">
        Remember your password?{' '}
        <Link to="/login" className="link">
          Sign in
        </Link>
      </p>
    </div>
  );
}