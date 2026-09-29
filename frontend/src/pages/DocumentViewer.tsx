import * as React from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Copy,
  Download,
  Eye,
  FileCheck2,
  FileSearch,
  FileSpreadsheet,
  FileText,
  Hash,
  Info,
  Layers,
  RefreshCw,
  Scale,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { api, documentsApi, getErrorMessage } from '../lib/api';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../components/ui/toaster';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '../components/ui/table';
import { Select } from '../components/ui/input';
import { Tooltip } from '../components/ui/tooltip';
import { EmptyState, LoadingBlock } from '../components/common/ui-helpers';
import {
  DocStatusBadge,
  DocTypeBadge,
  MethodBadge,
} from '../components/common/badges';
import { formatDateTime, labelize, truncate } from '../lib/utils';
import { SystemLayerTag } from '../components/common/SystemLayerTag';
import type { DocumentType } from '../types';

const DOCUMENT_TYPES: DocumentType[] = [
  'BID_DOSSIER',
  'PAN_CERTIFICATE',
  'GST_CERTIFICATE',
  'GST_RETURN',
  'UDYAM_CERTIFICATE',
  'ITR',
  'TURNOVER_CERTIFICATE',
  'EXPERIENCE_CERTIFICATE',
  'OEM_AUTHORIZATION',
  'EPFO_CERTIFICATE',
  'ESIC_CERTIFICATE',
  'MII_DECLARATION',
  'STARTUP_INDIA_CERTIFICATE',
  'NSIC_CERTIFICATE',
  'DIGILOCKER_DOCUMENT',
  'AUDITED_FINANCIAL_STATEMENT',
  'OTHER',
];

