import * as React from 'react';
import { NavLink, Outlet, useNavigate, useLocation, Link } from 'react-router-dom';
import {
  LayoutDashboard,
  FileText,
  FileCheck,
  ScrollText,
  User as UserIcon,
  LogOut,
  Menu,
  X,
  Bell,
  ChevronRight,
  Settings,
  Scale,
  Inbox,
  ShieldAlert,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { useAuth } from '../../context/AuthContext';
import { ThemeToggle } from './ThemeToggle';
import { useQuery } from '@tanstack/react-query';
import { dashboardApi } from '../../lib/api';
import {
  notificationKey,
  useDismissedNotifications,
} from '../../lib/dismissedNotifications';

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string; strokeWidth?: number | string }>;
  badge?: boolean; // show unread-count badge (officer notifications)
}

// Single-role navigation: the only user is the Procurement Officer.
const PRIMARY_NAV: NavItem[] = [
  { to: '/app/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/app/tenders', label: 'Tenders', icon: FileText },
  { to: '/app/inbox', label: 'Notifications', icon: Inbox, badge: true },
  { to: '/app/documents', label: 'Test Your Document', icon: FileCheck },
  { to: '/app/integrity', label: 'Integrity', icon: ShieldAlert },
  { to: '/app/audit', label: 'Audit Trail', icon: ScrollText },
];

const ACCOUNT_NAV: NavItem[] = [
  { to: '/app/profile', label: 'Profile', icon: UserIcon },
  { to: '/app/settings', label: 'Settings', icon: Settings },
];

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const navigate = useNavigate();
  React.useEffect(() => {
    if (!isLoading && !isAuthenticated) navigate('/login', { replace: true });
  }, [isLoading, isAuthenticated, navigate]);
  if (isLoading) return null;
  if (!isAuthenticated) return null;
  return <>{children}</>;
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const onLogout = () => {
    logout();
    navigate('/login');
  };

  // Officer notifications unread count (work-queue items needing attention),
  // excluding items the officer dismissed.
  const { data: dashboard } = useQuery({
    queryKey: ['dashboard'],
    queryFn: dashboardApi.get,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
  const dismissed = useDismissedNotifications();
  const unreadCount = (dashboard?.work_queue ?? []).filter(
    (item) => !dismissed.has(notificationKey(item)),
  ).length;

  const primaryItems = PRIMARY_NAV;
  const accountItems = ACCOUNT_NAV;

  return (
    <div className="flex h-full flex-col justify-between bg-slate-900 text-slate-200">
      <div>
        {/* Brand identity header — clicking anywhere returns to the dashboard */}
        <Link
          to="/app/dashboard"
          className="block border-b border-slate-800/80 px-5 py-5 transition-colors hover:bg-slate-800/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
          aria-label="BIDWISE — go to dashboard"
        >
          <div className="flex items-center gap-3">
            <img
              src="/bidwise-mark.png"
              alt="BIDWISE logo"
              className="h-11 w-11 shrink-0 rounded-md shadow-sm"
              draggable={false}
            />
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-lg font-bold tracking-tight text-white font-serif">
                  BIDWISE
                </span>
                <span className="rounded bg-blue-500/20 px-1.5 py-0.2 text-[10px] font-semibold text-blue-300 border border-blue-400/30">
                  CPSE
                </span>
              </div>
              <p className="truncate text-[11px] font-medium text-slate-300">
                Smart &amp; Evidence-Based Bid Verification
              </p>
              <div className="mt-1 flex items-center gap-1.5">
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-400 ring-2 ring-emerald-400/20" />
                <span className="text-[10px] font-medium text-blue-300/90 tracking-wide uppercase">
                  AI-Assisted Bid Compliance
                </span>
              </div>
            </div>
          </div>
        </Link>

        {/* Primary Navigation */}
        <nav className="px-3 pt-4" aria-label="Primary">
          <p className="px-3 pb-2 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">
            Procurement Operations
          </p>
          <ul className="space-y-1">
            {primaryItems.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-3 rounded-md px-3 py-2 text-[13px] font-medium transition-colors',
                      isActive
                        ? 'bg-blue-600/30 text-white border-l-2 border-blue-400 shadow-sm'
                        : 'text-slate-300 hover:bg-slate-800/80 hover:text-white'
                    )
                  }
                >
                  <item.icon className="h-4 w-4 shrink-0 text-slate-400" />
                  <span className="flex-1">{item.label}</span>
                  {item.badge && unreadCount > 0 && (
                    <span className="ml-auto rounded-full bg-amber-500 px-1.5 py-0.5 text-[10px] font-bold text-white">
                      {unreadCount}
                    </span>
                  )}
                </NavLink>
              </li>
            ))}
          </ul>

          <div className="my-4 border-t border-slate-800" />

          {/* Account section */}
          <p className="px-3 pb-2 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">
            Account
          </p>
          <ul className="space-y-1">
            {accountItems.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-3 rounded-md px-3 py-2 text-[13px] font-medium transition-colors',
                      isActive
                        ? 'bg-blue-600/30 text-white border-l-2 border-blue-400 shadow-sm'
                        : 'text-slate-300 hover:bg-slate-800/80 hover:text-white'
                    )
                  }
                >
                  <item.icon className="h-4 w-4 shrink-0 text-slate-400" />
                  <span>{item.label}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </div>

      {/* Institutional mandate notice & Officer identity */}
      <div className="border-t border-slate-800 bg-slate-950/60 p-3.5">
        <div className="mb-3 rounded border border-blue-900/60 bg-blue-950/40 p-2.5 text-[11px] leading-relaxed text-blue-200/90">
          <div className="flex items-center gap-1.5 font-semibold text-blue-100 mb-1">
            <Scale className="h-3.5 w-3.5 text-blue-400" />
            <span>Statutory Mandate</span>
          </div>
          <p className="text-[10.5px] text-slate-300">
            AI verifies &amp; explains. Rules evaluate. The{' '}
            <strong className="text-white font-medium">Procurement Officer</strong> retains sole decision authority.
          </p>
        </div>

        <div className="flex items-center gap-3 rounded-md bg-slate-800/60 p-2 border border-slate-800">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-700 text-xs font-bold text-white shadow-inner">
            {user?.name?.charAt(0)?.toUpperCase() ?? 'O'}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-semibold text-white">{user?.name}</p>
            <p className="truncate text-[10px] font-medium text-slate-400">
              Procurement Officer
            </p>
          </div>
          <button
            onClick={onLogout}
            className="rounded p-1.5 text-slate-400 hover:bg-slate-700 hover:text-white transition-colors"
            title="Sign out of portal"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

