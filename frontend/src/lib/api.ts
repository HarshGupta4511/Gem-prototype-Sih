import axios, { AxiosError } from 'axios';
import type {
  AuditLog,
  AuditVerifyResult,
  AuthResponse,
  BidDetail,
  BidSubmission,
  BidSummary,
  CaptchaChallenge,
  Clarification,
  ComparisonData,
  ComplianceResult,
  ConsistencyResult,
  ConsistencyRunResult,
  CreateBidRequest,
  CreateTenderRequest,
  DashboardData,
  Document,
  ExtractedField,
  IntegrityAnalysisResult,
  IntegrityFinding,
  IntegrityOverview,
  LoginRequest,
  OfficerDecisionRequest,
  OverrideRecord,
  OverrideRequest,
  ProviderStatus,
  RecommendationResult,
  ReportObservation,
  ReportStatus,
  ReportTimelineEvent,
  RequirementDraft,
  RiskAssessment,
  SuggestRequirementsRequest,
  SuggestedRequirement,
  Tender,
  TenderDetail,
  TenderListItem,
  TenderRequirement,
  User,
  VerificationCheck,
  VerificationReportData,
} from '../types';

const API_URL = import.meta.env.VITE_API_URL ?? '/api';
const TOKEN_KEY = 'bidverify_token';

export const api = axios.create({
  baseURL: API_URL,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err: AxiosError<{ detail?: string }>) => {
    if (err.response?.status === 401 && !window.location.pathname.startsWith('/login')) {
      localStorage.removeItem(TOKEN_KEY);
      window.location.href = '/login';
    }
    return Promise.reject(err);
  },
);

export function getErrorStatus(err: unknown): number | null {
  if (axios.isAxiosError(err)) return err.response?.status ?? null;
  return null;
}

export function getErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const d = (err as AxiosError<{ detail?: unknown }>).response?.data?.detail;
    if (typeof d === 'string') return d;
    if (d) return JSON.stringify(d);
    return err.message;
  }
  return err instanceof Error ? err.message : 'Unexpected error';
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export function documentFileUrl(id: number): string {
  return `${API_URL}/documents/${id}/file`;
}

// ------------------------------------------------------------------ auth
export const authApi = {
  login: (body: LoginRequest) =>
    api.post<AuthResponse>('/auth/login', body).then((r) => r.data),
  captcha: () => api.get<CaptchaChallenge>('/auth/captcha').then((r) => r.data),
  demo: () => api.post<AuthResponse>('/auth/demo', {}).then((r) => r.data),
  me: () => api.get<User>('/auth/me').then((r) => r.data),
};

// -------------------------------------------------------------- dashboard
export const dashboardApi = {
  get: () => api.get<DashboardData>('/dashboard').then((r) => r.data),
  providers: () => api.get<ProviderStatus>('/dashboard/providers').then((r) => r.data),
};

// ---------------------------------------------------------------- tenders
export const tendersApi = {
  list: () => api.get<TenderListItem[]>('/tenders').then((r) => r.data),
  get: (id: number) => api.get<TenderDetail>(`/tenders/${id}`).then((r) => r.data),
  create: (body: CreateTenderRequest) => api.post<Tender>('/tenders', body).then((r) => r.data),
  /** Delete a tender and every bid/derived record under it. Procurement Officer only. */
  delete: (id: number) => api.delete(`/tenders/${id}`).then((r) => r.data),
  analyzeDraft: (tender_text: string) =>
    api.post<{ requirements: RequirementDraft[] }>('/tenders/analyze-draft', { tender_text }).then((r) => r.data),
  /** AI-suggested requirements (advisory) — officer reviews before creation. */
  suggestRequirements: (payload: SuggestRequirementsRequest) =>
    api
      .post<{ requirements: SuggestedRequirement[]; provider: string }>(
        '/tenders/suggest-requirements',
        payload,
      )
      .then((r) => r.data),
  saveRequirements: (id: number, requirements: Partial<TenderRequirement>[]) =>
    api.post(`/tenders/${id}/requirements`, { requirements }).then((r) => r.data),
  analyze: (id: number, tender_text: string) =>
    api.post<{ requirements: Partial<TenderRequirement>[] }>(`/tenders/${id}/analyze`, { tender_text }).then((r) => r.data),
  comparison: (id: number) => api.get<ComparisonData>(`/tenders/${id}/comparison`).then((r) => r.data),
};

