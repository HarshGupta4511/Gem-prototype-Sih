import * as React from 'react';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Cpu,
  Database,
  FileCheck2,
  FileSearch,
  Globe,
  HardDrive,
  KeyRound,
  Layers,
  Lock,
  RefreshCw,
  ScanText,
  Server,
  ShieldCheck,
  Sparkles,
  Sprout,
  Terminal,
} from 'lucide-react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { API_BASE_URL, dashboardApi, getErrorMessage, seedApi } from '../lib/api';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../components/ui/dialog';
import { useToast } from '../components/ui/toaster';
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

export default function Settings() {
  const { hasRole } = useAuth();
  const { toast } = useToast();
  const [seedDialogOpen, setSeedDialogOpen] = React.useState(false);

  const { data: providers, isLoading, isError, isFetching, refetch } = useQuery({
    queryKey: ['providers'],
    queryFn: dashboardApi.providers,
    retry: false,
  });

  const seedMutation = useMutation({
    mutationFn: seedApi.run,
    onSuccess: (res) => {
      toast({
        title: 'Demo Benchmark Seeded',
        description: `Seeded ${res.tenders} tenders, ${res.bidders} bidders, and ${res.documents} verified documents.`,
      });
      setSeedDialogOpen(false);
    },
    onError: (err) => {
      toast({
        title: 'Demo Seed Failed',
        description: getErrorMessage(err),
      });
      setSeedDialogOpen(false);
    },
  });

  return (
    <div className="space-y-6">
      {/* 1. Header Section */}
      <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-blue-800 font-mono">
                System Administration &amp; Governance
              </span>
              <SystemLayerTag layer="AUDIT_CHAIN" size="sm" />
            </div>
            <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900 font-serif">
              System Configuration
            </h1>
            <p className="mt-0.5 text-xs text-slate-600">
              Underlying AI providers, relational database dialect, OCR pipelines, and statutory GeM integration endpoints.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              disabled={isFetching}
              className="h-8 text-xs font-medium text-slate-700 hover:bg-slate-50"
            >
              <RefreshCw className={`mr-1.5 h-3.5 w-3.5 text-slate-500 ${isFetching ? 'animate-spin' : ''}`} />
              Refresh Diagnostics
            </Button>
          </div>
        </div>
      </div>

      {isLoading ? (
        <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-xs">
          <LoadingBlock />
        </div>
      ) : isError ? (
        <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-xs">
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
            <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  AI / LLM Engine
                </span>
                <Cpu className="h-4 w-4 text-blue-700" />
              </div>
              <div className="flex items-baseline gap-2">
                <code className="font-mono text-sm font-bold text-slate-900">
                  {providers.llm_provider}
                </code>
                <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-800 border border-emerald-200">
                  ACTIVE
                </span>
              </div>
              <p className="mt-2 text-[11px] leading-relaxed text-slate-600">
                Pydantic schema-validated extraction. Deterministic fallback heuristics ensure continuous offline compliance.
              </p>
            </div>

            {/* OCR Pipeline */}
            <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  OCR Engine
                </span>
                <ScanText className="h-4 w-4 text-blue-700" />
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-sm font-bold text-slate-900">
                  {providers.ocr_available ? 'Tesseract OCR v5' : 'Heuristic Parser'}
                </span>
                <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-800 border border-emerald-200">
                  READY
                </span>
              </div>
              <p className="mt-2 text-[11px] leading-relaxed text-slate-600">
                Multi-page PDF rasterization &amp; bilingual text extraction with confidence-scored bounding boxes.
              </p>
            </div>

            {/* Database Engine */}
            <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  Relational Storage
                </span>
                <Database className="h-4 w-4 text-blue-700" />
              </div>
              <div className="flex items-baseline gap-2">
                <code className="font-mono text-sm font-bold text-slate-900 uppercase">
                  {providers.db_dialect}
                </code>
                <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-800 border border-emerald-200">
                  ACID
                </span>
              </div>
              <p className="mt-2 text-[11px] leading-relaxed text-slate-600">
                SQLAlchemy engine with strict transactional isolation and SHA-256 cryptographic audit ledger tables.
              </p>
            </div>

            {/* Embeddings / RAG */}
            <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  Vector Retrieval / RAG
                </span>
                <FileSearch className="h-4 w-4 text-blue-700" />
              </div>
              <div className="flex items-baseline gap-2">
                <code className="font-mono text-sm font-bold text-slate-900">
                  {providers.embedding_path}
                </code>
                <span className="rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-semibold text-blue-800 border border-blue-200">
                  COSINE
                </span>
              </div>
              <p className="mt-2 text-[11px] leading-relaxed text-slate-600">
                Fast semantic matching across CPSE General Financial Rules (GFR) and standard tender terms.
              </p>
            </div>
          </div>

          {/* 3. Statutory Adapters & Integrations */}
          <div className="rounded-lg border border-slate-200 bg-white shadow-xs">
            <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50/80 px-4 py-3">
              <div>
                <h2 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                  Statutory Government Registry Verification Adapters
                </h2>
                <p className="text-[11px] text-slate-500">
                  Direct mock adapters emulate authentic Indian public registries with realistic latency and mock schemas
                </p>
              </div>
              <SystemLayerTag layer="GOVERNMENT_ADAPTER" size="sm" />
            </div>

            <div className="divide-y divide-slate-100">
              {MOCK_ADAPTERS.map((adapter, idx) => (
                <div key={idx} className="flex flex-col sm:flex-row sm:items-center justify-between p-3.5 gap-2 hover:bg-slate-50/50">
                  <div className="flex items-center gap-2.5">
                    <span className="h-2 w-2 rounded-full bg-emerald-500" />
                    <div>
                      <p className="text-xs font-semibold text-slate-900">{adapter.name}</p>
                      <p className="text-[11px] font-mono text-slate-500">{adapter.endpoint}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 text-xs">
                    <span className="font-mono text-[11px] text-slate-500">Response: {adapter.latency}</span>
                    <span className="rounded bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-700 border border-emerald-200">
                      {adapter.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>

            <div className="border-t border-slate-200 bg-slate-50 px-4 py-2.5 text-[11px] text-slate-500 flex items-center justify-between">
              <span>All adapters adhere to the National Data Governance Framework (NDGF) schema standards.</span>
              <span className="font-mono text-slate-600">Mock Mode: Deterministic Sandboxed</span>
            </div>
          </div>

          {/* 4. API Gateway & Governance Controls */}
          <div className="grid gap-6 md:grid-cols-2">
            {/* Gateway Information */}
            <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-xs space-y-3">
              <div className="flex items-center gap-2">
                <Server className="h-4 w-4 text-blue-700" />
                <h3 className="text-sm font-bold text-slate-900">API Gateway &amp; Client Connection</h3>
              </div>
              <p className="text-xs text-slate-600">
                Frontend communicates securely with the backend API service using tokenized bearer sessions.
              </p>

              <div className="rounded border border-slate-200 bg-slate-50 p-3 space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-500 font-medium">Gateway Base URL</span>
                  <code className="font-mono text-slate-800 font-semibold">{API_BASE_URL}</code>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-500 font-medium">CORS Policy</span>
                  <span className="text-emerald-700 font-medium">Domain-Restricted</span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-500 font-medium">Authentication</span>
                  <span className="text-slate-800 font-medium">Stateless Bearer JWT</span>
                </div>
              </div>

              <p className="text-[11px] text-slate-500">
                Configured via environment parameter <code className="font-mono text-slate-700">VITE_API_URL</code>. Zero credentials stored in client code.
              </p>
            </div>

            {/* Demonstration Benchmark Seeding */}
            <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-xs space-y-3">
              <div className="flex items-center gap-2">
                <Sprout className="h-4 w-4 text-emerald-700" />
                <h3 className="text-sm font-bold text-slate-900">Demonstration Benchmark Data</h3>
              </div>
              <p className="text-xs text-slate-600">
                Populate or reset the database with realistic CPSE procurement packages, bidders, statutory filings, and rule evaluations.
              </p>

              <div className="rounded border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700 space-y-1.5">
                <div className="flex items-center gap-1.5 font-medium text-slate-800">
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                  <span>Idempotent Operation</span>
                </div>
                <p className="text-[11px] text-slate-500">
                  The seed script safely skips pre-existing tenders. It establishes benchmark test cases (e.g. CPCL-DEMO-2026-001) for verification testing.
                </p>
              </div>

              {hasRole('ADMIN') ? (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8 text-xs font-semibold border-slate-300 text-slate-800 hover:bg-slate-100"
                  onClick={() => setSeedDialogOpen(true)}
                  loading={seedMutation.isPending}
                >
                  <Sprout className="mr-1.5 h-3.5 w-3.5 text-emerald-600" />
                  Seed Benchmark Dataset
                </Button>
              ) : (
                <p className="text-[11px] text-slate-500 italic">
                  Administrator privileges required to execute database seeding.
                </p>
              )}
            </div>
          </div>
        </div>
      ) : null}

      {/* Seed Confirmation Dialog */}
      <Dialog open={seedDialogOpen} onOpenChange={setSeedDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Seed Benchmark Demonstration Data?</DialogTitle>
            <DialogDescription>
              Execute backend seeder on <code className="font-mono text-xs">POST /api/seed</code>.
            </DialogDescription>
          </DialogHeader>
          <DialogBody>
            <p className="text-xs leading-relaxed text-slate-600">
              This operation verifies database integrity and seeds benchmark CPSE tender packages with realistic bidder documents, GST certificates, and evaluation matrices. Existing records will be safely preserved.
            </p>
          </DialogBody>
          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setSeedDialogOpen(false)}
            >
              Cancel
            </Button>
            <Button
              variant="default"
              size="sm"
              loading={seedMutation.isPending}
              onClick={() => seedMutation.mutate()}
              className="bg-emerald-700 hover:bg-emerald-800 text-white"
            >
              <Sprout className="mr-1.5 h-3.5 w-3.5" />
              Confirm Seeding
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

