import * as React from 'react';
import {
  AlertTriangle,
  ArrowRight,
  Check,
  Cpu,
  Database,
  FileCheck2,
  FileSearch,
  Globe,
  HardDrive,
  KeyRound,
  Layers,
  Lock,
  Monitor,
  Moon,
  RefreshCw,
  ScanText,
  Server,
  ShieldCheck,
  Sparkles,
  Sun,
  Terminal,
} from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { API_BASE_URL, dashboardApi } from '../lib/api';
import { useTheme } from '../context/ThemeContext';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { EmptyState, LoadingBlock } from '../components/common/ui-helpers';
import { SystemLayerTag } from '../components/common/SystemLayerTag';

const MOCK_ADAPTERS = [
  { name: 'GSTN (Taxpayer Verification)', endpoint: 'api.gstn.gov.in/v2/taxpayer', status: 'ONLINE', latency: '< 50ms' },
  { name: 'Income Tax PAN Service (NSDL)', endpoint: 'incometax.gov.in/pan/verify', status: 'ONLINE', latency: '< 40ms' },
  { name: 'MCA21 Company Master (CIN)', endpoint: 'mca.gov.in/mcafoportal/cin', status: 'ONLINE', latency: '< 65ms' },
  { name: 'MSME Udyam Registration', endpoint: 'udyamregistration.gov.in/verify', status: 'ONLINE', latency: '< 55ms' },
  { name: 'EPFO Compliance Portal', endpoint: 'unifiedportal-epfo.gov.in/trrn', status: 'ONLINE', latency: '< 45ms' },
  { name: 'CPSE & GeM Debarment Registry', endpoint: 'gem.gov.in/debarment/registry', status: 'ONLINE', latency: '< 30ms' },
];

const THEME_OPTIONS = [
  { key: 'light' as const, label: 'Light', desc: 'Bright institutional theme', icon: Sun },
  { key: 'dark' as const, label: 'Dark', desc: 'Low-light institutional theme', icon: Moon },
  { key: 'system' as const, label: 'System default', desc: 'Follow this device\u2019s setting', icon: Monitor },
];

