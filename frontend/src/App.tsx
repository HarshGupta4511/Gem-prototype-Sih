import * as React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './context/AuthContext';
import { ToastProvider } from './components/ui/toaster';
import { AppLayout, ProtectedRoute } from './components/layout/AppLayout';
import type { Role } from './types';
import Login from './pages/Login';

// Lazily-loaded feature pages (built by page tracks)
const Dashboard = React.lazy(() => import('./pages/Dashboard'));
const Tenders = React.lazy(() => import('./pages/Tenders'));
const CreateTender = React.lazy(() => import('./pages/CreateTender'));
const Inbox = React.lazy(() => import('./pages/Inbox'));
const VerificationReport = React.lazy(() => import('./pages/VerificationReport'));
const TenderDetail = React.lazy(() => import('./pages/TenderDetail'));
const BidDetail = React.lazy(() => import('./pages/BidDetail'));
const Documents = React.lazy(() => import('./pages/Documents'));
const DocumentViewer = React.lazy(() => import('./pages/DocumentViewer'));
const Audit = React.lazy(() => import('./pages/Audit'));
const Settings = React.lazy(() => import('./pages/Settings'));
const Profile = React.lazy(() => import('./pages/Profile'));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function PageFallback() {
  return (
    <div className="flex items-center justify-center py-16 text-sm text-slate-500">
      <span className="mr-2 h-5 w-5 animate-spin rounded-full border-2 border-brand-700 border-t-transparent" />
      Loading page…
    </div>
  );
}

// Role sets for route guards (mirrors the navigation in AppLayout).
// STAFF_ROLES: procurement workflow pages. ADMIN is intentionally excluded —
// system administration stays separate from procurement decision authority.
const STAFF_ROLES: Role[] = ['PROCUREMENT_OFFICER', 'VERIFIER', 'AUDITOR'];
const AUDIT_ROLES: Role[] = ['PROCUREMENT_OFFICER', 'VERIFIER', 'AUDITOR', 'ADMIN'];
const OFFICER_ROLES: Role[] = ['PROCUREMENT_OFFICER'];
const ALL_ROLES: Role[] = ['PROCUREMENT_OFFICER', 'VERIFIER', 'AUDITOR', 'ADMIN'];

function Guard({ roles, children }: { roles: Role[]; children: React.ReactElement }) {
  return <ProtectedRoute roles={roles}>{children}</ProtectedRoute>;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <AuthProvider>
          <BrowserRouter>
            <React.Suspense fallback={<PageFallback />}>
              <Routes>
                <Route path="/" element={<Navigate to="/login" replace />} />
                <Route path="/login" element={<Login />} />
                <Route
                  path="/app"
                  element={
                    <ProtectedRoute>
                      <AppLayout />
                    </ProtectedRoute>
                  }
                >
                  <Route index element={<Navigate to="/app/dashboard" replace />} />
                  <Route path="dashboard" element={<Guard roles={ALL_ROLES}><Dashboard /></Guard>} />
                  <Route path="tenders" element={<Guard roles={STAFF_ROLES}><Tenders /></Guard>} />
                  <Route path="tenders/create" element={<Guard roles={OFFICER_ROLES}><CreateTender /></Guard>} />
                  <Route path="tenders/new" element={<Guard roles={OFFICER_ROLES}><CreateTender /></Guard>} />
                  <Route path="tenders/:id" element={<Guard roles={STAFF_ROLES}><TenderDetail /></Guard>} />
                  <Route path="bids/:id" element={<Guard roles={STAFF_ROLES}><BidDetail /></Guard>} />
                  <Route path="bids/:bidId/report" element={<Guard roles={['PROCUREMENT_OFFICER', 'VERIFIER', 'AUDITOR']}><VerificationReport /></Guard>} />
                  <Route path="inbox" element={<Guard roles={OFFICER_ROLES}><Inbox /></Guard>} />
                  <Route path="documents" element={<Guard roles={STAFF_ROLES}><Documents /></Guard>} />
                  <Route path="documents/:id" element={<Guard roles={STAFF_ROLES}><DocumentViewer /></Guard>} />
                  <Route path="audit" element={<Guard roles={AUDIT_ROLES}><Audit /></Guard>} />
                  <Route path="settings" element={<Guard roles={['ADMIN']}><Settings /></Guard>} />
                  <Route path="profile" element={<Guard roles={ALL_ROLES}><Profile /></Guard>} />
                </Route>
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </React.Suspense>
          </BrowserRouter>
        </AuthProvider>
      </ToastProvider>
    </QueryClientProvider>
  );
}
