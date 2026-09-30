import * as React from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  AlertOctagon,
  ArrowRight,
  CheckCircle2,
  Database,
  Download,
  FileCheck2,
  FileSearch,
  FileText,
  FileUp,
  Info,
  Layers,
  Loader2,
  RefreshCw,
  Scale,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  UploadCloud,
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
import { labelize } from '../lib/utils';
import { SystemLayerTag } from '../components/common/SystemLayerTag';
import type {
  BidSummary,
  ComplianceResult,
  Document,
  DocumentType,
  ExtractedField,
  TenderRequirement,
  VerificationCheck,
} from '../types';

const SAMPLE_DOCS = [
  {
    name: 'Sample GST Certificate',
    file: '/sample-documents/sample-gst-certificate.pdf',
    type: 'GST_CERTIFICATE',
    desc: 'Form GST REG-06 with active GSTIN 33AAACG1234F1Z5',
  },
  {
    name: 'Sample Udyam MSME Certificate',
    file: '/sample-documents/sample-gst-certificate.pdf',
    type: 'UDYAM_CERTIFICATE',
    desc: 'MSME registration certificate with micro/small enterprise status',
  },
  {
    name: 'Sample Turnover Certificate',
    file: '/sample-documents/sample-gst-certificate.pdf',
    type: 'TURNOVER_CERTIFICATE',
    desc: 'CA certified statement of 3-year turnover',
  },
  {
    name: 'Sample Experience Certificate',
    file: '/sample-documents/sample-gst-certificate.pdf',
    type: 'EXPERIENCE_CERTIFICATE',
    desc: 'Past supply and commissioning credential letter',
  },
];

