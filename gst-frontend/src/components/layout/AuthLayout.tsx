import { Outlet, Navigate } from 'react-router-dom';
import { useAuthStore } from '@/lib/store';

export function AuthLayout() {
  const { isAuthenticated, isLoading } = useAuthStore();

  if (isLoading) return null;

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4 py-12">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-brand-600 mb-4">
            <span className="text-white font-bold text-lg">AB</span>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">ApexBooks</h1>
          <p className="text-sm text-gray-500 mt-1">GST Accounting Engine</p>
        </div>
        <div className="card p-6">
          <Outlet />
        </div>
      </div>
    </div>
  );
}