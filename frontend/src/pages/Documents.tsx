import * as React from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  CheckCircle2,
  Download,
  FileSearch,
  FileText,
  FileUp,
  Info,
  Layers,
  Loader2,
  Scale,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  X,
} from 'lucide-react';
import {
  bidsApi,
  complianceApi,
  documentsApi,
  getErrorMessage,
  tendersApi,
  verificationApi,
} from '../lib/api';
import { useToast } from '../components/ui/toaster';
import { Button } from '../components/ui/button';
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '../components/ui/table';
import { Select } from '../components/ui/input';
import {
  DocStatusBadge,
  DocTypeBadge,
  MethodBadge,
  StatusBadge,
  VerificationBadge,
} from '../components/common/badges';
import { cn, labelize } from '../lib/utils';
import { SystemLayerTag } from '../components/common/SystemLayerTag';
import { MockSourceLabel } from '../components/common/honesty';
import type {
  BidSummary,
  ComplianceResult,
  Document,
  DocumentType,
  ExtractedField,
  RequirementStatus,
  TenderRequirement,
  VerificationCheck,
  VerificationStatus,
} from '../types';

/* ------------------------------------------------------------------ */
/* Benchmark documents — the current 10-document Stage-2 catalogue.    */
/* ------------------------------------------------------------------ */
const BENCHMARK_DOCS = [
  { name: 'Udyam Certificate', type: 'UDYAM_CERTIFICATE', file: '/sample-documents/sample-udyam-certificate.pdf', desc: 'MSME registration certificate' },
  { name: 'GST Registration', type: 'GST_CERTIFICATE', file: '/sample-documents/sample-gst-certificate.pdf', desc: 'Form GST REG-06 with active GSTIN' },
  { name: 'PAN Card', type: 'PAN_CERTIFICATE', file: '/sample-documents/sample-pan-card.pdf', desc: 'Income-tax PAN card' },
  { name: 'ITR 2023–24', type: 'ITR_DOCUMENT', file: '/sample-documents/sample-itr-document.pdf', desc: 'Income tax return acknowledgement' },
  { name: 'MCA21 Certificate', type: 'MCA21_CERTIFICATE', file: '/sample-documents/sample-mca21-certificate.pdf', desc: 'Certificate of incorporation (CIN)' },
  { name: 'Balance Sheet 2024', type: 'BALANCE_SHEET', file: '/sample-documents/sample-balance-sheet.pdf', desc: 'Audited financial position & turnover' },
  { name: 'Work Experience Certificate', type: 'EXPERIENCE_CERTIFICATE', file: '/sample-documents/sample-experience-certificate.pdf', desc: 'Past supply / commissioning credential' },
  { name: 'ISO 9001 Certificate', type: 'ISO_9001_CERTIFICATE', file: '/sample-documents/sample-iso-9001-certificate.pdf', desc: 'Quality management certification' },
  { name: 'EMD Receipt', type: 'EMD_RECEIPT', file: '/sample-documents/sample-emd-receipt.pdf', desc: 'Earnest money deposit proof' },
  { name: 'EPFO Registration', type: 'EPFO_CERTIFICATE', file: '/sample-documents/sample-epfo-registration.pdf', desc: 'Provident fund establishment registration' },
];

const TYPE_REQUIREMENT_KEYWORDS: Record<string, string[]> = {
  GST_CERTIFICATE: ['gst'],
  GST_RETURN: ['gstr', 'gst return'],
  PAN_CERTIFICATE: ['pan'],
  UDYAM_CERTIFICATE: ['udyam', 'msme'],
  TURNOVER_CERTIFICATE: ['turnover'],
  BALANCE_SHEET: ['balance sheet', 'turnover', 'financial'],
  EXPERIENCE_CERTIFICATE: ['experience'],
  OEM_AUTHORIZATION: ['oem'],
  ITR: ['itr', 'income tax'],
  ITR_DOCUMENT: ['itr', 'income tax'],
  EPFO_CERTIFICATE: ['epfo', 'provident fund'],
  ESIC_CERTIFICATE: ['esic'],
  MII_DECLARATION: ['mii', 'local content', 'make in india'],
  MCA21_CERTIFICATE: ['mca21', 'cin', 'incorporation'],
  ISO_9001_CERTIFICATE: ['iso', '9001', 'quality'],
  EMD_RECEIPT: ['emd', 'earnest'],
  EMD_PAYMENT: ['emd', 'earnest'],
  AUDITED_FINANCIAL_STATEMENT: ['audit'],
  STARTUP_INDIA_CERTIFICATE: ['startup'],
  NSIC_CERTIFICATE: ['nsic'],
};

function matchRequirements(
  docType: string | null | undefined,
  requirements: TenderRequirement[]
): TenderRequirement[] {
  if (!docType || docType === 'UNCLASSIFIED') return [];
  if (docType === 'BID_DOSSIER') return requirements;
  const keywords = TYPE_REQUIREMENT_KEYWORDS[docType] ?? [];
  if (keywords.length === 0) return [];
  return requirements.filter((r) => {
    const haystack = `${r.requirement_name} ${r.threshold ?? ''} ${r.description ?? ''}`.toLowerCase();
    return keywords.some((k) => haystack.includes(k));
  });
}