// ------------------------------------------------------------------- bids
export const bidsApi = {
  list: (tender_id?: number) =>
    api.get<BidSummary[]>('/bids', { params: tender_id ? { tender_id } : {} }).then((r) => r.data),
  create: (body: CreateBidRequest) => api.post('/bids', body).then((r) => r.data),
  get: (bid_id: number) => api.get<BidDetail>(`/bids/${bid_id}`).then((r) => r.data),
  /** Attach a demo bidder's fictional evidence dossier via the real backend pipeline. */
  seedDemoEvidence: (
    bid_id: number,
    profile_key: string,
    scenario_id?: string,
    seed?: number,
  ) =>
    api.post(`/bids/${bid_id}/seed-demo-evidence`, {
      profile_key,
      scenario_id: scenario_id ?? null,
      seed: seed ?? null,
    }).then((r) => r.data),
  /** Delete a bid and all its derived data. Procurement Officer only. */
  delete: (bid_id: number) => api.delete(`/bids/${bid_id}`).then((r) => r.data),
  /** Upload or replace a bidder's display-only logo (officer only; jpg/jpeg/png/webp ≤ 2MB, normalized to PNG). */
  uploadBidderLogo: (bidder_id: number, file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return api
      .post<{ bidder_id: number; logo_url: string; size_bytes: number }>(
        `/bidders/${bidder_id}/logo`,
        fd,
      )
      .then((r) => r.data);
  },
  /** Remove a bidder's logo (idempotent). */
  deleteBidderLogo: (bidder_id: number) =>
    api.delete(`/bidders/${bidder_id}/logo`).then((r) => r.data),
  /** Fetch a bidder's logo as a blob (the endpoint is auth-protected, so <img> can't hit it directly). */
  getBidderLogoBlob: (bidder_id: number) =>
    api.get(`/bidders/${bidder_id}/logo`, { responseType: 'blob' }).then((r) => r.data as Blob),
};

/** Public URL form of a bidder's logo (reference only — use getBidderLogoBlob for rendering). */
export const bidderLogoUrl = (bidder_id: number) => `${API_BASE_URL}/bidders/${bidder_id}/logo`;

// --------------------------------------------------------------- documents
export const documentsApi = {
  list: (bid_id?: number) =>
    (bid_id
      ? api.get<Document[]>(`/bids/${bid_id}/documents`)
      : api.get<Document[]>('/documents')
    ).then((r) => r.data),
  upload: (bid_id: number, file: File, onProgress?: (pct: number) => void) => {
    const fd = new FormData();
    fd.append('bid_id', String(bid_id));
    // No document_type — the pipeline auto-detects it from the content.
    fd.append('file', file);
    return api
      .post<Document>('/documents/upload', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => {
          if (e.total && onProgress) onProgress(Math.round((e.loaded / e.total) * 100));
        },
      })
      .then((r) => r.data);
  },
  process: (id: number) =>
    api.post<{ document: Document; extracted_fields: ExtractedField[]; classification: string }>(`/documents/${id}/process`).then((r) => r.data),
  /** Semantic extracted-information view for a bid: shared identity
   * fields consolidated across documents, document-specific fields kept
   * separate, genuine cross-document conflicts flagged. */
  semanticView: (bid_id: number) =>
    api
      .get<{
        bid_id: number;
        entities: {
          field_name: string;
          display_label: string;
          scope: 'shared' | 'document';
          document_type: string | null;
          values: {
            normalized_value: string;
            raw_value: string;
            method: string | null;
            confidence: number | null;
            page: number | null;
            sources: { document_id: number; document_type: string | null; filename: string | null }[];
          }[];
          has_conflict: boolean;
          is_empty: boolean;
          source_count: number;
        }[];
      }>(`/documents/semantic-view`, { params: { bid_id } })
      .then((r) => r.data),
  /** Bidder-registration preview: extract details from a PDF without
   * creating any Document row. Returns the same pipeline output shape
   * as process(), plus filename/status. */
  registrationPreview: (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return api
      .post<{
        status: string;
        filename: string;
        document_type: string | null;
        classification_confidence: number | null;
        type_detected?: boolean;
        pages: number;
        ocr_used: boolean;
        provider?: string;
        extraction_warning?: string;
        error?: string;
        extracted_fields: ExtractedField[];
      }>('/documents/registration-preview', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data);
  },
  get: (id: number) =>
    api.get<{ document: Document; extracted_fields: ExtractedField[] }>(`/documents/${id}`).then((r) => r.data),
  correctType: (id: number, document_type: string) =>
    api.patch<Document>(`/documents/${id}`, { document_type }).then((r) => r.data),
};

