import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Link, useNavigate } from 'react-router-dom';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { api } from '@/lib/api';
import { apiErrorToString } from '@/utils/validation';
import { passwordHelperText, validatePassword } from '@/utils/password';
import toast from 'react-hot-toast';
import { useState } from 'react';

const strongPasswordSchema = z.string().superRefine((value, ctx) => {
  const error = validatePassword(value);
  if (error) ctx.addIssue({ code: z.ZodIssueCode.custom, message: error });
});

const schema = z.object({
  email: z.string().email('Enter a valid email'),
  otp: z.string().min(6, 'Enter the OTP sent to your email'),
  new_password: strongPasswordSchema,
});

type Form = z.infer<typeof schema>;

export function ResetPasswordPage() {
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const { register, handleSubmit, formState: { errors } } = useForm<Form>({
    resolver: zodResolver(schema),
  });

  const onSubmit = async (data: Form) => {
    setLoading(true);
    try {
      await api.resetPassword({
        email: data.email,
        otp: data.otp,
        new_password: data.new_password,
      });
      toast.success('Password reset successfully! Please sign in.');
      navigate('/login');
    } catch (err) {
      toast.error(apiErrorToString(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h2 className="text-lg font-semibold text-gray-900 mb-6">Reset password</h2>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <Input
          label="Email"
          type="email"
          placeholder="you@company.com"
          error={errors.email?.message}
          {...register('email')}
        />
        <Input
          label="OTP"
          placeholder="Enter the OTP"
          error={errors.otp?.message}
          {...register('otp')}
        />
        <Input
          label="New Password"
          type="password"
          placeholder="8+ chars, Aa, 0-9, special"
          helperText={passwordHelperText}
          error={errors.new_password?.message}
          {...register('new_password')}
        />
        <Button type="submit" loading={loading} className="w-full">
          Reset password
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-gray-500">
        <Link to="/login" className="link">
          Back to sign in
        </Link>
      </p>
    </div>
  );
}