/* ------------------------------------------------------------------ */
/* 6-step document pipeline (architecture-aligned names).              */
/* ------------------------------------------------------------------ */
const PIPELINE_STAGES = [
  { n: 1, title: 'Document Intake', desc: 'File received, validated & hash computed', icon: FileUp, layer: 'DOCUMENT_INGESTION' as const },
  { n: 2, title: 'AI Classification', desc: 'Document type identified using AI', icon: ScanSearch, layer: 'AI_ASSISTED' as const },
  { n: 3, title: 'Information Extraction', desc: 'Required fields extracted via OCR / Regex / LLM', icon: FileSearch, layer: 'AI_ASSISTED' as const },
  { n: 4, title: 'Evidence Mapping', desc: 'Extracted evidence mapped to tender requirements', icon: Layers, layer: 'RULE_ENGINE' as const },
  { n: 5, title: 'Statutory Verification', desc: 'Identifiers cross-checked against available verification sources', icon: ShieldCheck, layer: 'VERIFICATION' as const },
  { n: 6, title: 'Compliance Evaluation', desc: 'Deterministic rules calculate PASS / FAIL / MISSING / REVIEW REQUIRED', icon: Scale, layer: 'RULE_ENGINE' as const },
];

interface ProcessedDoc {
  fileName: string;
  doc: Document;
  fields: ExtractedField[];
  matched: TenderRequirement[];
}

/* Which verification sources apply to which document types (primary attribution).
   Identifier matching is the fallback. */
const SOURCE_DOC_TYPES: Record<string, string[]> = {
  GSTN: ['GST_CERTIFICATE', 'GST_RETURN'],
  PAN_IT: ['PAN_CERTIFICATE', 'ITR', 'ITR_DOCUMENT'],
  UDYAM: ['UDYAM_CERTIFICATE'],
  MCA21: ['MCA21_CERTIFICATE'],
  EPFO: ['EPFO_CERTIFICATE'],
  ESIC: ['ESIC_CERTIFICATE'],
};

const IDENTIFIER_FIELDS = new Set(['pan', 'gstin', 'udyam_number', 'cin', 'esic_code']);

function docIdentifiers(p: ProcessedDoc): string[] {
  return p.fields
    .filter((f) => IDENTIFIER_FIELDS.has(f.field_name))
    .map((f) => (f.normalized_value || f.field_value || '').trim().toUpperCase())
    .filter(Boolean);
}

function checksForDoc(p: ProcessedDoc, runChecks: VerificationCheck[]): VerificationCheck[] {
  const ids = new Set(docIdentifiers(p));
  return runChecks.filter((c) => {
    const types = SOURCE_DOC_TYPES[c.source];
    if (types && p.doc.document_type && types.includes(p.doc.document_type)) return true;
    return ids.size > 0 && ids.has((c.identifier || '').trim().toUpperCase());
  });
}

