import * as React from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { authApi, getErrorMessage, setToken } from '../lib/api';
import { useToast } from '../components/ui/toaster';
import type { User } from '../types';

// Single-role application: the ONLY human user is the Procurement Officer.
// Every authenticated user therefore has full operational authority.
interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string, captchaId: string, captchaText: string) => Promise<void>;
  demoLogin: () => Promise<void>;
  logout: () => void;
  /** Always true for the authenticated officer: final decisions, overrides, clarifications, tender/bidder CRUD. */
  canDecide: boolean;
  /** Always true for the authenticated officer: run verification, process/evaluate docs, generate summaries. */
  canVerify: boolean;
  /** Always true for the authenticated officer. */
  isOfficer: boolean;
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

  const login = async (email: string, password: string, captchaId: string, captchaText: string) => {
    try {
      const res = await authApi.login({ email, password, captcha_id: captchaId, captcha_text: captchaText });
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
      toast('success', 'Signed in with demo account', res.user.name);
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

  const value: AuthContextValue = {
    user: user ?? null,
    isLoading,
    isAuthenticated: !!user,
    login,
    demoLogin,
    logout,
    canDecide: true,
    canVerify: true,
    isOfficer: true,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
