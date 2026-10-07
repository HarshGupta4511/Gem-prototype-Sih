import { Check, LogOut, ShieldCheck } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { SystemLayerTag } from '../components/common/SystemLayerTag';

// Single-role application: the only human user is the Procurement Officer.
// Every capability below is officer-owned and always available.
const CAPABILITIES = [
  { label: 'View Tenders, Bids & Evidence', desc: 'Access procurement packages across all stages' },
  { label: 'Ingest & Process Bid Documents', desc: 'Trigger OCR extraction, classification, and entity parsing pipelines' },
  { label: 'Execute Statutory Verification Adapters', desc: 'Cross-reference taxpayer GSTN, PAN, MCA21, EPFO, and Debarment APIs' },
  { label: 'Evaluate Deterministic Compliance Rules', desc: 'Compute requirement thresholds and weighted compliance percentages' },
  { label: 'Generate Verification Summary', desc: 'Generate and regenerate the evidence-backed verification summary' },
  { label: 'Record Formal Officer Verdicts', desc: 'Sign off on Approve, Reject, or Escalate determinations with audit hashing' },
  { label: 'Record Administrative Overrides', desc: 'Record officer justification to override automated rule findings' },
  { label: 'Cryptographic Audit Trail Verification', desc: 'Verify SHA-256 hash continuity and inspect tamper-evident logs' },
];

export default function Profile() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleSignOut = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="space-y-6">
      {/* 1. Header */}
      <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-xs dark:border-slate-800 dark:bg-slate-900">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-blue-800 font-mono dark:text-blue-400">
                Officer Administration
              </span>
              <SystemLayerTag layer="HUMAN_DECISION" size="sm" />
            </div>
            <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900 font-serif dark:text-slate-100">
              Officer Profile &amp; Delegations
            </h1>
            <p className="mt-0.5 text-xs text-slate-600 dark:text-slate-400">
              Account credentials and statutory delegations of the Procurement Officer.
            </p>
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={handleSignOut}
            className="border-slate-300 text-rose-700 hover:bg-rose-50 text-xs self-start sm:self-auto dark:border-slate-700 dark:text-rose-400 dark:hover:bg-rose-950/50"
          >
            <LogOut className="mr-1.5 h-3.5 w-3.5" />
            Sign Out of Session
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Officer Card */}
        <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-xs space-y-5 dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center gap-3.5 border-b border-slate-100 pb-4 dark:border-slate-800">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-blue-900 text-lg font-bold text-white shadow-sm font-serif">
              {user?.name?.charAt(0)?.toUpperCase() ?? 'O'}
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900 dark:text-slate-100">{user?.name}</h2>
              <p className="text-xs text-slate-500 font-mono dark:text-slate-400">{user?.email}</p>
            </div>
          </div>

          <div className="space-y-3 text-xs">
            <div>
              <span className="text-slate-500 block dark:text-slate-400">Role:</span>
              <span className="inline-block mt-1 rounded bg-blue-50 px-2 py-0.5 font-bold text-blue-900 border border-blue-200 text-xs dark:bg-blue-950/60 dark:text-blue-300 dark:border-blue-900">
                Procurement Officer
              </span>
            </div>

            <div>
              <span className="text-slate-500 block dark:text-slate-400">Procuring Entity:</span>
              <span className="font-semibold text-slate-800 block mt-0.5 dark:text-slate-200">
                Chennai Petroleum Corporation Limited (CPCL)
              </span>
            </div>

            <div>
              <span className="text-slate-500 block dark:text-slate-400">Ministry / Department:</span>
              <span className="font-semibold text-slate-800 block mt-0.5 dark:text-slate-200">
                Ministry of Petroleum &amp; Natural Gas
              </span>
            </div>

            <div>
              <span className="text-slate-500 block dark:text-slate-400">Account Status:</span>
              <span className="inline-flex items-center gap-1.5 text-emerald-800 font-semibold mt-0.5 dark:text-emerald-400">
                <span className="h-2 w-2 rounded-full bg-emerald-500" />
                Active &amp; Empaneled
              </span>
            </div>

            <div>
              <span className="text-slate-500 block dark:text-slate-400">Audit Signature ID:</span>
              <span className="font-mono text-slate-600 block mt-0.5 dark:text-slate-400">
                OFFICER-UID-{user?.id ?? '001'}
              </span>
            </div>
          </div>

          <div className="border-t border-slate-100 pt-4 dark:border-slate-800">
            <Button
              onClick={handleSignOut}
              variant="outline"
              className="w-full border-rose-200 bg-rose-50/50 hover:bg-rose-50 text-rose-800 text-xs font-semibold dark:border-rose-900 dark:bg-rose-950/40 dark:hover:bg-rose-950/70 dark:text-rose-300"
            >
              <LogOut className="mr-1.5 h-3.5 w-3.5 text-rose-600 dark:text-rose-400" />
              Terminate Active Session
            </Button>
          </div>
        </div>

        {/* Capabilities Matrix */}
        <div className="lg:col-span-2 rounded-lg border border-slate-200 bg-white p-6 shadow-xs space-y-4 dark:border-slate-800 dark:bg-slate-900">
          <div className="border-b border-slate-100 pb-3 dark:border-slate-800">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200">
              Statutory Delegations &amp; Capabilities
            </h3>
            <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
              As the single human user of this platform, the Procurement Officer holds the full procurement workflow end to end.
            </p>
          </div>

          <div className="divide-y divide-slate-100 dark:divide-slate-800">
            {CAPABILITIES.map((cap) => (
              <div key={cap.label} className="py-3 flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-xs font-semibold text-slate-900 dark:text-slate-100">{cap.label}</p>
                  <p className="text-[11px] text-slate-500 leading-snug mt-0.5 dark:text-slate-400">{cap.desc}</p>
                </div>
                <div className="shrink-0">
                  <span className="inline-flex items-center gap-1 rounded bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-800 border border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-400 dark:border-emerald-900">
                    <Check className="h-3 w-3 text-emerald-600 dark:text-emerald-400" /> Allowed
                  </span>
                </div>
              </div>
            ))}
          </div>

          <div className="rounded-lg border border-blue-200 bg-blue-50/60 p-3.5 text-xs text-blue-900 mt-4 flex items-start gap-2 dark:border-blue-900 dark:bg-blue-950/40 dark:text-blue-100">
            <ShieldCheck className="h-4 w-4 text-blue-700 shrink-0 mt-0.5 dark:text-blue-400" />
            <p className="leading-relaxed">
              <strong>Statutory Accountability:</strong> In compliance with General Financial Rules (GFR), all decision recording and administrative overrides require justification and are permanently recorded in the SHA-256 audit ledger.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