export default function Documents() {
  const { toast } = useToast();

  const [tenderId, setTenderId] = React.useState<number | null>(null);
  const [files, setFiles] = React.useState<File[]>([]);
  const [selectedSamples, setSelectedSamples] = React.useState<Set<string>>(new Set());
  const [analyzing, setAnalyzing] = React.useState(false);
  const [phase, setPhase] = React.useState('');
  const [sampleLoading, setSampleLoading] = React.useState(false);
  const [stageDone, setStageDone] = React.useState<number[]>([0, 0, 0, 0, 0, 0]);
  const [results, setResults] = React.useState<ProcessedDoc[]>([]);
  const [checks, setChecks] = React.useState<VerificationCheck[]>([]);
  const [compliance, setCompliance] = React.useState<ComplianceResult[]>([]);
  const [complianceScore, setComplianceScore] = React.useState<number | null>(null);
  const [selectedDocIdx, setSelectedDocIdx] = React.useState<number>(0);
  const [dragActive, setDragActive] = React.useState(false);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const { data: tenders = [] } = useQuery({
    queryKey: ['tenders'],
    queryFn: tendersApi.list,
  });

  React.useEffect(() => {
    if (!tenderId && tenders.length > 0) setTenderId(tenders[0].id);
  }, [tenders, tenderId]);

  const { data: bids = [] } = useQuery({
    queryKey: ['demo-bids', tenderId],
    queryFn: () => bidsApi.list(tenderId!),
    enabled: !!tenderId,
  });

  const { data: tenderDetail } = useQuery({
    queryKey: ['demo-tender', tenderId],
    queryFn: () => tendersApi.get(tenderId!),
    enabled: !!tenderId,
  });

  const demoBid: BidSummary | undefined = bids?.[0];
  const requirements = tenderDetail?.requirements ?? [];

  React.useEffect(() => {
    setResults([]);
    setStageDone([0, 0, 0, 0, 0, 0]);
    setSelectedDocIdx(0);
  }, [tenderId]);

  const bumpStage = (idx: number, value: number) =>
    setStageDone((prev) => {
      const next = [...prev];
      next[idx] = value;
      return next;
    });

  const addFiles = (incoming: File[]) => {
    const ok = incoming.filter((f) => /\.(pdf|png|jpe?g)$/i.test(f.name));
    if (ok.length < incoming.length) {
      toast({ title: 'Notice', description: 'Only PDF, JPG, JPEG, PNG files are accepted.' });
    }
    setFiles((prev) => {
      const names = new Set(prev.map((p) => p.name));
      return [...prev, ...ok.filter((f) => !names.has(f.name))];
    });
  };

  const removeFile = (name: string) =>
    setFiles((prev) => prev.filter((f) => f.name !== name));

  const toggleSample = (type: string) =>
    setSelectedSamples((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });

  const handleLoadSelected = async () => {
    const chosen = BENCHMARK_DOCS.filter((b) => selectedSamples.has(b.type));
    if (chosen.length === 0) {
      toast({ title: 'Select Documents', description: 'Tick at least one benchmark document first.' });
      return;
    }
    setSampleLoading(true);
    try {
      const loaded: File[] = [];
      for (const b of chosen) {
        const res = await fetch(b.file);
        if (!res.ok) throw new Error(`Sample not found: ${b.name}`);
        const blob = await res.blob();
        loaded.push(new File([blob], `${b.type.toLowerCase()}.pdf`, { type: 'application/pdf' }));
      }
      addFiles(loaded);
      toast({ title: 'Benchmark Documents Loaded', description: `${loaded.length} document(s) ready. Click 'Process N Documents'.` });
    } catch (err: unknown) {
      toast({ title: 'Notice', description: getErrorMessage(err) });
    } finally {
      setSampleLoading(false);
    }
  };

  const handleAnalyze = async () => {
    if (!demoBid) {
      toast({ title: 'No Bid', description: 'Select a tender with at least one bid first.' });
      return;
    }
    if (files.length === 0) {
      toast({ title: 'Select Files', description: 'Choose or load documents to test first.' });
      return;
    }
    const total = files.length;
    setAnalyzing(true);
    setResults([]);
    setChecks([]);
    setCompliance([]);
    setComplianceScore(null);
    setSelectedDocIdx(0);
    setStageDone([0, 0, 0, 0, 0, 0]);

    try {
      // Stages 1–3: upload each document; the upload pipeline classifies & extracts.
      const processed: ProcessedDoc[] = [];
      for (let i = 0; i < files.length; i++) {
        setPhase(`Document ${i + 1} of ${total}: uploading ${files[i].name}…`);
        const doc = await documentsApi.upload(demoBid.bid_id, files[i]);
        bumpStage(0, i + 1);
        setPhase(`Document ${i + 1} of ${total}: classifying & extracting…`);
        const detail = await documentsApi.get(doc.id);
        processed.push({
          fileName: files[i].name,
          doc: detail.document,
          fields: detail.extracted_fields ?? [],
          matched: [],
        });
        bumpStage(1, i + 1);
        bumpStage(2, i + 1);
      }

      // Stage 4: map each document's evidence to tender requirements.
      setPhase('Mapping extracted evidence to tender requirements…');
      processed.forEach((p, i) => {
        p.matched = matchRequirements(p.doc.document_type, requirements);
        bumpStage(3, i + 1);
      });

      // Stage 5: statutory verification (bid-level run, per-document attribution).
      let runChecks: VerificationCheck[] = [];
      const verifiable = processed.some(
        (p) => p.doc.processing_status === 'PROCESSED' && p.matched.length > 0
      );
      if (verifiable) {
        setPhase('Cross-checking identifiers against verification sources…');
        try {
          runChecks = (await verificationApi.run(demoBid.bid_id)).checks ?? [];
        } catch (err: unknown) {
          toast({ title: 'Verification Partially Failed', description: getErrorMessage(err) });
        }
      }
      const verifiedDocs = processed.filter((p) => checksForDoc(p, runChecks).length > 0).length;
      bumpStage(4, verifiedDocs);
      setChecks(runChecks);

      // Stage 6: compliance evaluation (bid-level, deterministic).
      setPhase('Evaluating compliance with deterministic rules…');
      try {
        const c = await complianceApi.evaluate(demoBid.bid_id);
        setCompliance(c.results ?? []);
        setComplianceScore(c.compliance_score ?? null);
        bumpStage(5, total);
      } catch (err: unknown) {
        toast({ title: 'Compliance Evaluation Failed', description: getErrorMessage(err) });
      }

      setResults(processed);
      toast({ title: 'Analysis Complete', description: `${processed.length} document(s) processed through the 6-stage pipeline.` });
    } catch (err: unknown) {
      toast({ title: 'Pipeline Error', description: getErrorMessage(err) });
    } finally {
      setAnalyzing(false);
      setPhase('');
    }
  };

  /* ---------------- derived batch data ---------------- */
  const totalReq = requirements.length;
  const received = results.length;
  const processedCount = results.filter((p) => p.doc.processing_status === 'PROCESSED').length;
  const classifiedCount = results.filter((p) => p.doc.document_type && p.doc.document_type !== 'UNCLASSIFIED').length;
  const extractionDone = results.filter((p) => p.fields.length > 0).length;
  const reviewRequired = results.filter((p) =>
    ['REVIEW_REQUIRED', 'FAILED', 'UNCLASSIFIED'].includes(p.doc.processing_status)
  ).length;

  const complianceByReq = new Map<number, ComplianceResult>();
  compliance.forEach((c) => complianceByReq.set(c.requirement_id, c));
  const passCount = compliance.filter((c) => c.status === 'PASS').length;
  const failCount = compliance.filter((c) => c.status === 'FAIL').length;
  const missingCount = compliance.filter((c) => c.status === 'MISSING').length;
  const reviewCount = compliance.filter((c) => c.status === 'REVIEW_REQUIRED').length;
  const supportedReqs = requirements.filter((r) => {
    const c = complianceByReq.get(r.id);
    return c && c.status !== 'MISSING';
  }).length;

  const selectedDoc = results[selectedDocIdx] ?? null;
  const anyMock = checks.some((c) => (c as unknown as { is_mock?: boolean }).is_mock);

  const docChecks = (p: ProcessedDoc): VerificationCheck[] => checksForDoc(p, checks);

  const docVerificationStatus = (p: ProcessedDoc): VerificationStatus | null => {
    const hit = docChecks(p);
    if (hit.length === 0) return null;
    if (hit.some((c) => ['MISMATCH', 'FAILED'].includes(c.verification_status))) return 'MISMATCH';
    if (hit.some((c) => c.verification_status === 'VERIFIED')) return 'VERIFIED';
    return 'REVIEW_REQUIRED';
  };

  const docComplianceSummary = (p: ProcessedDoc): RequirementStatus | null => {
    if (compliance.length === 0 || p.matched.length === 0) return null;
    const statuses = p.matched
      .map((r) => complianceByReq.get(r.id)?.status)
      .filter(Boolean) as RequirementStatus[];
    if (statuses.length === 0) return null;
    if (statuses.includes('FAIL')) return 'FAIL';
    if (statuses.includes('MISMATCH')) return 'MISMATCH';
    if (statuses.includes('REVIEW_REQUIRED')) return 'REVIEW_REQUIRED';
    if (statuses.includes('MISSING')) return 'MISSING';
    return 'PASS';
  };

  return (
    <div className="space-y-6">
      {/* 1. Header */}
      <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-blue-800 dark:text-blue-400 font-mono">
                Verification Laboratory
              </span>
              <SystemLayerTag layer="AI_ASSISTED" size="sm" />
            </div>
            <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 font-serif">
              Test Your Document
            </h1>
            <p className="mt-0.5 text-xs text-slate-600 dark:text-slate-400">
              Upload one bidder document or a full batch — every file runs the same 6-stage pipeline: intake, classification, extraction, evidence mapping, statutory verification, compliance evaluation.
            </p>
          </div>
        </div>
      </div>

      {/* 2. Pipeline stages with batch progress */}
      <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-xs overflow-x-auto">
        <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3 mb-4">
          <span className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200">
            Document Intelligence &amp; Verification Pipeline
          </span>
          <span className="text-[11px] text-slate-500 dark:text-slate-400 font-mono">
            Status: {analyzing ? phase : results.length > 0 ? 'Pipeline Execution Complete' : 'Awaiting Document Input'}
          </span>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          {PIPELINE_STAGES.map((s, idx) => {
            const Icon = s.icon;
            const done = stageDone[idx];
            const total = Math.max(files.length, results.length, 1);
            const isActive = analyzing && done < total;
            const isComplete = !analyzing && results.length > 0 && done >= total && total > 0;
            return (
              <div
                key={s.n}
                className={cn(
                  'rounded border p-3 text-xs transition-colors flex flex-col justify-between',
                  isActive
                    ? 'border-blue-700 bg-blue-50/80 dark:bg-blue-950/50 shadow-xs'
                    : isComplete
                    ? 'border-emerald-300 dark:border-emerald-700 bg-emerald-50/50 dark:bg-emerald-950/40'
                    : 'border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-950 text-slate-400 dark:text-slate-500'
                )}
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span
                      className={cn(
                        'flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-bold',
                        isActive
                          ? 'bg-blue-800 text-white animate-pulse'
                          : isComplete
                          ? 'bg-emerald-600 text-white'
                          : 'bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-400'
                      )}
                    >
                      {isComplete ? <CheckCircle2 className="h-3.5 w-3.5" /> : s.n}
                    </span>
                    <SystemLayerTag layer={s.layer} size="sm" />
                  </div>
                  <h4
                    className={cn(
                      'font-bold text-xs',
                      isActive
                        ? 'text-blue-950 dark:text-blue-200'
                        : isComplete
                        ? 'text-emerald-950 dark:text-emerald-200'
                        : 'text-slate-700 dark:text-slate-200'
                    )}
                  >
                    {s.title}
                  </h4>
                  <p className="mt-1 text-[10.5px] text-slate-500 dark:text-slate-400 leading-snug">{s.desc}</p>
                  {(analyzing || results.length > 0) && (
                    <p className="mt-1.5 font-mono text-[11px] font-bold text-slate-700 dark:text-slate-300">
                      {done} / {total}
                    </p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 3. Tender + upload area */}
      <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-xs">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Target tender + benchmark documents */}
          <div className="space-y-4 border-b lg:border-b-0 lg:border-r border-slate-200 dark:border-slate-800 lg:pr-6 pb-6 lg:pb-0">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-slate-200 mb-1">
                Target Procurement Package
              </label>
              <Select
                value={tenderId || ''}
                onChange={(e) => setTenderId(Number(e.target.value))}
                className="text-xs border-slate-300 dark:border-slate-700"
              >
                {tenders.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.tender_number} — {t.title.slice(0, 35)}...
                  </option>
                ))}
              </Select>
            </div>

            <div className="rounded border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 p-3 text-xs">
              <span className="text-slate-500 dark:text-slate-400 block font-medium">Evaluation Target:</span>
              <span className="font-semibold text-slate-900 dark:text-slate-100 block mt-0.5">
                {demoBid?.legal_name || 'Demo Bidder Entity'}
              </span>
              <span className="text-[11px] text-slate-500 dark:text-slate-400 mt-1 block">
                {totalReq} Requirements · {totalReq} Expected Documents
              </span>
            </div>

            {/* Benchmark documents — selectable */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-slate-200">
                  Quick-Load Benchmark Documents
                </span>
              </div>
              <div className="mb-2 flex gap-2">
                <button
                  type="button"
                  onClick={() => setSelectedSamples(new Set(BENCHMARK_DOCS.map((b) => b.type)))}
                  className="text-[11px] font-semibold text-blue-700 dark:text-blue-400 hover:underline"
                >
                  Select All
                </button>
                <span className="text-slate-300 dark:text-slate-600">|</span>
                <button
                  type="button"
                  onClick={() => setSelectedSamples(new Set())}
                  className="text-[11px] font-semibold text-blue-700 dark:text-blue-400 hover:underline"
                >
                  Clear
                </button>
              </div>
              <div className="max-h-64 space-y-1.5 overflow-y-auto pr-1">
                {BENCHMARK_DOCS.map((b) => (
                  <label
                    key={b.type}
                    className="flex cursor-pointer items-center gap-2.5 rounded border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-2 text-xs hover:border-blue-400 transition-colors"
                  >
                    <input
                      type="checkbox"
                      checked={selectedSamples.has(b.type)}
                      onChange={() => toggleSample(b.type)}
                      disabled={sampleLoading || analyzing}
                      className="h-3.5 w-3.5 shrink-0 accent-blue-800"
                    />
                    <div className="min-w-0">
                      <p className="font-semibold text-slate-800 dark:text-slate-200 truncate">{b.name}</p>
                      <p className="text-[10.5px] text-slate-500 dark:text-slate-400 truncate">{b.desc}</p>
                    </div>
                  </label>
                ))}
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={handleLoadSelected}
                disabled={sampleLoading || analyzing || selectedSamples.size === 0}
                className="mt-2 w-full border-slate-300 dark:border-slate-700 text-xs"
              >
                <Download className="mr-1.5 h-3.5 w-3.5" />
                {sampleLoading ? 'Loading…' : `Load Selected (${selectedSamples.size})`}
              </Button>
            </div>
          </div>

          {/* Multi-document dropzone */}
          <div className="lg:col-span-2 flex flex-col justify-between">
            <div>
              <div
                onClick={() => fileInputRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
                onDragLeave={() => setDragActive(false)}
                onDrop={(e) => { e.preventDefault(); setDragActive(false); addFiles(Array.from(e.dataTransfer.files)); }}
                className={cn(
                  'rounded-lg border-2 border-dashed p-8 text-center cursor-pointer transition-colors',
                  dragActive
                    ? 'border-blue-600 bg-blue-50/40 dark:bg-blue-950/40'
                    : 'border-slate-300 dark:border-slate-700 hover:border-blue-500 bg-slate-50 dark:bg-slate-900 hover:bg-blue-50/20'
                )}
              >
                <UploadCloud className="mx-auto h-10 w-10 text-blue-700 dark:text-blue-400" />
                <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-slate-100">
                  Upload Bidder Documents
                </p>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  Drag &amp; drop multiple files or click to browse
                </p>
                <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                  Supported: PDF, JPG, JPEG, PNG — up to 20 MB per file
                </p>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.png,.jpg,.jpeg"
                  multiple
                  className="hidden"
                  onChange={(e) => { addFiles(Array.from(e.target.files ?? [])); e.target.value = ''; }}
                />
              </div>

              {/* Selected file list */}
              {files.length > 0 && (
                <div className="mt-4 rounded-lg border border-slate-200 dark:border-slate-800">
                  <div className="border-b border-slate-100 dark:border-slate-800 px-4 py-2.5 flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-200">
                      Selected Files ({files.length})
                    </span>
                    <button
                      type="button"
                      onClick={() => setFiles([])}
                      className="text-[11px] font-semibold text-red-600 dark:text-red-400 hover:underline"
                    >
                      Remove all
                    </button>
                  </div>
                  <ul className="max-h-48 divide-y divide-slate-100 dark:divide-slate-800 overflow-y-auto">
                    {files.map((f) => (
                      <li key={f.name} className="flex items-center gap-3 px-4 py-2 text-xs">
                        <FileText className="h-4 w-4 shrink-0 text-blue-700 dark:text-blue-400" />
                        <span className="min-w-0 flex-1 truncate font-medium text-slate-800 dark:text-slate-200">{f.name}</span>
                        <span className="font-mono text-[10.5px] text-slate-500 dark:text-slate-400 shrink-0">
                          {(f.size / 1024).toFixed(1)} KB
                        </span>
                        <button
                          type="button"
                          onClick={() => removeFile(f.name)}
                          aria-label={`Remove ${f.name}`}
                          className="rounded-full p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-700 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            <div className="mt-6 flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-4 border-t border-slate-200 dark:border-slate-800">
              <span className="text-xs text-slate-500 dark:text-slate-400">
                Runs the 6-stage pipeline per document, then consolidates verification &amp; compliance.
              </span>
              <Button
                onClick={handleAnalyze}
                disabled={files.length === 0 || analyzing}
                loading={analyzing}
                className="bg-blue-800 hover:bg-blue-900 text-white text-xs font-medium py-2.5 px-5 shadow-xs"
              >
                {analyzing ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Executing Pipeline...
                  </>
                ) : (
                  <>
                    <Sparkles className="mr-2 h-4 w-4 text-blue-200" />
                    Process {files.length} Document{files.length === 1 ? '' : 's'}
                  </>
                )}
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* 4. BATCH RESULTS */}
      {results.length > 0 && (
        <div className="space-y-6">
          {/* A. Batch processing summary */}
          <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-xs">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3 mb-4">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200">
                  Document Processing Summary
                </span>
                <SystemLayerTag layer="DOCUMENT_INGESTION" size="sm" />
              </div>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 text-center">
              {[
                { label: 'Documents Received', value: received },
                { label: 'Documents Processed', value: processedCount },
                { label: 'Successfully Classified', value: classifiedCount },
                { label: 'Extraction Complete', value: extractionDone },
                { label: 'Verification Complete', value: stageDone[4] },
                { label: 'Review Required', value: reviewRequired },
              ].map((s) => (
                <div key={s.label} className="rounded-md border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-950 p-3">
                  <p className="text-2xl font-bold text-slate-900 dark:text-slate-100">{s.value}</p>
                  <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400 leading-tight">{s.label}</p>
                </div>
              ))}
            </div>
            <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
              {totalReq} Requirements · {received} Documents Received · {Math.max(totalReq - supportedReqs, 0)} Expected Evidence Missing
            </p>
          </div>

          {/* B. Processed documents table */}
          <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-xs">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3 mb-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200">
                Processed Bidder Documents ({results.length})
              </h3>
              <span className="text-[11px] text-slate-500 dark:text-slate-400">Click a row for extraction detail</span>
            </div>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-800/60 text-[10.5px] font-bold text-slate-600 dark:text-slate-400 uppercase tracking-wider">
                    <TableHead className="py-2.5 px-3">Document</TableHead>
                    <TableHead className="py-2.5 px-3">Classification</TableHead>
                    <TableHead className="py-2.5 px-3">Extraction</TableHead>
                    <TableHead className="py-2.5 px-3">Verification</TableHead>
                    <TableHead className="py-2.5 px-3">Compliance</TableHead>
                  </tr>
                </TableHeader>
                <TableBody>
                  {results.map((p, i) => (
                    <TableRow
                      key={p.doc.id}
                      onClick={() => setSelectedDocIdx(i)}
                      className={cn(
                        'cursor-pointer text-xs hover:bg-slate-50/60 dark:hover:bg-slate-800/70',
                        i === selectedDocIdx && 'bg-blue-50/60 dark:bg-blue-950/40'
                      )}
                    >
                      <TableCell className="py-2.5 px-3 font-medium text-slate-900 dark:text-slate-100">
                        {p.fileName}
                      </TableCell>
                      <TableCell className="py-2.5 px-3">
                        <DocTypeBadge docType={(p.doc.document_type as DocumentType) || 'UNCLASSIFIED'} />
                      </TableCell>
                      <TableCell className="py-2.5 px-3 text-slate-600 dark:text-slate-400">
                        {p.fields.length > 0 ? `${p.fields.length} fields` : 'Failed'}
                      </TableCell>
                      <TableCell className="py-2.5 px-3">
                        {(() => {
                          const vs = docVerificationStatus(p);
                          return vs ? (
                            <VerificationBadge status={vs} />
                          ) : (
                            <span className="text-slate-400 dark:text-slate-500">Not Run</span>
                          );
                        })()}
                      </TableCell>
                      <TableCell className="py-2.5 px-3">
                        {(() => {
                          const cs = docComplianceSummary(p);
                          return cs ? (
                            <StatusBadge status={cs} />
                          ) : (
                            <span className="text-slate-400 dark:text-slate-500">—</span>
                          );
                        })()}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>

          {/* C. Document-specific extraction */}
          {selectedDoc && (
            <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-xs">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 dark:border-slate-800 pb-3 mb-3">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200">
                  Information Extraction — {selectedDoc.fileName} ({selectedDoc.fields.length})
                </h3>
                <div className="flex items-center gap-2">
                  <DocTypeBadge docType={(selectedDoc.doc.document_type as DocumentType) || 'UNCLASSIFIED'} />
                  <DocStatusBadge status={selectedDoc.doc.processing_status} />
                </div>
              </div>
              {selectedDoc.fields.length > 0 ? (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-800/60 text-[10.5px] font-bold text-slate-600 dark:text-slate-400 uppercase tracking-wider">
                        <TableHead className="py-2.5 px-3">Field Name</TableHead>
                        <TableHead className="py-2.5 px-3">Extracted Value</TableHead>
                        <TableHead className="py-2.5 px-3">Normalized Value</TableHead>
                        <TableHead className="py-2.5 px-3 text-center">Extraction Method</TableHead>
                      </tr>
                    </TableHeader>
                    <TableBody>
                      {selectedDoc.fields.map((f) => (
                        <TableRow key={f.id} className="hover:bg-slate-50/60 dark:hover:bg-slate-800/70 text-xs">
                          <TableCell className="py-2.5 px-3 font-semibold text-slate-900 dark:text-slate-100 font-mono">
                            {f.field_name}
                          </TableCell>
                          <TableCell className="py-2.5 px-3 font-medium text-slate-800 dark:text-slate-200">
                            {f.field_value}
                          </TableCell>
                          <TableCell className="py-2.5 px-3 text-slate-600 dark:text-slate-400 font-mono">
                            {f.normalized_value || '—'}
                          </TableCell>
                          <TableCell className="py-2.5 px-3 text-center">
                            <MethodBadge method={f.extraction_method} />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              ) : (
                <p className="text-xs text-slate-400 dark:text-slate-500 italic">No fields extracted from this document.</p>
              )}
            </div>
          )}

          {/* D. Evidence mapping */}
          <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-xs">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3 mb-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200">
                Mapped Evidence &amp; Tender Requirements
              </h3>
              <SystemLayerTag layer="RULE_ENGINE" size="sm" />
            </div>
            <div className="mb-4 flex flex-wrap gap-x-6 gap-y-2 text-xs">
              <span className="text-slate-600 dark:text-slate-400"><strong className="text-slate-900 dark:text-slate-100">{totalReq}</strong> Total Requirements</span>
              <span className="text-slate-600 dark:text-slate-400"><strong className="text-emerald-700 dark:text-emerald-400">{supportedReqs}</strong> Supported by Evidence</span>
              <span className="text-slate-600 dark:text-slate-400"><strong className="text-red-700 dark:text-red-400">{failCount}</strong> Mismatch</span>
              <span className="text-slate-600 dark:text-slate-400"><strong className="text-amber-700 dark:text-amber-400">{missingCount}</strong> Missing</span>
              <span className="text-slate-600 dark:text-slate-400"><strong className="text-amber-700 dark:text-amber-400">{reviewCount}</strong> Review Required</span>
            </div>
            {requirements.length > 0 ? (
              <div className="space-y-2.5">
                {requirements.map((req) => {
                  const supporting = results.filter((p) =>
                    p.matched.some((m) => m.id === req.id)
                  );
                  const comp = complianceByReq.get(req.id);
                  const status: RequirementStatus | null =
                    comp?.status ?? (supporting.length > 0 ? null : 'MISSING');
                  return (
                    <div key={req.id} className="rounded border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-950 p-3 text-xs">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-semibold text-slate-900 dark:text-slate-100">{req.requirement_name}</span>
                        {status ? (
                          <StatusBadge status={status} />
                        ) : (
                          <span className="text-[11px] font-medium text-slate-500 dark:text-slate-400">
                            Evidence present — not evaluated
                          </span>
                        )}
                      </div>
                      <p className="mt-1 text-slate-600 dark:text-slate-400">
                        Evidence: {supporting.length > 0 ? supporting.map((p) => p.fileName).join(', ') : '—'}
                      </p>
                      {comp?.explanation && (
                        <p className="mt-0.5 text-slate-500 dark:text-slate-400">Status: {comp.explanation}</p>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-xs text-slate-400 dark:text-slate-500 italic">No tender requirements to map against.</p>
            )}
          </div>

          {/* E. Statutory verification */}
          <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-xs">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3 mb-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200">
                Statutory Verification
              </h3>
              <SystemLayerTag layer="VERIFICATION" size="sm" />
            </div>
            {anyMock && (
              <p className="mb-3 rounded-md border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/60 px-3 py-2 text-[11px] text-amber-900 dark:text-amber-300">
                <MockSourceLabel /> Demo/Mock source — not connected to live government systems.
              </p>
            )}
            {checks.length > 0 ? (
              <div className="space-y-2.5">
                {checks.map((chk) => (
                  <div key={chk.id} className="rounded border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-950 p-3 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-semibold font-mono text-slate-900 dark:text-slate-100">
                        {chk.source} <span className="font-sans font-normal text-slate-500 dark:text-slate-400">{chk.identifier}</span>
                      </span>
                      <VerificationBadge status={chk.verification_status} />
                    </div>
                    <p className="mt-1 text-slate-600 dark:text-slate-400">
                      {chk.evidence_reference || 'Verification executed against available source.'}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-400 dark:text-slate-500 italic">
                No statutory checks were triggered for these documents.
              </p>
            )}
          </div>

          {/* F. Compliance evaluation */}
          <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-xs">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3 mb-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200">
                Compliance Evaluation
              </h3>
              <SystemLayerTag layer="RULE_ENGINE" size="sm" />
            </div>
            {compliance.length > 0 ? (
              <>
                <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs">
                  <span className="text-slate-600 dark:text-slate-400">
                    Overall Compliance Score:{' '}
                    <strong className="font-mono text-base text-slate-900 dark:text-slate-100">
                      {complianceScore !== null ? `${Math.round(complianceScore)} / 100` : '—'}
                    </strong>
                  </span>
                  <span className="text-slate-600 dark:text-slate-400"><strong className="text-emerald-700 dark:text-emerald-400">{passCount}</strong> PASS</span>
                  <span className="text-slate-600 dark:text-slate-400"><strong className="text-red-700 dark:text-red-400">{failCount}</strong> FAIL</span>
                  <span className="text-slate-600 dark:text-slate-400"><strong className="text-amber-700 dark:text-amber-400">{missingCount}</strong> MISSING</span>
                  <span className="text-slate-600 dark:text-slate-400"><strong className="text-amber-700 dark:text-amber-400">{reviewCount}</strong> REVIEW REQUIRED</span>
                </div>
                {(failCount > 0 || missingCount > 0) && (
                  <div className="mt-3 rounded-md border border-red-200 dark:border-red-800 bg-red-50/60 dark:bg-red-950/40 px-3 py-2.5 text-xs text-red-900 dark:text-red-300">
                    <span className="font-semibold">Important: </span>
                    A weighted score does not override mandatory FAIL / MISSING requirements.
                    {compliance.filter((c) => c.status === 'FAIL' || c.status === 'MISSING')
                      .slice(0, 4)
                      .map((c) => ` ${c.requirement?.requirement_name ?? 'Requirement'} (${labelize(c.status)})`).join(';')}
                    {(failCount + missingCount) > 4 ? '…' : ''}
                  </div>
                )}
                <div className="mt-4 overflow-x-auto rounded-md border border-slate-200 dark:border-slate-800">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-slate-50 dark:bg-slate-900 text-left text-slate-500 dark:text-slate-400">
                        <th className="px-3 py-2 font-semibold">Requirement</th>
                        <th className="px-3 py-2 font-semibold">Result</th>
                        <th className="px-3 py-2 font-semibold">Weight</th>
                        <th className="px-3 py-2 font-semibold">Observation</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                      {compliance.map((c) => (
                        <tr key={c.id}>
                          <td className="px-3 py-2 font-medium text-slate-900 dark:text-slate-100">
                            {c.requirement?.requirement_name ?? `Requirement #${c.requirement_id}`}
                          </td>
                          <td className="px-3 py-2"><StatusBadge status={c.status} /></td>
                          <td className="px-3 py-2 font-mono text-slate-600 dark:text-slate-400">{c.weight}%</td>
                          <td className="px-3 py-2 text-slate-600 dark:text-slate-400">{c.explanation || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              <p className="text-xs text-slate-400 dark:text-slate-500 italic">
                Compliance has not been evaluated for this batch yet.
              </p>
            )}
            <p className="mt-3 flex items-start gap-1.5 text-[11px] text-slate-500 dark:text-slate-400">
              <Info className="h-3.5 w-3.5 shrink-0 mt-0.5" />
              The deterministic compliance engine is authoritative for these results. Risk analysis and integrity findings are separate bid-level layers and are not part of this document pipeline.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
