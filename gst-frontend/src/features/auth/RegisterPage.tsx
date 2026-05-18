import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Link, useNavigate } from 'react-router-dom';
import { Input, Select } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { api } from '@/lib/api';
import { apiErrorToString, STATE_CODES, BUSINESS_TYPES, REGISTRATION_TYPES } from '@/utils/validation';
import { passwordHelperText, validatePassword } from '@/utils/password';
import toast from 'react-hot-toast';
import { useState } from 'react';

const strongPasswordSchema = z.string().superRefine((value, ctx) => {
  const error = validatePassword(value);
  if (error) ctx.addIssue({ code: z.ZodIssueCode.custom, message: error });
});

const registerSchema = z.object({
  email: z.string().email('Enter a valid email'),
  password: strongPasswordSchema,
  full_name: z.string().min(1, 'Full name is required'),
  company_name: z.string().min(1, 'Company name is required'),
  gstin: z.string().min(15, 'Enter a valid GSTIN').max(15),
  pan: z.string().optional(),
  state_code: z.string().length(2, 'Select a state'),
  business_type: z.string().min(1, 'Select business type'),
  registration_type: z.string().optional(),
  address_line1: z.string().min(1, 'Address is required'),
  city: z.string().min(1, 'City is required'),
  pincode: z.string().min(6, 'Enter a valid pincode'),
});

type RegisterForm = z.infer<typeof registerSchema>;

export function RegisterPage() {
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterForm>({
    resolver: zodResolver(registerSchema),
    defaultValues: { registration_type: 'Regular' },
  });

  const onSubmit = async (data: RegisterForm) => {
    setLoading(true);
    try {
      await api.register({
        email: data.email,
        password: data.password,
        full_name: data.full_name,
        company: {
          company_name: data.company_name,
          gstin: data.gstin,
          pan: data.pan || undefined,
          state_code: data.state_code,
          business_type: data.business_type,
          registration_type: data.registration_type || 'Regular',
          address: {
            line1: data.address_line1,
            city: data.city,
            pincode: data.pincode,
            state_code: data.state_code,
          },
        },
      });
      toast.success('Account created successfully! Please sign in.');
      navigate('/login');
    } catch (err) {
      toast.error(apiErrorToString(err));
    } finally {
      setLoading(false);
    }
  };

  const stateOptions = Object.entries(STATE_CODES).map(([value, label]) => ({
    value,
    label: `${value} - ${label}`,
  }));

  return (
    <div>
      <h2 className="text-lg font-semibold text-gray-900 mb-6">Create your account</h2>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Input
            label="Full Name"
            placeholder="John Doe"
            error={errors.full_name?.message}
            {...register('full_name')}
          />
          <Input
            label="Email"
            type="email"
            placeholder="you@company.com"
            error={errors.email?.message}
            {...register('email')}
          />
        </div>
        <Input
          label="Password"
          type="password"
          placeholder="8+ chars, Aa, 0-9, special"
          helperText={passwordHelperText}
          error={errors.password?.message}
          {...register('password')}
        />
        <hr className="border-gray-200" />
        <Input
          label="Company Name"
          placeholder="Your Business Pvt Ltd"
          error={errors.company_name?.message}
          {...register('company_name')}
        />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Input
            label="GSTIN"
            placeholder="27AAAAA0000A1Z5"
            error={errors.gstin?.message}
            {...register('gstin')}
          />
          <Input
            label="PAN (optional)"
            placeholder="AAAAA0000A"
            error={errors.pan?.message}
            {...register('pan')}
          />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Select
            label="State"
            placeholder="Select state"
            options={stateOptions}
            error={errors.state_code?.message}
            {...register('state_code')}
          />
          <Select
            label="Business Type"
            placeholder="Select type"
            options={BUSINESS_TYPES.map((t) => ({ value: t, label: t }))}
            error={errors.business_type?.message}
            {...register('business_type')}
          />
        </div>
        <Select
          label="Registration Type"
          options={REGISTRATION_TYPES.map((t) => ({ value: t, label: t }))}
          {...register('registration_type')}
        />
        <Input
          label="Address"
          placeholder="Building, Street, Area"
          error={errors.address_line1?.message}
          {...register('address_line1')}
        />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Input
            label="City"
            placeholder="Mumbai"
            error={errors.city?.message}
            {...register('city')}
          />
          <Input
            label="Pincode"
            placeholder="400001"
            error={errors.pincode?.message}
            {...register('pincode')}
          />
        </div>
        <Button type="submit" loading={loading} className="w-full">
          Create account
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-gray-500">
        Already have an account?{' '}
        <Link to="/login" className="link">
          Sign in
        </Link>
      </p>
    </div>
  );
}