// ------------------------------------------------------------ verification
export interface VerificationAdapterInfo {
  source: string;
  display_name: string;
  mode: string;
  is_mock: boolean;
}
export const verificationApi = {
  run: (bid_id: number) =>
    api.post<{ checks: VerificationCheck[] }>('/verification/run', { bid_id }).then((r) => r.data),
  list: (bid_id: number) => api.get<{ checks: VerificationCheck[] }>(`/verification/${bid_id}`).then((r) => r.data),
  all: () => api.get<VerificationCheck[]>('/verification').then((r) => r.data),
  /** Read-only inventory of the verification adapters configured in this build. */
  adapters: () => api.get<VerificationAdapterInfo[]>('/verification/adapters').then((r) => r.data),
};

// ----------------------------------------------------- compliance & risk
export const complianceApi = {
  evaluate: (bid_id: number) =>
    api
      .post<{ results: ComplianceResult[]; compliance_score: number; risk: RiskAssessment }>('/compliance/evaluate', { bid_id })
      .then((r) => r.data),
  get: (bid_id: number) =>
    api.get<{ results: ComplianceResult[]; compliance_score: number; evaluated_at: string }>(`/compliance/${bid_id}`).then((r) => r.data),
  recent: () => api.get<ComplianceResult[]>('/compliance').then((r) => r.data),
};

export const riskApi = {
  get: (bid_id: number) => api.get<RiskAssessment>(`/risk/${bid_id}`).then((r) => r.data),
  all: () => api.get<RiskAssessment[]>('/risk').then((r) => r.data),
};

// --------------------------------------------------------- recommendation
export const recommendationApi = {
  generate: (bid_id: number) =>
    api.post<RecommendationResult>(`/recommendation/${bid_id}`).then((r) => r.data),
};

// ----------------------------------------------------------------- officer
export const officerApi = {
  decision: (body: OfficerDecisionRequest) =>
    api.post<{ bid: BidSubmission }>('/officer/decision', body).then((r) => r.data),
  override: (body: OverrideRequest) =>
    api.post<{ override: OverrideRecord }>('/officer/override', body).then((r) => r.data),
  clarification: (body: { bid_id: number; subject: string; body: string }) =>
    api.post<Clarification>('/officer/clarification', body).then((r) => r.data),
  sendClarification: (id: number) =>
    api.post<Clarification>(`/officer/clarification/${id}/send`).then((r) => r.data),
  clarifications: (bid_id?: number) =>
    api.get<Clarification[]>('/officer/clarifications', { params: bid_id ? { bid_id } : {} }).then((r) => r.data),
};

// ------------------------------------------------------------------- audit
export const auditApi = {
  list: (params?: { entity_type?: string; entity_id?: string; limit?: number }) =>
    api.get<AuditLog[]>('/audit', { params }).then((r) => r.data),
  byTender: (tenderId: number, limit = 200) =>
    api.get<AuditLog[]>(`/audit/by-tender/${tenderId}`, { params: { limit } }).then((r) => r.data),
  verify: () => api.post<AuditVerifyResult>('/audit/verify').then((r) => r.data),
};