export function AppLayout() {
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();

  // Bell badge: same dismissed-aware unread count as the sidebar.
  const { data: bellDashboard } = useQuery({
    queryKey: ['dashboard'],
    queryFn: dashboardApi.get,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
  const bellDismissed = useDismissedNotifications();
  const bellUnread = (bellDashboard?.work_queue ?? []).filter(
    (item) => !bellDismissed.has(notificationKey(item)),
  ).length;

  // Brief glow feedback when the bell is clicked.
  const [bellGlow, setBellGlow] = React.useState(false);
  const glowTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  React.useEffect(
    () => () => {
      if (glowTimer.current) clearTimeout(glowTimer.current);
    },
    [],
  );
  const handleBellClick = () => {
    setBellGlow(true);
    if (glowTimer.current) clearTimeout(glowTimer.current);
    glowTimer.current = setTimeout(() => setBellGlow(false), 700);
    navigate('/app/inbox');
  };

  // Compute breadcrumbs
  const path = location.pathname;
  const breadcrumbItems = React.useMemo(() => {
    const crumbs: { label: string; to?: string }[] = [{ label: 'BIDWISE', to: '/app/dashboard' }];

    if (path.startsWith('/app/dashboard')) {
      crumbs.push({ label: 'Executive Dashboard' });
    } else if (path.startsWith('/app/tenders')) {
      crumbs.push({ label: 'Tenders', to: '/app/tenders' });
      const parts = path.split('/').filter(Boolean);
      if (parts.length > 2 && (parts[2] === 'create' || parts[2] === 'new')) {
        crumbs.push({ label: 'Create Tender & Register Bidders' });
      } else if (parts.length > 2 && parts[2] !== '') {
        crumbs.push({ label: `Tender Dossier #${parts[2]}` });
      }
    } else if (path.startsWith('/app/bids')) {
      crumbs.push({ label: 'Tenders', to: '/app/tenders' });
      crumbs.push({ label: 'Bidder Evaluation Dossier' });
    } else if (path.startsWith('/app/inbox')) {
      crumbs.push({ label: 'Notifications' });
    } else if (path.startsWith('/app/integrity')) {
      crumbs.push({ label: 'Integrity Signals' });
    } else if (path.startsWith('/app/documents')) {
      crumbs.push({ label: 'Test Your Document (Verification Lab)' });
    } else if (path.startsWith('/app/audit')) {
      crumbs.push({ label: 'Statutory Audit Trail' });
    } else if (path.startsWith('/app/profile')) {
      crumbs.push({ label: 'Officer Profile' });
    } else if (path.startsWith('/app/settings')) {
      crumbs.push({ label: 'System Configuration' });
    }
    return crumbs;
  }, [path]);

  const pageTitle = breadcrumbItems[breadcrumbItems.length - 1]?.label ?? 'Portal Workspace';

  return (
    <div className="flex min-h-screen bg-slate-100 text-slate-900 font-sans dark:bg-slate-950 dark:text-slate-100">
      {/* Desktop Sidebar */}
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 bg-slate-900 shadow-md lg:block z-40">
        <SidebarContent />
      </aside>

      {/* Mobile Drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm"
            onClick={() => setMobileOpen(false)}
            aria-hidden
          />
          <aside className="absolute inset-y-0 left-0 w-72 bg-slate-900 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 p-3">
              <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                BIDWISE Navigation
              </span>
              <button
                className="rounded p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white"
                onClick={() => setMobileOpen(false)}
                aria-label="Close navigation"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="h-[calc(100%-53px)]">
              <SidebarContent onNavigate={() => setMobileOpen(false)} />
            </div>
          </aside>
        </div>
      )}

      {/* Main Content Column */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Institutional Top Header */}
        <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur-md shadow-xs dark:border-slate-800 dark:bg-slate-900/95">
          <div className="flex items-center justify-between gap-4 px-4 py-2.5 sm:px-6">
            <div className="flex items-center gap-3 min-w-0">
              <button
                className="rounded-md p-1.5 text-slate-600 hover:bg-slate-100 lg:hidden dark:text-slate-400 dark:hover:bg-slate-800"
                onClick={() => setMobileOpen(true)}
                aria-label="Open navigation"
              >
                <Menu className="h-5 w-5" />
              </button>

              {/* Breadcrumb path */}
              <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-xs text-slate-600 truncate dark:text-slate-400">
                {breadcrumbItems.map((crumb, idx) => {
                  const isLast = idx === breadcrumbItems.length - 1;
                  return (
                    <React.Fragment key={idx}>
                      {idx > 0 && <ChevronRight className="h-3 w-3 text-slate-400 shrink-0 dark:text-slate-500" />}
                      {crumb.to && !isLast ? (
                        <Link
                          to={crumb.to}
                          className="hover:text-blue-700 transition-colors font-medium hover:underline text-slate-600 truncate dark:text-slate-400 dark:hover:text-blue-400"
                        >
                          {crumb.label}
                        </Link>
                      ) : (
                        <span className={cn('truncate', isLast ? 'font-semibold text-slate-900 dark:text-slate-100' : 'text-slate-500 dark:text-slate-400')}>
                          {crumb.label}
                        </span>
                      )}
                    </React.Fragment>
                  );
                })}
              </nav>
            </div>

            {/* Contextual institutional badges and officer indicators */}
            <div className="flex items-center gap-3 shrink-0">
              <div className="hidden md:flex items-center gap-2 rounded-full border border-blue-200 bg-blue-50/80 px-2.5 py-0.5 text-[11px] font-medium text-blue-900 dark:border-blue-800 dark:bg-blue-950/60 dark:text-blue-300">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                <span>GeM Portal Sync: Connected</span>
              </div>

              <div className="relative">
                <button
                  type="button"
                  onClick={handleBellClick}
                  aria-label="Open notifications"
                  className={cn(
                    'rounded-full p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-800 transition-all dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100',
                    bellGlow &&
                      'bg-amber-50 ring-2 ring-amber-400/70 dark:bg-amber-950/50 dark:ring-amber-400/50',
                  )}
                  title="Notifications & System Alerts"
                >
                  <Bell className="h-4 w-4" />
                  {bellUnread > 0 && (
                    <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-amber-500 px-1 text-[9px] font-bold text-white ring-2 ring-white dark:ring-slate-900">
                      {bellUnread > 99 ? '99+' : bellUnread}
                    </span>
                  )}
                </button>
              </div>

              <ThemeToggle />

              <div className="hidden sm:flex items-center gap-2 border-l border-slate-200 pl-3 dark:border-slate-800">
                <div className="text-right">
                  <p className="text-xs font-semibold text-slate-900 leading-tight dark:text-slate-100">{user?.name}</p>
                  <p className="text-[10px] text-slate-500 font-medium dark:text-slate-400">Procurement Officer</p>
                </div>
                <div className="h-7 w-7 rounded-full bg-slate-800 text-white flex items-center justify-center text-xs font-bold shadow-xs">
                  {user?.name?.charAt(0)?.toUpperCase() ?? 'U'}
                </div>
              </div>
            </div>
          </div>
        </header>

        {/* Page Content */}
        <main id="main-content" className="flex-1 bg-slate-50/60 dark:bg-slate-950">
          <div className="mx-auto max-w-[1440px] p-4 sm:p-6 lg:p-7">
            <Outlet />
          </div>
        </main>

        {/* Institutional Footer */}
        <footer className="border-t border-slate-200 bg-white py-3 px-4 sm:px-6 dark:border-slate-800 dark:bg-slate-900">
          <div className="mx-auto flex max-w-[1440px] flex-col sm:flex-row items-center justify-between gap-2 text-[11px] text-slate-500 dark:text-slate-400">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-slate-700 dark:text-slate-200">BIDWISE</span>
              <span>— Smart &amp; Evidence-Based Bid Verification</span>
              <span className="hidden md:inline text-slate-300 dark:text-slate-600">|</span>
              <span className="hidden md:inline text-slate-500 dark:text-slate-400">Procurement Decision Support System</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600 border border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-800">
                Evidence-Backed Auditability
              </span>
              <span>CPCL Manali Refinery</span>
            </div>
          </div>
        </footer>
      </div>
    </div>
  );
}