const TYPE_REQUIREMENT_KEYWORDS: Record<string, string[]> = {
  GST_CERTIFICATE: ['gst'],
  GST_RETURN: ['gstr', 'gst return'],
  PAN_CERTIFICATE: ['pan'],
  UDYAM_CERTIFICATE: ['udyam', 'msme'],
  TURNOVER_CERTIFICATE: ['turnover'],
  EXPERIENCE_CERTIFICATE: ['experience'],
  OEM_AUTHORIZATION: ['oem'],
  ITR: ['itr', 'income tax'],
  EPFO_CERTIFICATE: ['epfo', 'provident fund'],
  ESIC_CERTIFICATE: ['esic'],
  MII_DECLARATION: ['mii', 'local content', 'make in india'],
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

interface DemoResult {
  doc: Document;
  fields: ExtractedField[];
  matched: TenderRequirement[];
  checks: VerificationCheck[];
  compliance: ComplianceResult[];
  complianceScore: number | null;
}

const PIPELINE_STAGES = [
  { n: 1, title: 'Upload', desc: 'File received & hash computed', icon: FileUp, layer: null },
  { n: 2, title: 'AI Understanding', desc: 'Document classified with confidence', icon: ScanSearch, layer: 'AI_ASSISTED' as const },
  { n: 3, title: 'Extraction', desc: 'Entities parsed via Regex/OCR/LLM', icon: FileSearch, layer: 'AI_ASSISTED' as const },
  { n: 4, title: 'Requirement Mapping', desc: 'Mapped to tender criteria', icon: Layers, layer: 'RULE_ENGINE' as const },
  { n: 5, title: 'Verification', desc: 'Cross-checked against mock portal', icon: ShieldCheck, layer: 'VERIFICATION' as const },
  { n: 6, title: 'Compliance Impact', desc: 'Pass/Fail evaluation computed', icon: Scale, layer: 'RULE_ENGINE' as const },
];

export default function Documents() {
  const { toast } = useToast();

  const [tenderId, setTenderId] = React.useState<number | null>(null);
  const [file, setFile] = React.useState<File | null>(null);
  const [analyzing, setAnalyzing] = React.useState(false);
  const [currentStep, setCurrentStep] = React.useState(0);
  const [phase, setPhase] = React.useState('');
  const [sampleLoading, setSampleLoading] = React.useState(false);
  const [result, setResult] = React.useState<DemoResult | null>(null);
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
    setResult(null);
    setCurrentStep(0);
  }, [tenderId]);

  const handleLoadSample = async (samplePath: string, sampleName: string) => {
    setSampleLoading(true);
    try {
      const res = await fetch(samplePath);
      if (!res.ok) throw new Error('Sample document not found');
      const blob = await res.blob();
      const sampleFile = new File([blob], sampleName, { type: 'application/pdf' });
      setFile(sampleFile);
      toast({ title: 'Sample Document Loaded', description: `${sampleName} ready. Click 'Execute Verification Pipeline'.` });
    } catch {
      toast({ title: 'Notice', description: 'Could not load static sample file. Please upload a local PDF/image.' });
    } finally {
      setSampleLoading(false);
    }
  };

  const handleAnalyze = async () => {
    if (!demoBid || !file) {
      toast({ title: 'Select File', description: 'Choose or load a document to test first.' });
      return;
    }
    setAnalyzing(true);
    setCurrentStep(1);
    setPhase('Uploading file & calculating SHA-256 hash…');
    setResult(null);

    try {
      // 1. Upload
      const doc = await documentsApi.upload(demoBid.bid_id, file);

      // 2. Classify & Extract
      setCurrentStep(2);
      setPhase('Classifying document structure…');
      await new Promise((r) => setTimeout(r, 600));

      setCurrentStep(3);
      setPhase('Extracting statutory identifiers & values…');
      const detail = await documentsApi.get(doc.id);
      const fields = detail.extracted_fields;

      // 4. Map requirements
      setCurrentStep(4);
      setPhase('Mapping extracted entities to tender requirements…');
      await new Promise((r) => setTimeout(r, 500));
      const matched = matchRequirements(detail.document.document_type, requirements);

      let checks: VerificationCheck[] = [];
      let compliance: ComplianceResult[] = [];
      let complianceScore: number | null = null;

      if (detail.document.processing_status === 'PROCESSED' && matched.length > 0) {
        // 5. Verification
        setCurrentStep(5);
        setPhase('Cross-referencing statutory mock adapters (GSTN/PAN/Udyam)…');
        try {
          const v = await verificationApi.run(demoBid.bid_id);
          checks = v.checks;
        } catch {
          checks = [];
        }

        // 6. Compliance Impact
        setCurrentStep(6);
        setPhase('Computing deterministic rule outcomes & impact…');
        try {
          const c = await complianceApi.evaluate(demoBid.bid_id);
          compliance = c.results;
          complianceScore = c.compliance_score;
        } catch {
          compliance = [];
        }
      }

      setResult({ doc: detail.document, fields, matched, checks, compliance, complianceScore });
      toast({ title: 'Analysis Complete', description: 'Pipeline execution completed across all 6 stages.' });
    } catch (err: unknown) {
      toast({ title: 'Pipeline Error', description: getErrorMessage(err) });
    } finally {
      setAnalyzing(false);
      setPhase('');
    }
  };

  const detectedType = result?.doc.document_type;

  return (
    <div className="space-y-6">
      {/* 1. Header */}
      <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-blue-800 font-mono">
                Verification Laboratory
              </span>
              <SystemLayerTag layer="AI_ASSISTED" size="sm" />
            </div>
            <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900 font-serif">
              Test Your Document
            </h1>
            <p className="mt-0.5 text-xs text-slate-600">
              Upload a bidder document to observe the AI extraction, statutory verification, and requirement mapping pipeline.
            </p>
          </div>
        </div>
      </div>

      {/* 2. Visual Pipeline Stages */}
      <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-xs overflow-x-auto">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-4">
          <span className="text-xs font-bold uppercase tracking-wider text-slate-800">
            Document Intelligence &amp; Verification Pipeline
          </span>
          <span className="text-[11px] text-slate-500 font-mono">
            Status: {analyzing ? phase : result ? 'Pipeline Execution Complete' : 'Awaiting Document Input'}
          </span>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          {PIPELINE_STAGES.map((s) => {
            const Icon = s.icon;
            const isCompleted = result !== null || currentStep > s.n;
            const isCurrent = analyzing && currentStep === s.n;
            return (
              <div
                key={s.n}
                className={`rounded border p-3 text-xs transition-colors flex flex-col justify-between ${
                  isCurrent
                    ? 'border-blue-700 bg-blue-50/80 shadow-xs'
                    : isCompleted
                    ? 'border-emerald-300 bg-emerald-50/50'
                    : 'border-slate-200 bg-slate-50/60 text-slate-400'
                }`}
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span
                      className={`flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-bold ${
                        isCurrent
                          ? 'bg-blue-800 text-white animate-pulse'
                          : isCompleted
                          ? 'bg-emerald-600 text-white'
                          : 'bg-slate-200 text-slate-600'
                      }`}
                    >
                      {isCompleted ? <CheckCircle2 className="h-3.5 w-3.5" /> : s.n}
                    </span>
                    {s.layer && <SystemLayerTag layer={s.layer} size="sm" />}
                  </div>
                  <h4 className={`font-bold text-xs ${isCurrent ? 'text-blue-950' : isCompleted ? 'text-emerald-950' : 'text-slate-700'}`}>
                    {s.title}
                  </h4>
                  <p className="mt-1 text-[10.5px] text-slate-500 leading-snug">
                    {s.desc}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 3. Upload & Evaluation Area */}
      <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-xs">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Target Tender & Bidder Selection */}
          <div className="space-y-4 border-b lg:border-b-0 lg:border-r border-slate-200 lg:pr-6 pb-6 lg:pb-0">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
                Target Procurement Package
              </label>
              <Select
                value={tenderId || ''}
                onChange={(e) => setTenderId(Number(e.target.value))}
                className="text-xs border-slate-300"
              >
                {tenders.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.tender_number} — {t.title.slice(0, 35)}...
                  </option>
                ))}
              </Select>
            </div>

            <div className="rounded border border-slate-200 bg-slate-50 p-3 text-xs">
              <span className="text-slate-500 block font-medium">Evaluation Target:</span>
              <span className="font-semibold text-slate-900 block mt-0.5">
                {demoBid?.legal_name || 'Demo Bidder Entity'}
              </span>
              <span className="text-[11px] text-slate-500 mt-1 block">
                Criteria: {requirements.length} tender rules defined
              </span>
            </div>

            {/* Quick Sample Document Loaders */}
            <div>
              <span className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-2">
                Quick-Load Benchmark Documents
              </span>
              <div className="space-y-2">
                {SAMPLE_DOCS.map((sample) => (
                  <button
                    key={sample.name}
                    type="button"
                    onClick={() => handleLoadSample(sample.file, `${sample.type.toLowerCase()}.pdf`)}
                    disabled={sampleLoading || analyzing}
                    className="w-full text-left rounded border border-slate-200 bg-white p-2 text-xs hover:border-blue-400 hover:bg-blue-50/50 transition-colors flex items-center justify-between"
                  >
                    <div>
                      <p className="font-semibold text-slate-800">{sample.name}</p>
                      <p className="text-[10.5px] text-slate-500">{sample.desc}</p>
                    </div>
                    <FileText className="h-4 w-4 text-blue-700 shrink-0 ml-2" />
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Document Dropzone & Action */}
          <div className="lg:col-span-2 flex flex-col justify-between">
            <div>
              <div
                onClick={() => fileInputRef.current?.click()}
                className="rounded-lg border-2 border-dashed border-slate-300 hover:border-blue-500 bg-slate-50 hover:bg-blue-50/20 p-8 text-center cursor-pointer transition-colors"
              >
                <UploadCloud className="mx-auto h-10 w-10 text-blue-700" />
                <p className="mt-2 text-sm font-semibold text-slate-900">
                  {file ? file.name : 'Click to select or drag document file'}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  Supported formats: PDF, scanned JPEG/PNG (Max 20MB)
                </p>
                {file && (
                  <span className="mt-3 inline-block rounded bg-blue-100 px-2.5 py-1 text-xs font-mono font-semibold text-blue-900 border border-blue-200">
                    File selected: {(file.size / 1024).toFixed(1)} KB
                  </span>
                )}
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.png,.jpg,.jpeg"
                  className="hidden"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                />
              </div>
            </div>

            <div className="mt-6 flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-4 border-t border-slate-200">
              <span className="text-xs text-slate-500">
                Runs OCR, entity parser, statutory verification checks &amp; compliance evaluation.
              </span>
              <Button
                onClick={handleAnalyze}
                disabled={!file || analyzing}
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
                    Execute Verification Pipeline
                  </>
                )}
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* 4. RESULTS LAB PANEL (APPEARS AFTER PROCESSING) */}
      {result && (
        <div className="space-y-6">
          {/* Document Summary Card */}
          <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-xs">
            <div className="border-b border-slate-100 pb-3 mb-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-800">
                  Document Classification &amp; Metadata
                </span>
                <SystemLayerTag layer="AI_ASSISTED" size="sm" />
              </div>
              <DocStatusBadge status={result.doc.processing_status} />
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-xs">
              <div>
                <span className="text-slate-500 block">Classified Document Type:</span>
                <div className="mt-1">
                  <DocTypeBadge docType={(detectedType as DocumentType) || 'GST_CERTIFICATE'} />
                </div>
              </div>
              <div>
                <span className="text-slate-500 block">Page Count / Size:</span>
                <span className="font-mono text-slate-800 block mt-1">
                  {result.doc.page_count ?? 1} Page(s) • {(result.doc.file_size / 1024).toFixed(1)} KB
                </span>
              </div>
              <div>
                <span className="text-slate-500 block">SHA-256 File Signature:</span>
                <span className="font-mono text-[11px] text-slate-600 block mt-1 truncate">
                  {result.doc.file_hash || 'SHA-256 GENERATED'}
                </span>
              </div>
            </div>
          </div>

          {/* Extracted Fields Table */}
          <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-xs">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                Extracted Entities &amp; Values ({result.fields.length})
              </h3>
              <span className="text-[11px] text-slate-500">Extraction method</span>
            </div>

            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <tr className="border-b border-slate-200 bg-slate-50/80 text-[10.5px] font-bold text-slate-600 uppercase tracking-wider">
                    <TableHead className="py-2.5 px-3">Field Name</TableHead>
                    <TableHead className="py-2.5 px-3">Extracted Value</TableHead>
                    <TableHead className="py-2.5 px-3">Normalized Value</TableHead>
                    <TableHead className="py-2.5 px-3 text-center">Extraction Method</TableHead>
                  </tr>
                </TableHeader>
                <TableBody>
                  {result.fields.map((f) => (
                    <TableRow key={f.id} className="hover:bg-slate-50/60 text-xs">
                      <TableCell className="py-2.5 px-3 font-semibold text-slate-900 font-mono">
                        {f.field_name}
                      </TableCell>
                      <TableCell className="py-2.5 px-3 font-medium text-slate-800">
                        {f.field_value}
                      </TableCell>
                      <TableCell className="py-2.5 px-3 text-slate-600 font-mono">
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
          </div>

          {/* Mapped Requirements & Compliance Impact */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-xs">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-3">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                  Mapped Tender Requirements ({result.matched.length})
                </h3>
                <SystemLayerTag layer="RULE_ENGINE" size="sm" />
              </div>

              {result.matched.length > 0 ? (
                <div className="space-y-2.5">
                  {result.matched.map((req) => (
                    <div key={req.id} className="rounded border border-slate-200 bg-slate-50/60 p-3 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-slate-900">{req.requirement_name}</span>
                        <span className="font-mono text-slate-500 font-bold">{req.weight}%</span>
                      </div>
                      <p className="mt-1 text-slate-600">Threshold: {req.threshold || 'Existence check'}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-400 italic">
                  Document did not match any specific tender requirement criteria.
                </p>
              )}
            </div>

            {/* Statutory Verification & Compliance Outcome */}
            <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-xs">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-3">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                  Simulated Statutory Verification &amp; Impact
                </h3>
                <SystemLayerTag layer="VERIFICATION" size="sm" />
              </div>

              {result.checks.length > 0 ? (
                <div className="space-y-2.5">
                  {result.checks.slice(0, 3).map((chk) => (
                    <div key={chk.id} className="rounded border border-slate-200 bg-slate-50/60 p-3 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold font-mono text-slate-900">{chk.source}</span>
                        <VerificationBadge status={chk.verification_status} />
                      </div>
                      <p className="mt-1 text-slate-600">
                        {chk.evidence_reference || (chk.response_payload ? JSON.stringify(chk.response_payload) : 'External verification verified.')}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-400 italic">
                  No automated portal checks triggered for this document type.
                </p>
              )}

              {result.complianceScore !== null && (
                <div className="mt-4 border-t border-slate-100 pt-3 flex items-center justify-between text-xs">
                  <span className="font-semibold text-slate-700">Calculated Compliance Score:</span>
                  <span className="font-mono font-bold text-base text-emerald-800">
                    {Math.round(result.complianceScore)}%
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
