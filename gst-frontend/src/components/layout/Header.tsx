import { Menu, Bell, LogOut, User } from 'lucide-react';
import { useAuthStore, useSidebarStore } from '@/lib/store';
import { Button } from '@/components/ui/Button';
import { useNavigate } from 'react-router-dom';
import { api, setAccessToken } from '@/lib/api';

export function Header() {
  const { user, logout } = useAuthStore();
  const { toggleMobile } = useSidebarStore();
  const navigate = useNavigate();

  const handleLogout = async () => {
    try {
      await api.logout();
    } catch {
      // ignore
    }
    setAccessToken(null);
    logout();
    navigate('/login');
  };

  return (
    <header className="sticky top-0 z-30 bg-white border-b border-gray-200">
      <div className="flex items-center justify-between px-4 h-16">
        <div className="flex items-center gap-3">
          <button
            onClick={toggleMobile}
            className="btn-ghost p-1.5 lg:hidden"
            aria-label="Open menu"
          >
            <Menu className="h-5 w-5" />
          </button>
          <div className="flex items-center gap-2 lg:hidden">
            <div className="w-7 h-7 rounded-lg bg-brand-600 flex items-center justify-center">
              <span className="text-white font-bold text-xs">AB</span>
            </div>
            <span className="font-semibold text-gray-900">ApexBooks</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button className="btn-ghost p-1.5 relative" aria-label="Notifications">
            <Bell className="h-5 w-5" />
            <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-red-500" />
          </button>

          <div className="flex items-center gap-2 pl-2 border-l border-gray-200">
            <div className="hidden sm:block text-right">
              <p className="text-sm font-medium text-gray-700 leading-tight">
                {user?.full_name || 'User'}
              </p>
              <p className="text-xs text-gray-500">{user?.email || ''}</p>
            </div>
            <div className="w-8 h-8 rounded-full bg-brand-100 flex items-center justify-center">
              <User className="h-4 w-4 text-brand-600" />
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleLogout}
              aria-label="Logout"
            >
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    </header>
  );
}
