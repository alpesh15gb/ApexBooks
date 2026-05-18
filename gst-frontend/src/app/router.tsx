import { createBrowserRouter, Navigate } from 'react-router-dom';
import { AppLayout } from '@/components/layout/AppLayout';
import { AuthLayout } from '@/components/layout/AuthLayout';
import { LoginPage } from '@/features/auth/LoginPage';
import { RegisterPage } from '@/features/auth/RegisterPage';
import { ForgotPasswordPage } from '@/features/auth/ForgotPasswordPage';
import { ResetPasswordPage } from '@/features/auth/ResetPasswordPage';
import { DashboardPage } from '@/features/dashboard/DashboardPage';
import { PartiesPage } from '@/features/parties/PartiesPage';
import { PartyDetailPage } from '@/features/parties/PartyDetailPage';
import { ItemsPage } from '@/features/items/ItemsPage';
import { InvoicesPage } from '@/features/invoices/InvoicesPage';
import { InvoiceFormPage } from '@/features/invoices/InvoiceFormPage';
import { InvoiceDetailPage } from '@/features/invoices/InvoiceDetailPage';
import { PaymentsPage } from '@/features/payments/PaymentsPage';
import { JournalPage } from '@/features/journal/JournalPage';
import { AccountsPage } from '@/features/accounts/AccountsPage';
import { ReportsPage } from '@/features/reports/ReportsPage';
import { GstPage } from '@/features/gst/GstPage';
import { SettingsPage } from '@/features/settings/SettingsPage';
import { AdminPage } from '@/features/admin/AdminPage';
import { ImportsPage } from '@/features/imports/ImportsPage';
import { lazy } from 'react';

// Code-split heavier routes
const ReportsPageLazy = lazy(() => import('@/features/reports/ReportsPage').then(m => ({ default: m.ReportsPage })));
const GstPageLazy = lazy(() => import('@/features/gst/GstPage').then(m => ({ default: m.GstPage })));
const SettingsPageLazy = lazy(() => import('@/features/settings/SettingsPage').then(m => ({ default: m.SettingsPage })));
const AdminPageLazy = lazy(() => import('@/features/admin/AdminPage').then(m => ({ default: m.AdminPage })));

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AuthLayout />,
    children: [
      { index: true, element: <Navigate to="/login" replace /> },
      { path: 'login', element: <LoginPage /> },
      { path: 'register', element: <RegisterPage /> },
      { path: 'forgot-password', element: <ForgotPasswordPage /> },
      { path: 'reset-password', element: <ResetPasswordPage /> },
    ],
  },
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      { path: 'dashboard', element: <DashboardPage /> },
      { path: 'parties', element: <PartiesPage /> },
      { path: 'parties/:id', element: <PartyDetailPage /> },
      { path: 'items', element: <ItemsPage /> },
      { path: 'invoices/:kind', element: <InvoicesPage /> },
      { path: 'invoices/:kind/new', element: <InvoiceFormPage /> },
      { path: 'invoices/:kind/:id/edit', element: <InvoiceFormPage /> },
      { path: 'invoices/:kind/:id', element: <InvoiceDetailPage /> },
      { path: 'payments', element: <PaymentsPage /> },
      { path: 'journal', element: <JournalPage /> },
      { path: 'accounts', element: <AccountsPage /> },
      { path: 'reports', element: <ReportsPageLazy /> },
      { path: 'gst', element: <GstPageLazy /> },
      { path: 'settings', element: <SettingsPageLazy /> },
      { path: 'admin', element: <AdminPageLazy /> },
      { path: 'import', element: <ImportsPage /> },
    ],
  },
]);