export default function DocumentViewer() {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const openedFromBid = (location.state as { from?: string } | null)?.from === 'bid';
  const docId = id ? Number(id) : NaN;
  const { canVerify, canDecide } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const [newType, setNewType] = React.useState<DocumentType | ''>('');
  const [savingType, setSavingType] = React.useState(false);
  const [reprocessing, setReprocessing] = React.useState(false);
  const [copiedHash, setCopiedHash] = React.useState(false);

  const {
    data,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ['document', docId],
    queryFn: () => documentsApi.get(docId),
    enabled: Number.isFinite(docId),
  });

  const doc = data?.document;
  const fields = data?.extracted_fields ?? [];

  React.useEffect(() => {
    if (doc) setNewType(doc.document_type === 'UNCLASSIFIED' ? '' : doc.document_type);
  }, [doc]);

  // Authenticated file bytes → object URL, revoked on cleanup.
  const { data: fileUrl } = useQuery({
    queryKey: ['document-file', docId],
    queryFn: async () => {
      const r = await api.get(`/documents/${docId}/file`, { responseType: 'blob' });
      return URL.createObjectURL(r.data as Blob);
    },
    enabled: Number.isFinite(docId),
    staleTime: Infinity,
  });

  React.useEffect(() => {
    return () => {
      if (fileUrl) URL.revokeObjectURL(fileUrl);
    };
  }, [fileUrl]);

  const handleCopyHash = (hash: string) => {
    void navigator.clipboard.writeText(hash);
    setCopiedHash(true);
    setTimeout(() => setCopiedHash(false), 2000);
    toast({
      title: 'SHA-256 Copied',
      description: 'Cryptographic digest copied to clipboard for audit verification.',
    });
  };

  const handleSaveType = async () => {
    if (!doc || !newType || newType === doc.document_type) return;
    setSavingType(true);
    try {
      const updated = await documentsApi.correctType(doc.id, newType);
      const oldLabel = doc.document_type === 'UNCLASSIFIED' ? 'Type Not Detected' : labelize(doc.document_type);
      toast({
        title: 'Classification Corrected',
        description: `${oldLabel} → ${labelize(updated.document_type)} (Logged to audit ledger)`,
      });
      queryClient.invalidateQueries({ queryKey: ['document', docId] });
      queryClient.invalidateQueries({ queryKey: ['documents'] });
    } catch (err) {
      toast({ title: 'Classification Update Failed', description: getErrorMessage(err) });
    } finally {
      setSavingType(false);
    }
  };

  const handleReprocess = async () => {
    if (!doc) return;
    setReprocessing(true);
    try {
      const res = await documentsApi.process(doc.id);
      toast({
        title: 'Document Re-processed',
        description: `Classification: ${res.classification === 'UNCLASSIFIED' ? 'Type Not Detected' : labelize(res.classification)} · ${res.extracted_fields.length} entities extracted`,
      });
      queryClient.invalidateQueries({ queryKey: ['document', docId] });
      queryClient.invalidateQueries({ queryKey: ['documents'] });
    } catch (err) {
      toast({ title: 'Re-processing Failed', description: getErrorMessage(err) });
    } finally {
      setReprocessing(false);
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-xs">
          <LoadingBlock />
        </div>
      </div>
    );
  }

  if (isError || !doc) {
    return (
      <div className="space-y-4">
        <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-xs">
          <Link
            to="/app/documents"
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-blue-700 hover:underline mb-4"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> Back to Document Verification Lab
          </Link>
          <EmptyState
            icon={<FileSearch className="h-8 w-8 text-slate-400" />}
            title="Document Record Not Found"
            description={getErrorMessage(error) || 'The requested document record does not exist or access is restricted.'}
          />
        </div>
      </div>
    );
  }

  const isImage = doc.mime_type.startsWith('image/');
  const backTarget = openedFromBid ? `/app/bids/${doc.bid_id}` : '/app/documents';
  const backLabel = openedFromBid ? 'Return to Bidder Evaluation Dossier' : 'Return to Verification Lab';

  return (
    <div className="space-y-5">
      {/* 1. Institutional Document Header Banner */}
      <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-xs">
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <Link
              to={backTarget}
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-blue-800 hover:text-blue-950 transition-colors"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              <span>{backLabel}</span>
            </Link>
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs text-slate-500">DOC ID #{doc.id}</span>
              <SystemLayerTag layer="DOCUMENT_INGESTION" size="sm" />
            </div>
          </div>

          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 border-t border-slate-100 pt-4">
            <div>
              <div className="flex items-center gap-2.5 flex-wrap">
                <h1 className="text-xl font-bold tracking-tight text-slate-900 font-serif">
                  {doc.filename}
                </h1>
                <DocTypeBadge docType={doc.document_type} />
                <DocStatusBadge status={doc.processing_status} />
              </div>
              <p className="mt-1 text-xs text-slate-600 flex items-center gap-3 flex-wrap">
                <span>MIME: <strong className="text-slate-800 font-mono">{doc.mime_type}</strong></span>
                <span>•</span>
                <span>Size: <strong className="text-slate-800">{(doc.file_size / 1024).toFixed(1)} KB</strong></span>
                <span>•</span>
                <span>Pages: <strong className="text-slate-800">{doc.page_count ?? 1}</strong></span>
                <span>•</span>
                <span>Uploaded: <strong className="text-slate-800">{formatDateTime(doc.upload_time)}</strong></span>
              </p>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              {fileUrl && (
                <a href={fileUrl} download={doc.filename}>
                  <Button variant="outline" size="sm" className="h-8 text-xs font-medium">
                    <Download className="mr-1.5 h-3.5 w-3.5 text-slate-500" />
                    Download File
                  </Button>
                </a>
              )}
              {canVerify && (
                <Button
                  variant="outline"
                  size="sm"
                  loading={reprocessing}
                  onClick={handleReprocess}
                  className="h-8 text-xs font-medium border-blue-200 text-blue-900 bg-blue-50/50 hover:bg-blue-100"
                >
                  <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                  Re-process OCR &amp; Rules
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* 2. Main Two-Column Layout */}
      <div className="grid gap-5 lg:grid-cols-12">
        {/* LEFT COLUMN — Document Visual Preview (7 Cols) */}
        <div className="lg:col-span-7 space-y-4">
          <div className="rounded-lg border border-slate-200 bg-white overflow-hidden shadow-xs">
            <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50/80 px-4 py-2.5">
              <div className="flex items-center gap-2">
                <FileText className="h-4 w-4 text-slate-500" />
                <span className="text-xs font-semibold text-slate-800 uppercase tracking-wide">
                  Official Document Preview
                </span>
              </div>
              <span className="text-[11px] font-mono text-slate-500">
                {isImage ? 'Raster Image' : 'PDF Document Stream'}
              </span>
            </div>

            <div className="p-4 bg-slate-100/50">
              {!fileUrl ? (
                <div className="flex h-[68vh] items-center justify-center rounded-md border border-dashed border-slate-300 bg-white text-xs text-slate-500">
                  <span className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-blue-700 border-t-transparent" />
                  Loading authenticated document stream…
                </div>
              ) : isImage ? (
                <div className="flex h-[68vh] items-center justify-center rounded-md border border-slate-200 bg-slate-900/5 p-2 overflow-auto">
                  <img
                    src={fileUrl}
                    alt={doc.filename}
                    className="max-h-full max-w-full rounded object-contain shadow-xs"
                  />
                </div>
              ) : (
                <iframe
                  title={doc.filename}
                  src={fileUrl}
                  className="h-[68vh] w-full rounded border border-slate-200 bg-white shadow-xs"
                />
              )}
            </div>

            <div className="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-4 py-2 text-[11px] text-slate-500">
              <div className="flex items-center gap-1.5">
                <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />
                <span>Original Bidder Submission — Untampered Static Artifact</span>
              </div>
              <span>Page count: {doc.page_count ?? 1}</span>
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN — Cryptographic Metadata & Extracted Data Dictionary (5 Cols) */}
        <div className="lg:col-span-5 space-y-4">
          {/* Integrity & Classification Card */}
          <div className="rounded-lg border border-slate-200 bg-white shadow-xs">
            <div className="border-b border-slate-200 bg-slate-50/80 px-4 py-3">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                  Cryptographic Integrity &amp; Provenance
                </h3>
                <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-800 border border-emerald-200">
                  SHA-256 Anchored
                </span>
              </div>
            </div>

            <div className="p-4 space-y-3.5">
              <div>
                <p className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">
                  SHA-256 Checksum Digest
                </p>
                <div className="mt-1 flex items-center justify-between rounded border border-slate-200 bg-slate-50 p-2 font-mono text-[11px] text-slate-800">
                  <span className="truncate pr-2 select-all">{doc.file_hash}</span>
                  <button
                    type="button"
                    onClick={() => handleCopyHash(doc.file_hash)}
                    className="shrink-0 p-1 text-slate-500 hover:text-slate-800 transition-colors"
                    title="Copy full SHA-256 hash"
                  >
                    {copiedHash ? (
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                    ) : (
                      <Copy className="h-3.5 w-3.5" />
                    )}
                  </button>
                </div>
              </div>

              {doc.error && (
                <div className="rounded-md border border-red-200 bg-red-50 p-3 text-xs text-red-900">
                  <div className="flex items-center gap-1.5 font-bold">
                    <AlertTriangle className="h-4 w-4 text-red-600 shrink-0" />
                    <span>Processing Exception Encountered</span>
                  </div>
                  <p className="mt-1 text-[11.5px] leading-relaxed text-red-800">
                    {doc.error}
                  </p>
                  <p className="mt-1.5 text-[10.5px] font-semibold text-red-700">
                    Per CPSE procurement policy, documents with processing exceptions trigger statutory REVIEW_REQUIRED.
                  </p>
                </div>
              )}

              {/* Classification Correction (Exception Handling) */}
              <div className="border-t border-slate-100 pt-3">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs font-semibold text-slate-800">Classification Status</span>
                  <DocTypeBadge docType={doc.document_type} />
                </div>

                {(canVerify || canDecide) && doc.document_type === 'UNCLASSIFIED' ? (
                  <div className="space-y-2 mt-2 rounded bg-amber-50/70 p-2.5 border border-amber-200 text-xs">
                    <p className="text-[11px] font-medium text-amber-900">
                      The automated classifier could not identify this document. Assign the proper statutory classification:
                    </p>
                    <div className="flex items-center gap-2">
                      <Select
                        value={newType}
                        onChange={(e) => setNewType(e.target.value as DocumentType)}
                        className="h-8 text-xs flex-1"
                        aria-label="Correct document type"
                      >
                        <option value="">Select Document Type…</option>
                        {DOCUMENT_TYPES.map((t) => (
                          <option key={t} value={t}>
                            {labelize(t)}
                          </option>
                        ))}
                      </Select>
                      <Button
                        variant="default"
                        size="sm"
                        loading={savingType}
                        onClick={handleSaveType}
                        disabled={!newType || newType === doc.document_type}
                        className="h-8 text-xs bg-blue-700 hover:bg-blue-800"
                      >
                        Save
                      </Button>
                    </div>
                  </div>
                ) : (
                  <p className="text-[11px] text-slate-500">
                    Deterministic pipeline matched against CPSE requirement taxonomy. Manual override is restricted to unclassified documents.
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* Extracted Fields Table */}
          <div className="rounded-lg border border-slate-200 bg-white shadow-xs">
            <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50/80 px-4 py-3">
              <div>
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                  Extracted Entities &amp; Metadata
                </h3>
                <p className="text-[11px] text-slate-500">
                  {fields.length} structured field{fields.length === 1 ? '' : 's'} extracted from document
                </p>
              </div>
              <SystemLayerTag layer="RULE_ENGINE" size="sm" />
            </div>

            <div className="p-0">
              {fields.length === 0 ? (
                <div className="p-6 text-center text-xs text-slate-500">
                  <FileSearch className="mx-auto h-6 w-6 text-slate-400 mb-2" />
                  <p className="font-semibold text-slate-700">No Entities Extracted</p>
                  <p className="mt-1 text-[11px]">
                    Re-process document to trigger OCR pattern extraction or check document readability.
                  </p>
                </div>
              ) : (
                <div className="overflow-x-auto max-h-[380px] overflow-y-auto">
                  <Table>
                    <TableHeader className="sticky top-0 bg-slate-100 z-10">
                      <TableRow>
                        <TableHead className="text-[11px] font-bold">Field</TableHead>
                        <TableHead className="text-[11px] font-bold">Value</TableHead>
                        <TableHead className="text-[11px] font-bold">Method</TableHead>
                        <TableHead className="text-[11px] font-bold text-center">Pg</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {fields.map((f) => (
                        <TableRow key={f.id} className="hover:bg-slate-50/80">
                          <TableCell className="font-mono text-xs font-medium text-slate-800 whitespace-nowrap">
                            {f.field_name}
                          </TableCell>
                          <TableCell className="max-w-[180px]">
                            <div className="font-mono text-xs text-slate-900 font-semibold truncate" title={f.field_value}>
                              {f.field_value}
                            </div>
                            {f.normalized_value && f.normalized_value !== f.field_value && (
                              <div className="font-mono text-[10px] text-slate-500 truncate" title={`Normalized: ${f.normalized_value}`}>
                                Norm: {f.normalized_value}
                              </div>
                            )}
                          </TableCell>
                          <TableCell>
                            <MethodBadge method={f.extraction_method} />
                          </TableCell>
                          <TableCell className="text-center font-mono text-xs text-slate-600">
                            {f.page_number ?? '1'}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </div>

            <div className="border-t border-slate-200 bg-slate-50 px-4 py-2.5 text-[11px] text-slate-600">
              <span className="font-semibold text-slate-700">Extraction Methodology: </span>
              Heuristic REGEX &amp; OCR extract values, verified against external public registries.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

