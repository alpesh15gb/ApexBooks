import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard, Users, Building2, Package, FileText,
  Receipt, ArrowRightLeft, BookOpen, BarChart3, Settings,
  Shield, ClipboardList, ChevronLeft, X, Calculator,
  Banknote, FileSpreadsheet, Download,
} from 'lucide-react';
import clsx from 'clsx';
import { useSidebarStore } from '@/lib/store';

const navigation = [
  { label: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
  { label: 'Sales', href: '/invoices/sales', icon: FileText },
  { label: 'Purchases', href: '/invoices/purchase', icon: Receipt },
  { label: 'Customers', href: '/parties?type=Customer', icon: Users },
  { label: 'Vendors', href: '/parties?type=Vendor', icon: Building2 },
  { label: 'Items', href: '/items', icon: Package },
  { label: 'Payments', href: '/payments', icon: Banknote },
  { label: 'Journal', href: '/journal', icon: BookOpen },
  { label: 'Accounts', href: '/accounts', icon: Calculator },
  { label: 'GST', href: '/gst', icon: FileSpreadsheet },
  { label: 'Reports', href: '/reports', icon: BarChart3 },
  { label: 'Admin', href: '/admin', icon: Shield },
  { label: 'Import', href: '/import', icon: Download },
  { label: 'Settings', href: '/settings', icon: Settings },
];

export function Sidebar() {
  const { isOpen, toggle, isMobileOpen, closeMobile } = useSidebarStore();
  const location = useLocation();

  const linkClasses = ({ isActive }: { isActive: boolean }) =>
    clsx(
      'flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
      isActive
        ? 'bg-brand-50 text-brand-700'
        : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900',
    );

  const content = (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 h-16 border-b border-gray-200">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-brand-600 flex items-center justify-center">
            <span className="text-white font-bold text-sm">AB</span>
          </div>
          {isOpen && (
            <span className="font-semibold text-gray-900">ApexBooks</span>
          )}
        </div>
        <button
          onClick={isMobileOpen ? closeMobile : toggle}
          className="btn-ghost p-1.5 hidden lg:flex"
          aria-label={isOpen ? 'Collapse sidebar' : 'Expand sidebar'}
        >
          <ChevronLeft className={`h-4 w-4 transition-transform ${!isOpen && 'rotate-180'}`} />
        </button>
        <button
          onClick={closeMobile}
          className="btn-ghost p-1.5 lg:hidden"
          aria-label="Close sidebar"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto p-3 space-y-1 scrollbar-thin">
        {navigation.map((item) => (
          <NavLink
            key={item.href}
            to={item.href}
            end={item.href === '/dashboard'}
            onClick={closeMobile}
            className={linkClasses}
          >
            <item.icon className="h-5 w-5 shrink-0" />
            {isOpen && <span>{item.label}</span>}
          </NavLink>
        ))}
      </nav>

      {isOpen && (
        <div className="px-4 py-3 border-t border-gray-200">
          <p className="text-xs text-gray-400">GST API Engine v0.2</p>
        </div>
      )}
    </div>
  );

  return (
    <>
      {/* Desktop sidebar */}
      <aside
        className={clsx(
          'hidden lg:flex flex-col bg-white border-r border-gray-200 transition-all duration-200',
          isOpen ? 'w-60' : 'w-16',
        )}
      >
        {content}
      </aside>

      {/* Mobile sidebar overlay */}
      {isMobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/50" onClick={closeMobile} />
          <aside className="relative w-72 h-full bg-white shadow-xl">
            {content}
          </aside>
        </div>
      )}
    </>
  );
}