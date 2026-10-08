import * as React from 'react';
import {
  Lock,
  Building2,
  KeyRound,
  RefreshCw,
} from 'lucide-react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { useAuth } from '../context/AuthContext';
import { authApi, getErrorStatus } from '../lib/api';

const schema = z.object({
  email: z.string().email('Please enter a valid official email address'),
  password: z.string().min(1, 'Password is required'),
  captchaText: z.string().min(1, 'Security code is required'),
});

type FormValues = z.infer<typeof schema>;

export default function Login() {
  const navigate = useNavigate();
  const { login, demoLogin, isAuthenticated } = useAuth();
  const [busy, setBusy] = React.useState(false);
  const [demoBusy, setDemoBusy] = React.useState(false);
  const [authError, setAuthError] = React.useState<string | null>(null);
  const [captcha, setCaptcha] = React.useState<{ id: string; image: string } | null>(null);
  const [captchaLoading, setCaptchaLoading] = React.useState(false);

  const loadCaptcha = React.useCallback(async () => {
    setCaptchaLoading(true);
    try {
      const c = await authApi.captcha();
      setCaptcha({ id: c.captcha_id, image: c.image });
    } catch {
      setCaptcha(null);
    } finally {
      setCaptchaLoading(false);
    }
  }, []);

  React.useEffect(() => {
    loadCaptcha();
  }, [loadCaptcha]);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>();

  React.useEffect(() => {
    if (isAuthenticated) navigate('/app/dashboard', { replace: true });
  }, [isAuthenticated, navigate]);

  const onSubmit = async (values: FormValues) => {
    const parsed = schema.safeParse(values);
    if (!parsed.success || !captcha) return;
    setBusy(true);
    setAuthError(null);
    try {
      await login(parsed.data.email, parsed.data.password, captcha.id, parsed.data.captchaText);
      navigate('/app/dashboard');
    } catch (err: unknown) {
      // Backend rejects a bad/expired code with 400 and bad credentials with
      // 401 — surface which one failed so the officer knows what to retype.
      // Challenges are single-use, so a fresh code is loaded either way.
      if (getErrorStatus(err) === 400) {
        setAuthError('Security code was incorrect or expired. A fresh code has been loaded — please try again.');
      } else {
        setAuthError('Email or password is incorrect. A fresh security code has been loaded — please try again.');
      }
      loadCaptcha();
    } finally {
      setBusy(false);
    }
  };

  const onDemo = async () => {
    setDemoBusy(true);
    setAuthError(null);
    try {
      await demoLogin();
      navigate('/app/dashboard');
    } catch (err: unknown) {
      setAuthError('Unable to initialize demo session. Please try again.');
    } finally {
      setDemoBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen bg-slate-900">
      {/* Left aesthetic & minimalist intelligence showcase column */}
      <div className="relative hidden w-1/2 flex-col justify-between overflow-hidden border-r border-slate-800/80 bg-[#020b18] p-10 lg:flex xl:p-14 select-none">
        {/* Continuous 24*7 ambient floating aurora auras */}
        <div className="pointer-events-none absolute -left-20 -top-20 h-96 w-96 rounded-full bg-gradient-to-br from-blue-600/20 via-cyan-500/15 to-transparent blur-3xl animate-float-drift" />
        <div className="pointer-events-none absolute -bottom-24 -right-16 h-96 w-96 rounded-full bg-gradient-to-tl from-indigo-600/20 via-blue-500/15 to-transparent blur-3xl animate-float-reverse" />
        <div className="pointer-events-none absolute left-1/3 top-1/2 h-72 w-72 -translate-y-1/2 rounded-full bg-cyan-500/10 blur-3xl animate-glow-breathe" />

        {/* Ambient fine grid overlay */}
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.035]"
          style={{
            backgroundImage:
              'radial-gradient(circle at 1px 1px, #93c5fd 1px, transparent 0)',
            backgroundSize: '28px 28px',
          }}
        />

        {/* Continuous 24*7 subtle scanning beam */}
        <div className="pointer-events-none absolute inset-x-0 h-24 bg-gradient-to-b from-transparent via-cyan-400/5 to-transparent animate-scan" />

        {/* Top Minimalist Header */}
        <div className="relative z-10 flex items-center justify-between">
          <div className="inline-flex items-center gap-2 rounded-full border border-blue-500/25 bg-blue-950/60 px-3.5 py-1 text-xs font-medium text-blue-300 backdrop-blur-md shadow-sm">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
            </span>
            <span className="tracking-wide">CPSE Verification Engine</span>
            <span className="text-blue-500/50">•</span>
            <span className="font-mono text-[11px] text-cyan-400">SIH-26100</span>
          </div>

          <div className="flex items-center gap-2 rounded-full border border-slate-800/80 bg-slate-900/60 px-3 py-1 text-[11px] font-mono text-slate-400 backdrop-blur-md">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
            <span>SYSTEM ACTIVE</span>
          </div>
        </div>

        {/* Centerpiece: 24*7 Animated Celestial Orbital Stage with Logo */}
        <div className="relative z-10 my-auto flex flex-col items-center text-center py-6">
          {/* Orbital Celestial System (Runs 24*7) */}
          <div className="relative flex h-56 w-56 sm:h-64 sm:w-64 items-center justify-center">
            {/* 24*7 Breathing Glow Core */}
            <div className="pointer-events-none absolute h-44 w-44 rounded-full bg-gradient-to-tr from-blue-600/35 via-cyan-500/30 to-indigo-600/25 animate-glow-breathe" />

            {/* 24*7 Outward Radiating Ripple Waves */}
            <div className="pointer-events-none absolute h-48 w-48 rounded-full border border-cyan-400/30 animate-ripple-wave-1" />
            <div className="pointer-events-none absolute h-48 w-48 rounded-full border border-blue-500/25 animate-ripple-wave-2" />

            {/* 24*7 Rotating Outer Celestial Ring (Dashed, slow clockwise) */}
            <div className="pointer-events-none absolute h-52 w-52 sm:h-60 sm:w-60 rounded-full border border-dashed border-blue-400/25 animate-spin-slow" />

            {/* 24*7 Rotating Inner Orbital Ring with Orbiting Satellites (Counter-clockwise) */}
            <div className="pointer-events-none absolute h-40 w-40 sm:h-48 sm:w-48 rounded-full border border-blue-500/30 animate-spin-reverse-slow">
              {/* Orbiting Satellite Node 1 */}
              <div className="absolute -top-1.5 left-1/2 -translate-x-1/2 flex items-center justify-center">
                <span className="h-3 w-3 rounded-full bg-cyan-400 shadow-[0_0_12px_#38bdf8]" />
              </div>
              {/* Orbiting Satellite Node 2 */}
              <div className="absolute -bottom-1 left-1/2 -translate-x-1/2 flex items-center justify-center">
                <span className="h-2 w-2 rounded-full bg-blue-400 shadow-[0_0_8px_#60a5fa]" />
              </div>
            </div>

            {/* Logo Glass Emblem - Seamlessly fitted, gently floating 24*7 */}
            <div className="relative z-10 flex h-28 w-28 sm:h-36 sm:w-36 items-center justify-center rounded-3xl border border-blue-500/30 bg-gradient-to-b from-[#081e42]/85 via-[#02132e]/90 to-[#010916]/95 p-4 shadow-[0_0_50px_-10px_rgba(56,189,248,0.35)] backdrop-blur-xl animate-float-slow transition-transform hover:scale-105 duration-500 group">
              <img
                src="/bidwise-logo-transparent.png"
                alt="BIDWISE"
                className="h-full w-full object-contain drop-shadow-[0_4px_16px_rgba(56,189,248,0.35)]"
                draggable={false}
              />
            </div>
          </div>

          {/* Minimalist, High-Impact Typography */}
          <div className="mt-5 max-w-md">
            <h1 className="text-2xl xl:text-3xl font-semibold tracking-tight text-white font-serif leading-tight">
              Evidence-Based Bid Verification
            </h1>
            <p className="mt-2 text-xs sm:text-sm leading-relaxed text-slate-400">
              Deterministic statutory cross-checks and cryptographically sealed decision intelligence for CPSE procurement committees.
            </p>
          </div>

          {/* Minimalist 24*7 Live Status Badges */}
          <div className="mt-6 flex flex-wrap items-center justify-center gap-2 max-w-lg">
            <div className="group flex items-center gap-1.5 rounded-full border border-slate-800/90 bg-slate-900/60 px-3 py-1 text-[11px] text-slate-300 backdrop-blur-md transition-all hover:border-blue-500/40 hover:bg-slate-900/80">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_#34d399] animate-pulse" />
              <span>GSTN &amp; PAN</span>
              <span className="font-mono text-[9px] text-emerald-400">VERIFIED</span>
            </div>

            <div className="group flex items-center gap-1.5 rounded-full border border-slate-800/90 bg-slate-900/60 px-3 py-1 text-[11px] text-slate-300 backdrop-blur-md transition-all hover:border-blue-500/40 hover:bg-slate-900/80">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_#34d399] animate-pulse" />
              <span>MCA-21 &amp; EPFO</span>
              <span className="font-mono text-[9px] text-emerald-400">ACTIVE</span>
            </div>

            <div className="group flex items-center gap-1.5 rounded-full border border-slate-800/90 bg-slate-900/60 px-3 py-1 text-[11px] text-slate-300 backdrop-blur-md transition-all hover:border-blue-500/40 hover:bg-slate-900/80">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_#34d399] animate-pulse" />
              <span>Debarment Watch</span>
              <span className="font-mono text-[9px] text-emerald-400">CLEAR</span>
            </div>
          </div>

          {/* 24*7 Animated Telemetry Scanner Ribbon */}
          <div className="mt-5 w-full max-w-xs overflow-hidden rounded-full border border-slate-800/80 bg-slate-950/70 p-1 backdrop-blur-md">
            <div className="relative flex items-center justify-between px-3.5 py-1 text-[10px] font-mono text-slate-400">
              {/* Continuous 24*7 light shimmer wave */}
              <div className="pointer-events-none absolute inset-0 bg-gradient-to-r from-transparent via-cyan-400/10 to-transparent animate-shimmer" />
              <span className="flex items-center gap-1.5 text-cyan-300">
                <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 animate-ping" />
                100% Deterministic
              </span>
              <span className="text-slate-600">•</span>
              <span className="text-slate-300">SHA-256 Chained</span>
            </div>
          </div>
        </div>

        {/* Minimalist Institutional Trust Footer */}
        <div className="relative z-10 flex items-center justify-between border-t border-slate-800/80 pt-4 text-xs text-slate-400">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_8px_#34d399]" />
            <span className="text-[11px] font-medium text-slate-300">Official Decision Support Gateway</span>
          </div>
          <div className="flex items-center gap-2 text-[11px] font-mono text-slate-500">
            <span>GFR-2017</span>
            <span>•</span>
            <span>CPSE Compliant</span>
          </div>
        </div>
      </div>

      {/* Right authentication form */}
      <div className="flex flex-1 items-center justify-center bg-slate-50 p-6 sm:p-12 dark:bg-slate-950">
        <div className="w-full max-w-md">
          {/* Mobile identity banner */}
          <div className="mb-6 flex items-center gap-3 lg:hidden">
            <img
              src="/bidwise-mark.png"
              alt="BIDWISE logo"
              className="h-10 w-10 rounded-md"
              draggable={false}
            />
            <div>
              <p className="text-lg font-bold text-slate-900 dark:text-slate-100">BIDWISE</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">Smart &amp; Evidence-Based Bid Verification</p>
            </div>
          </div>

          <div className="rounded-lg border border-slate-300 bg-white p-7 sm:p-8 shadow-sm dark:border-slate-700 dark:bg-slate-900">
            <div className="border-b border-slate-200 pb-5 dark:border-slate-700">
              <div className="flex items-center justify-between">
                <span className="inline-flex items-center gap-1.5 rounded bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-700 border border-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:border-slate-700">
                  <Lock className="h-3 w-3 text-slate-500 dark:text-slate-400" /> Secure Officer Access
                </span>
                <span className="text-[11px] font-mono text-slate-400 dark:text-slate-500">SIH-26100</span>
              </div>
              <h2 className="mt-3 text-xl font-bold tracking-tight text-slate-900 font-serif dark:text-slate-100">
                Officer Sign In
              </h2>
              <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">
                Authenticate with your official CPSE credentials to access the bid evaluation workspace.
              </p>
            </div>

            {authError && (
              <div className="mt-4 rounded border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800 dark:border-rose-900 dark:bg-rose-950/50 dark:text-rose-300">
                {authError}
              </div>
            )}

            {/* Standard Credentials Form */}
            <form onSubmit={handleSubmit(onSubmit)} className="mt-5 space-y-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-slate-200" htmlFor="email">
                  Official Email Address
                </label>
                <div className="mt-1.5">
                  <Input
                    id="email"
                    type="email"
                    placeholder="officer@demo.cpcl.in"
                    autoComplete="email"
                    className="border-slate-300 focus:border-blue-600 focus:ring-blue-600 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500"
                    {...register('email')}
                  />
                </div>
                {errors.email && <p className="mt-1 text-xs text-rose-600 dark:text-rose-400">{errors.email.message}</p>}
              </div>

              <div>
                <div className="flex items-center justify-between">
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-slate-200" htmlFor="password">
                    Password
                  </label>
                </div>
                <div className="mt-1.5">
                  <Input
                    id="password"
                    type="password"
                    placeholder="••••••••••••"
                    autoComplete="current-password"
                    className="border-slate-300 focus:border-blue-600 focus:ring-blue-600 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500"
                    {...register('password')}
                  />
                </div>
                {errors.password && <p className="mt-1 text-xs text-rose-600 dark:text-rose-400">{errors.password.message}</p>}
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-slate-200" htmlFor="captchaText">
                  Security Check
                </label>
                <div className="mt-1.5 flex items-stretch gap-2">
                  <div className="flex h-11 items-center overflow-hidden rounded-md border border-slate-300 bg-slate-100 select-none dark:border-slate-700 dark:bg-slate-800">
                    {captcha ? (
                      <img src={captcha.image} alt="Security code" className="h-full" draggable={false} />
                    ) : (
                      <span className="px-4 text-xs text-slate-400 dark:text-slate-500">
                        {captchaLoading ? 'Loading…' : 'Unavailable'}
                      </span>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={loadCaptcha}
                    disabled={captchaLoading}
                    title="Get a new security code"
                    aria-label="Get a new security code"
                    className="flex w-11 items-center justify-center rounded-md border border-slate-300 text-slate-500 hover:bg-slate-50 hover:text-slate-700 disabled:opacity-50 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                  >
                    <RefreshCw className={`h-4 w-4 ${captchaLoading ? 'animate-spin' : ''}`} />
                  </button>
                </div>
                <div className="mt-1.5">
                  <Input
                    id="captchaText"
                    type="text"
                    placeholder="Enter the code shown above"
                    autoComplete="off"
                    className="border-slate-300 focus:border-blue-600 focus:ring-blue-600 text-sm uppercase dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500"
                    {...register('captchaText')}
                  />
                </div>
                {errors.captchaText && <p className="mt-1 text-xs text-rose-600 dark:text-rose-400">{errors.captchaText.message}</p>}
                <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                  Type the characters shown in the image. Each code works once and expires after 5 minutes.
                </p>
              </div>

              <div className="pt-1">
                <Button
                  type="submit"
                  className="w-full bg-blue-800 hover:bg-blue-900 text-white font-medium py-2.5 shadow-sm transition-colors"
                  loading={busy}
                >
                  <KeyRound className="mr-2 h-4 w-4" />
                  Sign In to BIDWISE
                </Button>
              </div>
            </form>

            <div className="relative my-6 text-center">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-slate-200 dark:border-slate-700" />
              </div>
              <span className="relative bg-white px-3 text-[11px] font-semibold uppercase tracking-wider text-slate-400 dark:bg-slate-900 dark:text-slate-500">
                Evaluation &amp; Demo Access
              </span>
            </div>

            {/* Secondary Demo Access */}
            <div>
              <Button
                type="button"
                variant="outline"
                className="w-full border-slate-300 hover:bg-slate-50 text-slate-700 font-medium py-2 dark:border-slate-700 dark:hover:bg-slate-800 dark:text-slate-200"
                onClick={onDemo}
                loading={demoBusy}
              >
                <Building2 className="mr-2 h-4 w-4 text-blue-700 dark:text-blue-400" />
                Quick Launch: Demo Procurement Officer
              </Button>
              <p className="mt-2 text-center text-[11px] text-slate-500 dark:text-slate-400">
                Demo account: officer@demo.cpcl.in
              </p>
            </div>
          </div>

          <div className="mt-6 text-center text-xs text-slate-500 dark:text-slate-400">
            <span>Chennai Petroleum Corporation Limited</span> • <span>Ministry of Petroleum &amp; Natural Gas</span>
          </div>
        </div>
      </div>
    </div>
  );
}
