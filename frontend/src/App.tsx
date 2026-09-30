import * as React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './context/AuthContext';
import { ToastProvider } from './components/ui/toaster';
import { AppLayout, ProtectedRoute } from './components/layout/AppLayout';
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
const Integrity = React.lazy(() => import('./pages/Integrity'));
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

// Single-role application: the only human user is the Procurement Officer.
// The /app ProtectedRoute enforces authentication; no per-role route guards.
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
                  <Route path="dashboard" element={<Dashboard />} />
                  <Route path="tenders" element={<Tenders />} />
                  <Route path="tenders/create" element={<CreateTender />} />
                  <Route path="tenders/new" element={<CreateTender />} />
                  <Route path="tenders/:id" element={<TenderDetail />} />
                  <Route path="bids/:id" element={<BidDetail />} />
                  <Route path="bids/:bidId/report" element={<VerificationReport />} />
                  <Route path="inbox" element={<Inbox />} />
                  <Route path="integrity" element={<Integrity />} />
                  <Route path="documents" element={<Documents />} />
                  <Route path="documents/:id" element={<DocumentViewer />} />
                  <Route path="audit" element={<Audit />} />
                  <Route path="settings" element={<Settings />} />
                  <Route path="profile" element={<Profile />} />
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