export default function Settings() {
  const { theme, setTheme } = useTheme();
  const { data: providers, isLoading, isError, isFetching, refetch } = useQuery({
    queryKey: ['providers'],
    queryFn: dashboardApi.providers,
    retry: false,
  });

  return (
    <div className="space-y-6">
      {/* 1. Header Section */}
      <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-xs dark:border-slate-800 dark:bg-slate-900">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-blue-800 font-mono dark:text-blue-400">
                Platform Configuration &amp; Governance
              </span>
              <SystemLayerTag layer="AUDIT_CHAIN" size="sm" />
            </div>
            <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900 font-serif dark:text-slate-100">
              System Configuration
            </h1>
            <p className="mt-0.5 text-xs text-slate-600 dark:text-slate-400">
              Underlying AI providers, relational database dialect, OCR pipelines, and statutory GeM integration endpoints.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              disabled={isFetching}
              className="h-8 text-xs font-medium text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              <RefreshCw className={`mr-1.5 h-3.5 w-3.5 text-slate-500 dark:text-slate-400 ${isFetching ? 'animate-spin' : ''}`} />
              Refresh Diagnostics
            </Button>
          </div>
        </div>
      </div>

      {/* 1a. Appearance */}
      <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-xs dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center gap-2">
          <Monitor className="h-4 w-4 text-blue-700 dark:text-blue-400" />
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-200">
            Appearance
          </h2>
        </div>
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          Choose the display theme for this device. The selection is saved locally and
          does not affect backend processing or compliance evaluation.
        </p>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3" role="radiogroup" aria-label="Appearance">
          {THEME_OPTIONS.map((opt) => {
            const active = theme === opt.key;
            const Icon = opt.icon;
            return (
              <button
                key={opt.key}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => setTheme(opt.key)}
                className={`flex items-center gap-3 rounded-lg border p-3.5 text-left transition-colors ${
                  active
                    ? 'border-blue-600 bg-blue-50/60 ring-1 ring-blue-600 dark:border-blue-500 dark:bg-blue-950/40 dark:ring-blue-500'
                    : 'border-slate-200 bg-white hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-slate-800'
                }`}
              >
                <span
                  className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-md border ${
                    active
                      ? 'border-blue-200 bg-blue-100 text-blue-800 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-300'
                      : 'border-slate-200 bg-slate-50 text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400'
                  }`}
                >
                  <Icon className="h-4 w-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-xs font-semibold text-slate-900 dark:text-slate-100">
                    {opt.label}
                  </span>
                  <span className="block text-[11px] text-slate-500 dark:text-slate-400">
                    {opt.desc}
                  </span>
                </span>
                {active && (
                  <Check className="h-4 w-4 shrink-0 text-blue-700 dark:text-blue-400" aria-label="Selected" />
                )}
              </button>
            );
          })}
        </div>
      </div>

      {isLoading ? (
        <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-xs dark:border-slate-800 dark:bg-slate-900">
          <LoadingBlock />
        </div>
      ) : isError ? (
        <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-xs dark:border-slate-800 dark:bg-slate-900">
          <EmptyState
            icon={<AlertTriangle className="h-6 w-6 text-amber-500" />}
            title="Provider Status Unavailable"
            description="Could not connect to backend system diagnostics service. Please check server process."
          />
        </div>
      ) : providers ? (
        <div className="space-y-6">
          {/* 2. Core Operational Engines Grid */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {/* AI / LLM Engine */}
            <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  AI / LLM Engine
                </span>
                <Cpu className="h-4 w-4 text-blue-700 dark:text-blue-400" />
              </div>
              <div className="flex items-baseline gap-2">
                <code className="font-mono text-sm font-bold text-slate-900 dark:text-slate-100">
                  {providers.llm_provider}
                </code>
                <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-800 border border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-900">
                  ACTIVE
                </span>
              </div>
              <p className="mt-2 text-[11px] leading-relaxed text-slate-600 dark:text-slate-400">
                Pydantic schema-validated extraction. Deterministic fallback heuristics ensure continuous offline compliance.
              </p>
            </div>

            {/* OCR Pipeline */}
            <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  OCR Engine
                </span>
                <ScanText className="h-4 w-4 text-blue-700 dark:text-blue-400" />
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-sm font-bold text-slate-900 dark:text-slate-100">
                  {providers.ocr_available ? 'Tesseract OCR v5' : 'Heuristic Parser'}
                </span>
                <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-800 border border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-900">
                  READY
                </span>
              </div>
              <p className="mt-2 text-[11px] leading-relaxed text-slate-600 dark:text-slate-400">
                Multi-page PDF rasterization &amp; bilingual text extraction with confidence-scored bounding boxes.
              </p>
            </div>

            {/* Database Engine */}
            <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Relational Storage
                </span>
                <Database className="h-4 w-4 text-blue-700 dark:text-blue-400" />
              </div>
              <div className="flex items-baseline gap-2">
                <code className="font-mono text-sm font-bold text-slate-900 uppercase dark:text-slate-100">
                  {providers.db_dialect}
                </code>
                <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-800 border border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-900">
                  ACID
                </span>
              </div>
              <p className="mt-2 text-[11px] leading-relaxed text-slate-600 dark:text-slate-400">
                SQLAlchemy engine with strict transactional isolation and SHA-256 cryptographic audit ledger tables.
              </p>
            </div>

            {/* Embeddings / RAG */}
            <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Vector Retrieval / RAG
                </span>
                <FileSearch className="h-4 w-4 text-blue-700 dark:text-blue-400" />
              </div>
              <div className="flex items-baseline gap-2">
                <code className="font-mono text-sm font-bold text-slate-900 dark:text-slate-100">
                  {providers.embedding_path}
                </code>
                <span className="rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-semibold text-blue-800 border border-blue-200 dark:bg-blue-950/60 dark:text-blue-300 dark:border-blue-900">
                  COSINE
                </span>
              </div>
              <p className="mt-2 text-[11px] leading-relaxed text-slate-600 dark:text-slate-400">
                Fast semantic matching across CPSE General Financial Rules (GFR) and standard tender terms.
              </p>
            </div>
          </div>

          {/* 3. Statutory Adapters & Integrations */}
          <div className="rounded-lg border border-slate-200 bg-white shadow-xs dark:border-slate-800 dark:bg-slate-900">
            <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50/80 px-4 py-3 dark:border-slate-800 dark:bg-slate-800/40">
              <div>
                <h2 className="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-200">
                  Statutory Government Registry Verification Adapters
                </h2>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">
                  Direct mock adapters emulate authentic Indian public registries with realistic latency and mock schemas
                </p>
              </div>
              <SystemLayerTag layer="GOVERNMENT_ADAPTER" size="sm" />
            </div>

            <div className="divide-y divide-slate-100 dark:divide-slate-800">
              {MOCK_ADAPTERS.map((adapter, idx) => (
                <div key={idx} className="flex flex-col sm:flex-row sm:items-center justify-between p-3.5 gap-2 hover:bg-slate-50/50 dark:hover:bg-slate-800/50">
                  <div className="flex items-center gap-2.5">
                    <span className="h-2 w-2 rounded-full bg-emerald-500" />
                    <div>
                      <p className="text-xs font-semibold text-slate-900 dark:text-slate-100">{adapter.name}</p>
                      <p className="text-[11px] font-mono text-slate-500 dark:text-slate-400">{adapter.endpoint}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 text-xs">
                    <span className="font-mono text-[11px] text-slate-500 dark:text-slate-400">Response: {adapter.latency}</span>
                    <span className="rounded bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-700 border border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-400 dark:border-emerald-900">
                      {adapter.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>

            <div className="border-t border-slate-200 bg-slate-50 px-4 py-2.5 text-[11px] text-slate-500 flex items-center justify-between dark:border-slate-800 dark:bg-slate-800/40 dark:text-slate-400">
              <span>All adapters adhere to the National Data Governance Framework (NDGF) schema standards.</span>
              <span className="font-mono text-slate-600 dark:text-slate-400">Mock Mode: Deterministic Sandboxed</span>
            </div>
          </div>

          {/* 4. API Gateway & Governance Controls */}
          <div className="grid gap-6 md:grid-cols-2">
            {/* Gateway Information */}
            <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-xs dark:border-slate-800 dark:bg-slate-900 space-y-3">
              <div className="flex items-center gap-2">
                <Server className="h-4 w-4 text-blue-700 dark:text-blue-400" />
                <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">API Gateway &amp; Client Connection</h3>
              </div>
              <p className="text-xs text-slate-600 dark:text-slate-400">
                Frontend communicates securely with the backend API service using tokenized bearer sessions.
              </p>

              <div className="rounded border border-slate-200 bg-slate-50 p-3 space-y-2 dark:border-slate-700 dark:bg-slate-800/50">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-500 font-medium dark:text-slate-400">Gateway Base URL</span>
                  <code className="font-mono text-slate-800 font-semibold dark:text-slate-200">{API_BASE_URL}</code>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-500 font-medium dark:text-slate-400">CORS Policy</span>
                  <span className="text-emerald-700 font-medium dark:text-emerald-400">Domain-Restricted</span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-500 font-medium dark:text-slate-400">Authentication</span>
                  <span className="text-slate-800 font-medium dark:text-slate-200">Stateless Bearer JWT</span>
                </div>
              </div>

              <p className="text-[11px] text-slate-500 dark:text-slate-400">
                Configured via environment parameter <code className="font-mono text-slate-700 dark:text-slate-300">VITE_API_URL</code>. Zero credentials stored in client code.
              </p>
            </div>

            {/* Demonstration Benchmark Seeding — removed: seeding is a system
                administration control with no single-role officer agreement. */}
          </div>
        </div>
      ) : null}

      {/* Seed Confirmation Dialog — removed with benchmark seeding control */}
    </div>
  );
}