// ------------------------------------------------------- verification summaries
// Officer-owned: the Procurement Officer generates the verification
// summary directly. There is no report handoff (no send/receive/acknowledge).
export const summariesApi = {
  get: (bidId: number) =>
    api.get<VerificationReportData>(`/verification-summaries/bids/${bidId}`).then((r) => r.data),
  lifecycle: (bidId: number) =>
    api.get<{ status: ReportStatus; observations: ReportObservation[]; timeline: ReportTimelineEvent[] }>(
      `/verification-summaries/bids/${bidId}/lifecycle`
    ).then((r) => r.data),
  addObservation: (bidId: number, observation: string) =>
    api.post(`/verification-summaries/bids/${bidId}/observations`, { observation }).then((r) => r.data),
  generate: (bidId: number) =>
    api.post<VerificationReportData>(`/verification-summaries/bids/${bidId}/generate`).then((r) => r.data),
  regenerate: (bidId: number) =>
    api.post<VerificationReportData>(`/verification-summaries/bids/${bidId}/regenerate`).then((r) => r.data),
};

// ------------------------------------------------------------------- seed
export const seedApi = {
  run: () => api.post<{ tenders: number; bidders: number; documents: number }>('/seed').then((r) => r.data),
};

export const API_BASE_URL = API_URL;

// --------------------------------------------------------------- integrity
export const integrityApi = {
  analyze: () => api.post('/integrity/analyze', {}).then((r) => r.data as IntegrityAnalysisResult),
  dedupe: () => api.post('/integrity/dedupe', {}).then((r) => r.data as { removed_duplicates: number; remaining_open: number }),
  cleanupStale: () => api.post('/integrity/cleanup-stale', {}).then((r) => r.data as Record<string, number>),
  overview: () => api.get('/integrity/overview').then((r) => r.data as IntegrityOverview),
  findings: (params?: {
    status?: string;
    severity?: string;
    signal_type?: string;
    tender_id?: number;
    bid_id?: number;
    include_closed?: boolean;
  }) => api.get('/integrity/findings', { params }).then((r) => r.data as IntegrityFinding[]),
  get: (id: number) => api.get(`/integrity/findings/${id}`).then((r) => r.data as IntegrityFinding),
  officerAction: (id: number, action: string, note?: string) =>
    api
      .post(`/integrity/findings/${id}/actions`, { action, note })
      .then((r) => r.data as IntegrityFinding),
  bidSignals: (bidId: number) =>
    api.get(`/integrity/bid/${bidId}/signals`).then((r) => r.data as IntegrityFinding[]),
  loadDemoDataset: () => api.post('/integrity/demo-dataset').then((r) => r.data),
  resetDemoDataset: () => api.delete('/integrity/demo-dataset').then((r) => r.data),
  demoDatasetStatus: () =>
    api.get('/integrity/demo-dataset/status').then(
      (r) => r.data as { loaded: boolean; tenders: Array<{ id: number; tender_number: string }>; [k: string]: unknown },
    ),
};

// -------------------------------------------------------------- variety demo dataset
export const demoVarietyApi = {
  loadDataset: () => api.post('/demo-variety/dataset').then((r) => r.data),
  resetDataset: () => api.delete('/demo-variety/dataset').then((r) => r.data),
  datasetStatus: () =>
    api.get('/demo-variety/dataset').then(
      (r) => r.data as { loaded: boolean; tenders: Array<{ id: number; tender_number: string }>; [k: string]: unknown },
    ),
};

// -------------------------------------------------------------- consistency
export const consistencyApi = {
  run: (bidId: number) =>
    api.post(`/consistency/bids/${bidId}/run`).then((r) => r.data as ConsistencyRunResult),
  get: (bidId: number) => api.get(`/consistency/bids/${bidId}`).then((r) => r.data as ConsistencyResult),
};
