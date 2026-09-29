import * as React from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { authApi, getErrorMessage, setToken } from '../lib/api';
import { useToast } from '../components/ui/toaster';
import type { Role, User } from '../types';

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  demoLogin: () => Promise<void>;
  logout: () => void;
  hasRole: (...roles: Role[]) => boolean;
  canDecide: boolean; // procurement officer only: final decisions, overrides, clarifications, tender/bidder CRUD
  canVerify: boolean; // procurement officer + verifier: run verification, process/evaluate docs
  canReport: boolean; // verifier only: generate + send verification reports
  isOfficer: boolean;
  isVerifier: boolean;
  isAuditor: boolean; // read-only
}

const AuthContext = React.createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const ctx = React.useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const hasToken = typeof window !== 'undefined' && !!localStorage.getItem('bidverify_token');

  const { data: user, isLoading } = useQuery({
    queryKey: ['me'],
    queryFn: authApi.me,
    enabled: hasToken,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

  const applyAuth = (u: User, token: string) => {
    setToken(token);
    queryClient.setQueryData(['me'], u);
  };

  const login = async (email: string, password: string) => {
    try {
      const res = await authApi.login({ email, password });
      applyAuth(res.user, res.access_token);
      toast('success', `Welcome, ${res.user.name}`);
    } catch (err) {
      toast('error', 'Login failed', getErrorMessage(err));
      throw err;
    }
  };

  const demoLogin = async () => {
    try {
      const res = await authApi.demo();
      applyAuth(res.user, res.access_token);
      toast('success', 'Signed in with demo account', `${res.user.name} · ${res.user.role}`);
    } catch (err) {
      toast('error', 'Demo login failed', getErrorMessage(err));
      throw err;
    }
  };

  const logout = () => {
    setToken(null);
    queryClient.setQueryData(['me'], null);
    queryClient.clear();
  };

  const role = user?.role;
  const hasRole = (...roles: Role[]) => !!role && roles.includes(role);

  const value: AuthContextValue = {
    user: user ?? null,
    isLoading,
    isAuthenticated: !!user,
    login,
    demoLogin,
    logout,
    hasRole,
    canDecide: hasRole('PROCUREMENT_OFFICER'),
    canVerify: hasRole('PROCUREMENT_OFFICER', 'VERIFIER'),
    canReport: hasRole('VERIFIER'),
    isOfficer: role === 'PROCUREMENT_OFFICER',
    isVerifier: role === 'VERIFIER',
    isAuditor: role === 'AUDITOR',
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
