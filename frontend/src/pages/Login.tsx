import * as React from 'react';
import {
  ShieldCheck,
  FileText,
  CheckCircle,
  Scale,
  UserCheck,
  ArrowRight,
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
import { authApi } from '../lib/api';

const schema = z.object({
  email: z.string().email('Please enter a valid official email address'),
  password: z.string().min(1, 'Password is required'),
  captchaText: z.string().min(1, 'Security code is required'),
});

type FormValues = z.infer<typeof schema>;

const WORKFLOW_STEPS = [
  {
    step: '01',
    name: 'DOCUMENTS',
    desc: 'Ingest bidder tender submissions & statutory filings',
    icon: FileText,
  },
  {
    step: '02',
    name: 'VERIFICATION',
    desc: 'Cross-reference GSTN, PAN, MCA, EPFO & Debarment lists',
    icon: CheckCircle,
  },
  {
    step: '03',
    name: 'COMPLIANCE',
    desc: 'Deterministic rule evaluation & independent risk scoring',
    icon: Scale,
  },
  {
    step: '04',
    name: 'DECISION',
    desc: 'Evidence-backed approval, rejection, or clarification by Officer',
    icon: UserCheck,
  },
];

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
      setAuthError('Authentication failed. Please verify your credentials and security code, or try Demo sign-in.');
      // Challenges are single-use — always issue a fresh one after an attempt.
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
      {/* Left institutional authority column */}
      <div className="relative hidden w-1/2 flex-col justify-between overflow-hidden border-r border-slate-800 bg-slate-950 p-12 lg:flex xl:p-16">
        {/* Subtle grid pattern overlay */}
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage:
              'radial-gradient(circle at 1px 1px, white 1px, transparent 0)',
            backgroundSize: '24px 24px',
          }}
        />

        {/* Top Product Identity */}
        <div className="relative z-10">
          <div className="flex items-center gap-3.5">
            <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-gradient-to-br from-blue-600 via-blue-700 to-indigo-900 border border-blue-400/40 text-white shadow-md">
              <ShieldCheck className="h-7 w-7 text-blue-100" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-2xl font-bold tracking-tight text-white font-serif">
                  GEVRA
                </span>
                <span className="rounded bg-blue-500/20 px-2 py-0.5 text-[10px] font-semibold text-blue-300 border border-blue-400/30">
                  CPSE PROCUREMENT
                </span>
              </div>
              <p className="text-xs font-medium text-slate-300">
                GeM Verification &amp; Risk Assessment Platform
              </p>
            </div>
          </div>

          <div className="mt-8 max-w-lg">
            <h1 className="text-2xl font-semibold tracking-tight text-white sm:text-3xl font-serif">
              AI-assisted verification and decision support for GeM procurement.
            </h1>
            <p className="mt-3 text-sm leading-relaxed text-slate-400">
              Deterministic rule evaluation, statutory portal cross-referencing, and verifiable evidence dossiers designed exclusively for procurement officers and committee evaluations.
            </p>
          </div>
        </div>

        {/* Subtle Workflow Visualization: DOCUMENTS → VERIFICATION → COMPLIANCE → DECISION */}
        <div className="relative z-10 my-8 max-w-md">
          <p className="mb-4 text-[11px] font-semibold uppercase tracking-[0.14em] text-blue-400">
            Bid Verification Pipeline
          </p>
          <div className="space-y-3">
            {WORKFLOW_STEPS.map((s, idx) => {
              const Icon = s.icon;
              return (
                <div key={s.name} className="relative">
                  <div className="flex items-start gap-3.5 rounded-md border border-slate-800/80 bg-slate-900/60 p-3 transition-colors hover:border-slate-700">
                    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded bg-blue-950/80 border border-blue-800/60 text-blue-300">
                      <Icon className="h-4 w-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold tracking-wider text-slate-200">
                          {s.name}
                        </span>
                        <span className="text-[10px] font-mono text-slate-500">{s.step}</span>
                      </div>
                      <p className="mt-0.5 text-xs text-slate-400 leading-snug">{s.desc}</p>
                    </div>
                  </div>
                  {idx < WORKFLOW_STEPS.length - 1 && (
                    <div className="flex justify-center py-1">
                      <ArrowRight className="h-3 w-3 rotate-90 text-slate-700" />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Institutional notice at footer */}
        <div className="relative z-10 border-t border-slate-800/80 pt-4 text-[11.5px] text-slate-500">
          <p>
            Official Decision-Support Environment • Verification data simulated via statutory mock adapters. Final award decisions rest solely with the authorized Procurement Officer.
          </p>
        </div>
      </div>

      {/* Right authentication form */}
      <div className="flex flex-1 items-center justify-center bg-slate-50 p-6 sm:p-12">
        <div className="w-full max-w-md">
          {/* Mobile identity banner */}
          <div className="mb-6 flex items-center gap-3 lg:hidden">
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-blue-900 text-white">
              <ShieldCheck className="h-6 w-6" />
            </div>
            <div>
              <p className="text-lg font-bold text-slate-900">GEVRA</p>
              <p className="text-xs text-slate-500">GeM Verification &amp; Risk Assessment</p>
            </div>
          </div>

          <div className="rounded-lg border border-slate-300 bg-white p-7 sm:p-8 shadow-sm">
            <div className="border-b border-slate-200 pb-5">
              <div className="flex items-center justify-between">
                <span className="inline-flex items-center gap-1.5 rounded bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-700 border border-slate-200">
                  <Lock className="h-3 w-3 text-slate-500" /> Secure Officer Access
                </span>
                <span className="text-[11px] font-mono text-slate-400">SIH-26100</span>
              </div>
              <h2 className="mt-3 text-xl font-bold tracking-tight text-slate-900 font-serif">
                Officer Sign In
              </h2>
              <p className="mt-1 text-xs text-slate-600">
                Authenticate with your official CPSE credentials to access the bid evaluation workspace.
              </p>
            </div>

            {authError && (
              <div className="mt-4 rounded border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
                {authError}
              </div>
            )}

            {/* Standard Credentials Form */}
            <form onSubmit={handleSubmit(onSubmit)} className="mt-5 space-y-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700" htmlFor="email">
                  Official Email Address
                </label>
                <div className="mt-1.5">
                  <Input
                    id="email"
                    type="email"
                    placeholder="officer@demo.cpcl.in"
                    autoComplete="email"
                    className="border-slate-300 focus:border-blue-600 focus:ring-blue-600 text-sm"
                    {...register('email')}
                  />
                </div>
                {errors.email && <p className="mt-1 text-xs text-rose-600">{errors.email.message}</p>}
              </div>

              <div>
                <div className="flex items-center justify-between">
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700" htmlFor="password">
                    Password
                  </label>
                </div>
                <div className="mt-1.5">
                  <Input
                    id="password"
                    type="password"
                    placeholder="••••••••••••"
                    autoComplete="current-password"
                    className="border-slate-300 focus:border-blue-600 focus:ring-blue-600 text-sm"
                    {...register('password')}
                  />
                </div>
                {errors.password && <p className="mt-1 text-xs text-rose-600">{errors.password.message}</p>}
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700" htmlFor="captchaText">
                  Security Check
                </label>
                <div className="mt-1.5 flex items-stretch gap-2">
                  <div className="flex h-11 items-center overflow-hidden rounded-md border border-slate-300 bg-slate-100 select-none">
                    {captcha ? (
                      <img src={captcha.image} alt="Security code" className="h-full" draggable={false} />
                    ) : (
                      <span className="px-4 text-xs text-slate-400">
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
                    className="flex w-11 items-center justify-center rounded-md border border-slate-300 text-slate-500 hover:bg-slate-50 hover:text-slate-700 disabled:opacity-50"
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
                    className="border-slate-300 focus:border-blue-600 focus:ring-blue-600 text-sm uppercase"
                    {...register('captchaText')}
                  />
                </div>
                {errors.captchaText && <p className="mt-1 text-xs text-rose-600">{errors.captchaText.message}</p>}
                <p className="mt-1 text-[11px] text-slate-500">
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
                  Sign In to GEVRA
                </Button>
              </div>
            </form>

            <div className="relative my-6 text-center">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-slate-200" />
              </div>
              <span className="relative bg-white px-3 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                Evaluation &amp; Demo Access
              </span>
            </div>

            {/* Secondary Demo Access */}
            <div>
              <Button
                type="button"
                variant="outline"
                className="w-full border-slate-300 hover:bg-slate-50 text-slate-700 font-medium py-2"
                onClick={onDemo}
                loading={demoBusy}
              >
                <Building2 className="mr-2 h-4 w-4 text-blue-700" />
                Quick Launch: Demo Procurement Officer
              </Button>
              <p className="mt-2 text-center text-[11px] text-slate-500">
                Demo account: officer@demo.cpcl.in
              </p>
            </div>
          </div>

          <div className="mt-6 text-center text-xs text-slate-500">
            <span>Chennai Petroleum Corporation Limited</span> • <span>Ministry of Petroleum &amp; Natural Gas</span>
          </div>
        </div>
      </div>
    </div>
  );
}
