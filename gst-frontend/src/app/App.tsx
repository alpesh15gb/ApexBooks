import { RouterProvider } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'react-hot-toast';
import { useEffect, Suspense } from 'react';
import { api, getStoredAccessToken, setAccessToken } from '@/lib/api';
import { useAuthStore } from '@/lib/store';
import { Spinner } from '@/components/ui/Spinner';
import { router } from './router';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function AuthInitializer({ children }: { children: React.ReactNode }) {
  const { setUser, setLoading } = useAuthStore();

  useEffect(() => {
    const init = async () => {
      const token = getStoredAccessToken() || localStorage.getItem('apexbooks_access_token');
      if (token) {
        setAccessToken(token);
        try {
          const user = await api.getMe();
          setUser(user);
          return;
        } catch {
          const refreshRes = await fetch(`${import.meta.env.VITE_API_BASE_URL || '/api/v1'}/auth/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
          }).catch(() => null);

          if (refreshRes?.ok) {
            const data = await refreshRes.json();
            const refreshedToken = data?.data?.access_token || data?.access_token;
            if (refreshedToken) {
              setAccessToken(refreshedToken);
              const user = await api.getMe();
              setUser(user);
              return;
            }
          }

          setAccessToken(null);
          localStorage.removeItem('apexbooks_access_token');
          localStorage.removeItem('apexbooks_refresh_token');
        }
      }
      setLoading(false);
    };
    init();
  }, [setUser, setLoading]);

  return <>{children}</>;
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthInitializer>
        <Suspense
          fallback={
            <div className="flex items-center justify-center h-screen">
              <Spinner className="h-8 w-8 text-brand-600" />
            </div>
          }
        >
          <RouterProvider router={router} />
        </Suspense>
      </AuthInitializer>
      <Toaster
        position="top-right"
        toastOptions={{
          duration: 3000,
          style: { fontSize: '14px', borderRadius: '8px' },
        }}
      />
    </QueryClientProvider>
  );
}
