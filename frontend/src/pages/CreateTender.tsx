import * as React from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import {
  ArrowLeft,
  ArrowRight,
  Building2,
  Calendar,
  CheckCircle2,
  FileCheck,
  FileText,
  Info,
  Layers,
  ListChecks,
  Loader2,
  Plus,
  RefreshCw,
  Scale,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  Upload,
  UserCheck,
  Users,
  X,
} from 'lucide-react';
import { tendersApi, bidsApi, documentsApi, getErrorMessage, API_BASE_URL } from '../lib/api';
import { formatINR, labelize } from '../lib/utils';
import { useToast } from '../components/ui/toaster';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input, Select, Textarea } from '../components/ui/input';
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '../components/ui/table';
import { SystemLayerTag } from '../components/common/SystemLayerTag';
import {
  defaultTemplate,
  expectedDocTypesFor,
  expectedDocsForRequirements,
  getCatalogue,
  getCatalogueEntry,
  isApplicableTo,
  validateRequirementDraft,
  type CatalogueEntry,
} from '../lib/requirement-catalogue';
import DemoBiddersModal, {
  normalizeBidderName,
  type DemoBidderProfile,
} from '../components/tenders/DemoBiddersModal';
import type {
  CreateTenderRequest,
  RequirementDraft,
  RequirementCategory,
  RuleType,
  AdapterSource,
  TenderType,
  CreateBidRequest,
} from '../types';

interface QueuedBidder {
  clientId: string;
  /** Demo evidence profile key ('apex' | 'vertex' | 'nova' | 'primetech') — set only for modal-loaded demo bidders. */
  demo_profile_key?: string;
  /** Mismatch-focused scenario id (backend/app/seed/demo_scenarios.py). */
  scenario_id?: string;
  /** Fixed seed for reproducible demo datasets. */
  seed?: number;
  legal_name: string;
  trade_name?: string;
  pan?: string;
  gstin?: string;
  udyam?: string;
  cin?: string;
  registered_address?: string;
  contact_name?: string;
  contact_email?: string;
  contact_phone?: string;
}

/** A registration PDF being processed through the extraction pipeline. */
interface RegDoc {
  id: string;
  file: File;
  status: 'processing' | 'done' | 'failed';
  classification?: string;
  error?: string;
}

// Default requirements now come from the authoritative catalogue
// (frontend/src/lib/requirement-catalogue.json) via defaultTemplate().
// Both this wizard and TenderWizard.tsx consume the same source, so they
// can no longer silently produce different rule configurations.


const SAMPLE_DEMO_BIDDERS: Omit<QueuedBidder, 'clientId'>[] = [
  // Preloaded with the 'apex' demo profile key so the modal's Apex entry
  // deduplicates against it (same normalized legal name) AND the publish
  // step attaches the profile's fictional evidence dossier via the backend
  // seed endpoint. Without the key this bidder was registered with
  // Documents: 0 and the modal Apex could never be selected.
  {
    demo_profile_key: 'apex',
    legal_name: 'Apex Flow Systems Pvt. Ltd.',
    trade_name: 'Apex Industrial Solutions',
    pan: 'AAFCA1234E',
    gstin: '27AAFCA1234E1Z5',
    udyam: 'UDYAM-MH-19-0012345',
    cin: 'U28999MH2015PTC123456',
    registered_address: 'Plot 42, MIDC Industrial Area, Bhosari, Pune - 411026',
    contact_name: 'R. Ramanathan, Director',
    contact_email: 'contracts@apexflow-demo.in',
    contact_phone: '+91 98400 10001',
  },
];

export default function CreateTender() {
  const navigate = useNavigate();
  const { toast } = useToast();

  const [currentStep, setCurrentStep] = React.useState(1);
  const [publishing, setPublishing] = React.useState(false);
  const [errorMsg, setErrorMsg] = React.useState<string | null>(null);

  // Step 1 State: Scope & Identification
  const [tenderNumber, setTenderNumber] = React.useState(
    () => `CPCL-2026-${Math.floor(100 + Math.random() * 900)}`
  );
  const [title, setTitle] = React.useState(
    'Procurement of API 610 Centrifugal Hydrocarbon Pumps & Spares'
  );
  const [organization, setOrganization] = React.useState(
    'Chennai Petroleum Corporation Limited (CPCL)'
  );
  const [department, setDepartment] = React.useState(
    'Procurement - Mechanical & Projects'
  );
  const [description, setDescription] = React.useState(
    'Supply, inspection, civil verification, vibration baseline analysis, and commissioning of high-pressure centrifugal pumping systems at CPCL Manali Refinery.'
  );
  const [closingDate, setClosingDate] = React.useState(() => {
    const d = new Date();
    d.setDate(d.getDate() + 30);
    return d.toISOString().slice(0, 10);
  });
  const [estimatedValue, setEstimatedValue] = React.useState<number>(45000000);
  const [tenderType, setTenderType] = React.useState<TenderType>('GOODS');
  const [emdAmount, setEmdAmount] = React.useState<string>('900000');
  const [deliveryPeriod, setDeliveryPeriod] = React.useState('20 Weeks');
  const [placeOfDelivery, setPlaceOfDelivery] = React.useState(
    'CPCL Refinery Complex, Manali, Chennai - 600068'
  );

  // Step 2 State: Requirements
  const [requirements, setRequirements] = React.useState<RequirementDraft[]>(() => defaultTemplate());

  // Step 3 State: Participating Bidders
  const [bidders, setBidders] = React.useState<QueuedBidder[]>(() =>
    SAMPLE_DEMO_BIDDERS.map((b, i) => ({ ...b, clientId: `bidder-${i}-${Date.now()}` }))
  );

  // Bidder registration state (document-based flow)
  const [regDocs, setRegDocs] = React.useState<RegDoc[]>([]);
  const [regDragOver, setRegDragOver] = React.useState(false);
  /** Merged, officer-editable bidder details from the uploaded docs. */
  const [review, setReview] = React.useState({
    legal_name: '',
    trade_name: '',
    pan: '',
    gstin: '',
    udyam: '',
    cin: '',
    registered_address: '',
    contact_name: '',
    contact_email: '',
    contact_phone: '',
  });
  /** Which source document each reviewed field was extracted from. */
  const [reviewSources, setReviewSources] = React.useState<Record<string, string>>({});
  const [regBusy, setRegBusy] = React.useState(false);
  const regFileInput = React.useRef<HTMLInputElement>(null);

  // Step 4 State: Declaration
  const [gfrDeclaration, setGfrDeclaration] = React.useState(false);

  // Demo bidders modal (Stage 3)
  const [demoModalOpen, setDemoModalOpen] = React.useState(false);

  const totalWeight = React.useMemo(
    () => requirements.reduce((acc, r) => acc + (Number(r.weight) || 0), 0),
    [requirements]
  );

  // Stage 2 gate: the officer cannot proceed to Stage 3 unless the total
  // requirement weight is exactly 100%. The backend enforces the same rule
  // (422) at publish time so it cannot be bypassed.
  const isWeightValid = Math.round(totalWeight * 100) / 100 === 100;

  // Stage 4 publish gate: block publication when the configuration is
  // invalid — no requirements, weights not totalling 100%, or a mandatory
  // requirement without a valid rule configuration (checked against the
  // deterministic engine's contract in requirement-catalogue.ts).
  const publishBlockers = React.useMemo(() => {
    const blockers: string[] = [];
    if (requirements.length === 0) {
      blockers.push('Add at least one requirement before publishing.');
    }
    if (!isWeightValid) {
      blockers.push(`Requirement weights must total exactly 100% (currently ${totalWeight}%).`);
    }
    requirements.forEach((r) => {
      for (const p of validateRequirementDraft(r)) blockers.push(p);
    });
    return blockers;
  }, [requirements, isWeightValid, totalWeight]);

  const canPublish = gfrDeclaration && publishBlockers.length === 0;

  // Document-based bidder registration -------------------------------------
  // Upload PDF → existing extraction/classification pipeline → review →
  // register. Nothing is typed manually unless extraction missed a value.

  /** Canonical extracted field → review-detail key. */
  const REG_FIELD_MAP: Record<string, keyof typeof review> = {
    legal_name: 'legal_name',
    trade_name: 'trade_name',
    pan: 'pan',
    gstin: 'gstin',
    udyam_number: 'udyam',
    cin: 'cin',
    address: 'registered_address',
    email: 'contact_email',
    phone: 'contact_phone',
  };

  const mapExtractedToReview = (
    fields: { field_name: string; field_value: string }[],
  ): Partial<typeof review> => {
    const out: Partial<typeof review> = {};
    for (const f of fields) {
      const key = REG_FIELD_MAP[(f.field_name || '').toLowerCase().trim()];
      if (!key) continue;
      const v = (f.field_value || '').trim();
      if (v && !out[key]) out[key] = v;
    }
    return out;
  };

  const runRegPreview = async (regDoc: RegDoc) => {
    try {
      const res = await documentsApi.registrationPreview(regDoc.file);
      if (res.status === 'FAILED') {
        throw new Error(res.error || 'Extraction failed for this document.');
      }
      setRegDocs((prev) =>
        prev.map((d) =>
          d.id === regDoc.id
            ? { ...d, status: 'done', classification: res.document_type || undefined }
            : d,
        ),
      );
      const mapped = mapExtractedToReview(res.extracted_fields || []);
      if (Object.keys(mapped).length > 0) {
        setReview((prev) => {
          const next = { ...prev };
          (Object.keys(mapped) as (keyof typeof review)[]).forEach((k) => {
            if (!next[k] && mapped[k]) next[k] = mapped[k] as string;
          });
          return next;
        });
        setReviewSources((prev) => {
          const next = { ...prev };
          (Object.keys(mapped) as (keyof typeof review)[]).forEach((k) => {
            if (!next[k]) next[k] = regDoc.file.name;
          });
          return next;
        });
      } else {
        toast({
          title: 'No bidder details found',
          description: `${regDoc.file.name}: the pipeline could not extract registration details. Enter them manually below.`,
        });
      }
      if (res.extraction_warning) {
        toast({ title: 'Partial extraction', description: res.extraction_warning });
      }
    } catch (err) {
      const msg = getErrorMessage(err);
      setRegDocs((prev) =>
        prev.map((d) => (d.id === regDoc.id ? { ...d, status: 'failed', error: msg } : d)),
      );
      toast({
        title: 'Extraction failed',
        description: `${regDoc.file.name}: ${msg} You can still enter the details manually below.`,
      });
    }
  };

  const handleRegFiles = (files: FileList | File[] | null) => {
    if (!files) return;
    const pdfs = Array.from(files).filter((f) => /\.pdf$/i.test(f.name));
    const rejected = Array.from(files).length - pdfs.length;
    if (rejected > 0) {
      toast({
        title: 'Only PDF supported',
        description: `${rejected} file(s) skipped — bidder registration accepts PDF documents only.`,
      });
    }
    if (pdfs.length === 0) return;
    const fresh: RegDoc[] = pdfs.map((file) => ({
      id: `reg-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      file,
      status: 'processing' as const,
    }));
    setRegDocs((prev) => [...prev, ...fresh]);
    fresh.forEach((d) => void runRegPreview(d));
  };

  const handleRemoveRegDoc = (id: string) => {
    setRegDocs((prev) => prev.filter((d) => d.id !== id));
  };

  const handleClearRegistration = () => {
    setRegDocs([]);
    setReview({
      legal_name: '',
      trade_name: '',
      pan: '',
      gstin: '',
      udyam: '',
      cin: '',
      registered_address: '',
      contact_name: '',
      contact_email: '',
      contact_phone: '',
    });
    setReviewSources({});
  };

  const handleRegisterBidder = () => {
    if (!review.legal_name.trim()) {
      toast({
        title: 'Validation Notice',
        description: 'Legal Business Name is required — upload a registration document or type it in the review section.',
      });
      return;
    }
    const t = (s: string) => s.trim();
    const upper = (s: string) => s.trim().toUpperCase();
    const newEntry: QueuedBidder = {
      clientId: `bidder-${Date.now()}`,
      legal_name: t(review.legal_name),
      trade_name: t(review.trade_name) || undefined,
      pan: upper(review.pan) || undefined,
      gstin: upper(review.gstin) || undefined,
      udyam: t(review.udyam) || undefined,
      cin: upper(review.cin) || undefined,
      registered_address: t(review.registered_address) || undefined,
      contact_name: t(review.contact_name) || undefined,
      contact_email: t(review.contact_email) || undefined,
      contact_phone: t(review.contact_phone) || undefined,
    };
    setBidders((prev) => [...prev, newEntry]);
    handleClearRegistration();
    toast({
      title: 'Bidder Added',
      description: `${newEntry.legal_name} added to tender participant queue.`,
    });
  };

  const handleRemoveBidder = (clientId: string) => {
    setBidders((prev) => prev.filter((b) => b.clientId !== clientId));
  };

  const handleLoadSampleBidders = () => {
    setDemoModalOpen(true);
  };

  /** Appends modal-selected demo bidders to the existing queue via the same
   *  QueuedBidder shape as manual registration. Skips duplicates by legal name.
   *  The demo profile key is carried through so publish-time can attach the
   *  profile's fictional evidence dossier via the backend seed endpoint. */
  const handleLoadSelectedDemoBidders = (
    selected: DemoBidderProfile[],
    scenarioId: string,
    seed?: number,
  ) => {
    const existing = new Set(bidders.map((b) => normalizeBidderName(b.legal_name)));
    const fresh: QueuedBidder[] = [];
    for (const profile of selected) {
      if (existing.has(normalizeBidderName(profile.legal_name))) continue;
      existing.add(normalizeBidderName(profile.legal_name));
      const { scenario, scenario_tone, scenario_description, profile_key, ...registration } = profile;
      fresh.push({ ...registration, demo_profile_key: profile_key, scenario_id: scenarioId, seed, clientId: `demo-${Date.now()}-${fresh.length}` });
    }
    if (fresh.length === 0) {
      toast({
        title: 'Demo bidders already loaded.',
        description: 'The selected demo bidders are already in the tender queue.',
      });
      return;
    }
    setBidders((prev) => [...prev, ...fresh]);
    toast({
      title: 'Demo Bidders Loaded',
      description: `${fresh.length} fictional demo bidder(s) added to the tender queue.`,
    });
  };

  // Requirement row editing
  const updateRequirement = (index: number, patch: Partial<RequirementDraft>) => {
    setRequirements((prev) => {
      const copy = [...prev];
      copy[index] = { ...copy[index], ...patch };
      return copy;
    });
  };

  const removeRequirement = (index: number) => {
    setRequirements((prev) => prev.filter((_, i) => i !== index));
  };

  const addManualRequirement = () => {
    setRequirements((prev) => [
      ...prev,
      {
        requirement_name: '',
        category: 'TECHNICAL',
        description: '',
        mandatory: true,
        rule_type: 'CUSTOM_RULE',
        rule_config: {},
        threshold: '',
        verification_source: null,
        weight: 5,
      },
    ]);
  };

  // Final Publish Handler
  const handlePublishTender = async () => {
    if (!tenderNumber.trim() || !title.trim() || !description.trim()) {
      setErrorMsg('Please complete mandatory tender specification fields.');
      return;
    }
    if (!gfrDeclaration) {
      setErrorMsg('Confirmation of the statutory procurement declaration is mandatory.');
      return;
    }
    if (publishBlockers.length > 0) {
      setErrorMsg(`Cannot publish: ${publishBlockers[0]}`);
      return;
    }
    setPublishing(true);
    setErrorMsg(null);

    try {
      // 1. Create Tender
      const req: CreateTenderRequest = {
        tender_number: tenderNumber.trim(),
        title: title.trim(),
        organization: organization.trim(),
        department: department.trim(),
        description: description.trim(),
        closing_date: closingDate,
        estimated_value_inr: Number(estimatedValue),
        tender_type: tenderType,
        emd_amount_inr: emdAmount ? Number(emdAmount) : undefined,
        delivery_period: deliveryPeriod,
        place_of_delivery: placeOfDelivery,
        requirements: requirements.map((r) => ({
          requirement_name: r.requirement_name.trim(),
          category: r.category,
          description: r.description,
          mandatory: r.mandatory,
          rule_type: r.rule_type,
          rule_config: r.rule_config || {},
          threshold: r.threshold?.trim() || null,
          expected_value: r.expected_value,
          verification_source: r.verification_source,
          // Preserve an officer-set 0 explicitly — the old `|| 5` coercion
          // silently rewrote it.
          weight: Number.isFinite(Number(r.weight)) ? Number(r.weight) : 5,
          policy_reference: r.policy_reference,
        })),
      };

      const createdTender = await tendersApi.create(req);
      const tenderId = createdTender.id;

      // 2. Register Queued Bidders for this Tender
      let registeredBiddersCount = 0;
      let demoEvidenceCount = 0;
      const demoEvidenceErrors: string[] = [];
      for (const b of bidders) {
        try {
          const bidPayload: CreateBidRequest = {
            tender_id: tenderId,
            legal_name: b.legal_name,
            trade_name: b.trade_name,
            pan: b.pan,
            gstin: b.gstin,
            udyam: b.udyam,
            cin: b.cin,
            registered_address: b.registered_address,
            contact_name: b.contact_name,
            contact_email: b.contact_email,
            contact_phone: b.contact_phone,
          };
          const created = await bidsApi.create(bidPayload);
          registeredBiddersCount++;
          // 2a. For modal-loaded demo bidders, attach the profile's fictional
          // evidence dossier through the real backend pipeline (documents ->
          // extraction; the officer runs verification/compliance from Bid
          // Detail). Failures are reported with the real reason — never
          // silently swallowed — and the evidence can be attached later from
          // Bid Detail → Documents → "Attach Demo Evidence".
          const bidId = created?.bid?.id;
          if (b.demo_profile_key && bidId) {
            try {
              await bidsApi.seedDemoEvidence(bidId, b.demo_profile_key, b.scenario_id, b.seed);
              demoEvidenceCount++;
            } catch (seedErr) {
              const reason = getErrorMessage(seedErr);
              demoEvidenceErrors.push(`${b.legal_name}: ${reason}`);
              console.warn(`Could not seed demo evidence for ${b.legal_name}:`, seedErr);
            }
          }
        } catch (bidErr) {
          console.warn(`Could not register bidder ${b.legal_name}:`, bidErr);
        }
      }

      const evidenceFailed = demoEvidenceErrors.length;
      const networkHint = demoEvidenceErrors.some((e) => e.includes('Network Error'))
        ? ` The backend did not respond at ${API_BASE_URL} — check that the backend service is running and rebuilt.`
        : '';
      toast({
        title: 'Tender Package Published',
        description: `Tender #${createdTender.tender_number} published with ${registeredBiddersCount} participating bidder(s).` +
          (demoEvidenceCount > 0 ? ` Demo evidence attached for ${demoEvidenceCount} demo bidder(s).` : '') +
          (evidenceFailed > 0
            ? ` Demo evidence FAILED for ${evidenceFailed} bidder(s) — bids were registered without evidence. Reason: ${demoEvidenceErrors[0]}.${networkHint} You can attach it later from the bid's Documents tab.`
            : ''),
      });

      // Navigate directly to the new tender dossier command center
      navigate(`/app/tenders/${tenderId}`);
    } catch (err: unknown) {
      setErrorMsg(getErrorMessage(err));
    } finally {
      setPublishing(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* 1. Institutional Header Banner */}
      <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-xs dark:border-slate-800 dark:bg-slate-900">
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <Link
              to="/app/tenders"
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-blue-800 hover:text-blue-950 transition-colors dark:text-blue-300 dark:hover:text-blue-100"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              <span>Return to Procurement Directory</span>
            </Link>
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs text-slate-500 font-semibold dark:text-slate-400">TENDER CREATION WORKSPACE</span>
              <SystemLayerTag layer="RULE_ENGINE" size="sm" />
            </div>
          </div>

          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 border-t border-slate-100 pt-4 dark:border-slate-800">
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-slate-900 font-serif dark:text-slate-100">
                Create Tender Package &amp; Register Bidders
              </h1>
              <p className="mt-0.5 text-xs text-slate-600 dark:text-slate-400">
                Define technical specifications, configure qualification criteria, and register participating enterprise bidders for automated compliance analysis.
              </p>
            </div>

            <div className="flex items-center gap-2">
              <span className="rounded bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-900 border border-blue-200 dark:bg-blue-950/60 dark:text-blue-200 dark:border-blue-800">
                GFR 2017 &amp; GeM Protocol Compliant
              </span>
            </div>
          </div>
        </div>

        {/* 2. Four-Stage Process Stepper */}
        <div className="mt-6 border-t border-slate-100 pt-5 dark:border-slate-800">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { n: 1, title: 'Tender Specifications', desc: 'Scope, dates & financials', icon: FileText },
              { n: 2, title: 'Qualification Rules', desc: 'Statutory criteria & weights', icon: ListChecks },
              { n: 3, title: 'Participating Bidders', desc: 'Vendor registry & IDs', icon: Users },
              { n: 4, title: 'Review & Publication', desc: 'Statutory seal & publish', icon: ShieldCheck },
            ].map((st) => {
              const isActive = currentStep === st.n;
              const isPast = currentStep > st.n;
              const Icon = st.icon;
              return (
                <button
                  key={st.n}
                  type="button"
                  onClick={() => setCurrentStep(st.n)}
                  className={`flex items-start gap-3 p-3 rounded-lg border text-left transition-all ${
                    isActive
                      ? 'border-blue-700 bg-blue-50/60 shadow-2xs dark:bg-blue-950/60'
                      : isPast
                      ? 'border-emerald-200 bg-emerald-50/30 dark:border-emerald-900 dark:bg-emerald-950/30'
                      : 'border-slate-200 bg-slate-50/50 hover:bg-slate-100/60 dark:border-slate-800 dark:bg-slate-800/50 dark:hover:bg-slate-800/60'
                  }`}
                >
                  <div
                    className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md font-mono text-xs font-bold ${
                      isActive
                        ? 'bg-blue-800 text-white'
                        : isPast
                        ? 'bg-emerald-600 text-white'
                        : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'
                    }`}
                  >
                    {isPast ? <CheckCircle2 className="h-4 w-4" /> : `0${st.n}`}
                  </div>
                  <div className="min-w-0">
                    <p className={`text-xs font-bold leading-tight ${isActive ? 'text-blue-950 dark:text-blue-100' : 'text-slate-900 dark:text-slate-100'}`}>
                      {st.title}
                    </p>
                    <p className="truncate text-[11px] text-slate-500 mt-0.5 dark:text-slate-400">{st.desc}</p>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {errorMsg && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-xs text-red-900 flex items-center gap-2 dark:border-red-900 dark:bg-red-950/60 dark:text-red-200">
          <ShieldAlert className="h-4 w-4 text-red-600 shrink-0 dark:text-red-400" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* 3. STEP CONTENT */}

      {/* STEP 1: SPECIFICATIONS */}
      {currentStep === 1 && (
        <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-xs space-y-6 dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3 dark:border-slate-800">
            <div>
              <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wide dark:text-slate-100">
                Stage 1 — Tender Scope &amp; Procurement Identification
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Establish the administrative credentials, monetary threshold, and timelines for this procurement.
              </p>
            </div>
            <span className="font-mono text-xs font-semibold text-slate-400 dark:text-slate-500">Step 1 of 4</span>
          </div>

          <div className="grid gap-5 md:grid-cols-2">
            <div>
              <label className="block text-xs font-semibold text-slate-800 mb-1 dark:text-slate-200">
                Tender Reference Number *
              </label>
              <Input
                value={tenderNumber}
                onChange={(e) => setTenderNumber(e.target.value)}
                placeholder="e.g. CPCL-2026-004"
                className="font-mono text-xs uppercase dark:bg-slate-900 dark:border-slate-700 dark:placeholder:text-slate-500 dark:text-slate-100"
              />
              <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">Unique statutory reference code under GeM/CPSE ledger.</p>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-800 mb-1 dark:text-slate-200">
                Procuring Organization *
              </label>
              <Input
                value={organization}
                onChange={(e) => setOrganization(e.target.value)}
                className="text-xs dark:bg-slate-900 dark:border-slate-700 dark:placeholder:text-slate-500 dark:text-slate-100"
              />
            </div>

            <div className="md:col-span-2">
              <label className="block text-xs font-semibold text-slate-800 mb-1 dark:text-slate-200">
                Tender Package Title *
              </label>
              <Input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Brief formal title describing the procurement scope"
                className="text-xs font-medium dark:bg-slate-900 dark:border-slate-700 dark:placeholder:text-slate-500 dark:text-slate-100"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-800 mb-1 dark:text-slate-200">
                Executing Department *
              </label>
              <Input
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
                className="text-xs dark:bg-slate-900 dark:border-slate-700 dark:placeholder:text-slate-500 dark:text-slate-100"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-800 mb-1 dark:text-slate-200">
                Estimated Contract Value (INR) *
              </label>
              <div className="flex items-center gap-2">
                <Input
                  type="number"
                  value={estimatedValue}
                  onChange={(e) => setEstimatedValue(Number(e.target.value))}
                  className="text-xs font-mono dark:bg-slate-900 dark:border-slate-700 dark:placeholder:text-slate-500 dark:text-slate-100"
                />
                <span className="shrink-0 rounded bg-slate-100 px-2.5 py-1 text-xs font-mono font-bold text-slate-800 border border-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:border-slate-800">
                  {formatINR(estimatedValue)}
                </span>
              </div>
            </div>

            <div className="md:col-span-2">
              <label className="block text-xs font-semibold text-slate-800 mb-1 dark:text-slate-200">
                Detailed Scope of Work &amp; Technical Specifications *
              </label>
              <Textarea
                rows={4}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Detail technical standards, delivery parameters, ISO/API codes, inspection checkpoints..."
                className="text-xs dark:bg-slate-900 dark:border-slate-700 dark:placeholder:text-slate-500 dark:text-slate-100"
              />
              <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                This scope is analyzed by the deterministic rule engine and AI assistant to synthesize compliance requirements.
              </p>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-800 mb-1 dark:text-slate-200">
                Tender Category
              </label>
              <Select
                value={tenderType}
                onChange={(e) => setTenderType(e.target.value as TenderType)}
                className="text-xs dark:bg-slate-900 dark:border-slate-700 dark:placeholder:text-slate-500 dark:text-slate-100"
              >
                <option value="GOODS">Goods &amp; Equipment Supply</option>
                <option value="SERVICES">Consultancy &amp; Technical Services</option>
                <option value="WORKS">Works Contract &amp; Construction</option>
              </Select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-800 mb-1 dark:text-slate-200">
                Bid Submission Closing Date *
              </label>
              <Input
                type="date"
                value={closingDate}
                onChange={(e) => setClosingDate(e.target.value)}
                className="text-xs font-mono dark:bg-slate-900 dark:border-slate-700 dark:placeholder:text-slate-500 dark:text-slate-100"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-800 mb-1 dark:text-slate-200">
                Earnest Money Deposit (EMD in INR)
              </label>
              <Input
                type="number"
                value={emdAmount}
                onChange={(e) => setEmdAmount(e.target.value)}
                placeholder="e.g. 1000000"
                className="text-xs font-mono dark:bg-slate-900 dark:border-slate-700 dark:placeholder:text-slate-500 dark:text-slate-100"
              />
              <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">Exemptions automatically apply for verified MSME / Startups.</p>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-800 mb-1 dark:text-slate-200">
                Delivery / Contract Duration
              </label>
              <Input
                value={deliveryPeriod}
                onChange={(e) => setDeliveryPeriod(e.target.value)}
                placeholder="e.g. 24 Weeks"
                className="text-xs dark:bg-slate-900 dark:border-slate-700 dark:placeholder:text-slate-500 dark:text-slate-100"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-800 mb-1 dark:text-slate-200">
                Place of Delivery &amp; Inspection
              </label>
              <Input
                value={placeOfDelivery}
                onChange={(e) => setPlaceOfDelivery(e.target.value)}
                className="text-xs dark:bg-slate-900 dark:border-slate-700 dark:placeholder:text-slate-500 dark:text-slate-100"
              />
            </div>
          </div>

          <div className="flex items-center justify-between border-t border-slate-100 pt-4 dark:border-slate-800">
            <span className="text-xs text-slate-500 dark:text-slate-400">All fields marked with * are required under CPSE procurement audit standards.</span>
            <Button
              type="button"
              onClick={() => setCurrentStep(2)}
              className="bg-blue-800 hover:bg-blue-900 text-white text-xs font-medium"
            >
              Continue to Qualification Rules
              <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      )}

      {/* STEP 2: REQUIREMENTS */}
      {currentStep === 2 && (
        <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-xs space-y-6 dark:border-slate-800 dark:bg-slate-900">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-100 pb-3 dark:border-slate-800">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wide dark:text-slate-100">
                  Stage 2 — Bidder Qualification &amp; Compliance Rules
                </h2>
                <SystemLayerTag layer="RULE_ENGINE" size="sm" />
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Configure deterministic evaluation rules. Weights must equal 100% for scored criteria.
              </p>
            </div>

            <div className="flex items-center gap-2">
              <Select
                value=""
                onChange={(e) => {
                  const entry = getCatalogueEntry(e.target.value);
                  if (!entry) return;
                  setRequirements((prev) => [
                    ...prev,
                    {
                      requirement_name: entry.requirement_name,
                      category: entry.category,
                      description: entry.description,
                      mandatory: entry.default_mandatory,
                      rule_type: entry.rule_type,
                      rule_config: { ...entry.rule_config },
                      threshold: entry.threshold,
                      expected_value: entry.expected_value ?? undefined,
                      verification_source: entry.verification_source ?? null,
                      weight: entry.default_weight,
                      policy_reference: entry.policy_reference ?? undefined,
                    },
                  ]);
                  e.target.value = '';
                }}
                className="h-8 text-xs font-medium border-slate-300 text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
                title="Add a requirement from the authoritative catalogue"
              >
                <option value="">Add from catalogue…</option>
                {getCatalogue()
                  .filter((c) => !requirements.some((r) => r.requirement_name === c.requirement_name))
                  .map((c) => (
                    <option key={c.key} value={c.key}>
                      {c.requirement_name} ({c.applicability.toLowerCase()}
                      {isApplicableTo(c, tenderType) ? '' : ' — not for ' + tenderType})
                    </option>
                  ))}
              </Select>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setRequirements(defaultTemplate())}
                title="Replace the requirement list with the catalogue default template (weights total 100%)"
                className="h-8 text-xs font-medium border-slate-300 text-slate-700 dark:border-slate-700 dark:text-slate-200"
              >
                <RefreshCw className="mr-1 h-3.5 w-3.5" />
                Reset to defaults
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={addManualRequirement}
                className="h-8 text-xs font-medium border-slate-300 text-slate-700 dark:border-slate-700 dark:text-slate-200"
              >
                <Plus className="mr-1 h-3.5 w-3.5" />
                Add Custom Rule
              </Button>
            </div>
          </div>

          {/* Weight Counter Bar */}
          <div className="rounded-lg border border-slate-200 bg-slate-50/80 p-3 flex items-center justify-between text-xs dark:border-slate-800 dark:bg-slate-800/60">
            <div className="flex items-center gap-2">
              <Scale className="h-4 w-4 text-slate-600 dark:text-slate-400" />
              <span className="font-semibold text-slate-800 dark:text-slate-200">Total Scored Weight:</span>
              <span
                className={`font-mono font-bold text-sm ${
                  isWeightValid ? 'text-emerald-700 dark:text-emerald-400' : 'text-rose-700 dark:text-rose-400'
                }`}
              >
                {totalWeight}% / 100%
              </span>
            </div>
            {isWeightValid ? (
              <span className="flex items-center gap-1 text-[11px] font-semibold text-emerald-700 dark:text-emerald-400">
                <CheckCircle2 className="h-3.5 w-3.5" /> Perfectly Balanced
              </span>
            ) : (
              <span className="text-[11px] font-semibold text-rose-700 dark:text-rose-400">
                Requirement weights must total exactly 100%.
              </span>
            )}
          </div>

          {/* Requirements Table */}
          <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
            <Table>
              <TableHeader>
                <tr className="border-b border-slate-200 bg-slate-50 text-[10.5px] font-bold text-slate-600 uppercase tracking-wider dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
                  <TableHead className="w-12 text-center">#</TableHead>
                  <TableHead className="min-w-[260px]">Requirement Name &amp; Description</TableHead>
                  <TableHead className="w-36">Category</TableHead>
                  <TableHead className="w-36">Threshold / Expected</TableHead>
                  <TableHead className="w-24 text-center">Mandatory</TableHead>
                  <TableHead className="w-24 text-center">Weight %</TableHead>
                  <TableHead className="w-16 text-right">Action</TableHead>
                </tr>
              </TableHeader>
              <TableBody>
                {requirements.map((r, idx) => (
                  <TableRow key={idx} className="hover:bg-slate-50/50 text-xs dark:hover:bg-slate-800/50">
                    <TableCell className="text-center font-mono text-slate-400 font-bold dark:text-slate-500">
                      {idx + 1}
                    </TableCell>
                    <TableCell className="space-y-1">
                      <Input
                        value={r.requirement_name}
                        onChange={(e) => updateRequirement(idx, { requirement_name: e.target.value })}
                        placeholder="Requirement title"
                        className="text-xs font-semibold h-8 dark:bg-slate-900 dark:border-slate-700 dark:placeholder:text-slate-500 dark:text-slate-100"
                      />
                      <Input
                        value={r.description || ''}
                        onChange={(e) => updateRequirement(idx, { description: e.target.value })}
                        placeholder="Detailed verification criteria"
                        className="text-[11px] text-slate-500 h-7 dark:text-slate-400 dark:bg-slate-900 dark:border-slate-700 dark:placeholder:text-slate-500"
                      />
                      {(() => {
                        const entry = getCatalogue().find((c) => c.requirement_name === r.requirement_name);
                        if (!entry) return null;
                        const docs = expectedDocTypesFor(entry);
                        return (
                          <p className="text-[10px] leading-snug text-slate-500 dark:text-slate-400">
                            <span className={`font-bold ${entry.applicability === 'REQUIRED' ? 'text-blue-700 dark:text-blue-400' : entry.applicability === 'CONDITIONAL' ? 'text-amber-700 dark:text-amber-400' : 'text-slate-500 dark:text-slate-400'}`}>
                              {entry.applicability.toLowerCase()}
                            </span>
                            {!isApplicableTo(entry, tenderType) && (
                              <span className="font-semibold text-rose-600 dark:text-rose-400"> · not applicable to {tenderType}</span>
                            )}
                            {docs.length > 0 && <span> · evidence: {docs.join(', ')}</span>}
                            {docs.length === 0 && <span> · portal-verified, no document needed</span>}
                          </p>
                        );
                      })()}
                    </TableCell>
                    <TableCell>
                      <Select
                        value={r.category}
                        onChange={(e) => updateRequirement(idx, { category: e.target.value as RequirementCategory })}
                        className="text-xs h-8 dark:bg-slate-900 dark:border-slate-700 dark:placeholder:text-slate-500 dark:text-slate-100"
                      >
                        <option value="STATUTORY">Statutory</option>
                        <option value="FINANCIAL">Financial</option>
                        <option value="EXPERIENCE">Experience</option>
                        <option value="TECHNICAL">Technical</option>
                        <option value="REGISTRATION">Registration</option>
                        <option value="LOCAL_CONTENT">Local Content</option>
                      </Select>
                    </TableCell>
                    <TableCell>
                      <Input
                        value={r.threshold || ''}
                        onChange={(e) => updateRequirement(idx, { threshold: e.target.value })}
                        placeholder="e.g. ₹1.5 Cr / 50%"
                        className="text-xs font-mono h-8 dark:bg-slate-900 dark:border-slate-700 dark:placeholder:text-slate-500 dark:text-slate-100"
                      />
                    </TableCell>
                    <TableCell className="text-center">
                      <input
                        type="checkbox"
                        checked={r.mandatory}
                        onChange={(e) => updateRequirement(idx, { mandatory: e.target.checked })}
                        className="h-4 w-4 rounded border-slate-300 text-blue-800 focus:ring-blue-500 dark:border-slate-700 dark:text-blue-300"
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        type="number"
                        value={r.weight}
                        onChange={(e) => updateRequirement(idx, { weight: Number(e.target.value) })}
                        className="text-xs font-mono text-center h-8 dark:bg-slate-900 dark:border-slate-700 dark:placeholder:text-slate-500 dark:text-slate-100"
                        min={0}
                        max={100}
                      />
                    </TableCell>
                    <TableCell className="text-right">
                      <button
                        type="button"
                        onClick={() => removeRequirement(idx)}
                        className="text-slate-400 hover:text-rose-600 p-1 dark:text-slate-500 dark:hover:text-rose-400"
                        title="Delete rule"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <div className="flex items-center justify-between border-t border-slate-100 pt-4 dark:border-slate-800">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setCurrentStep(1)}
              className="text-xs"
            >
              <ArrowLeft className="mr-1.5 h-3.5 w-3.5" /> Back to Specifications
            </Button>
            <Button
              type="button"
              onClick={() => setCurrentStep(3)}
              disabled={!isWeightValid}
              title={isWeightValid ? undefined : 'Requirement weights must total exactly 100%.'}
              className="bg-blue-800 hover:bg-blue-900 text-white text-xs font-medium disabled:cursor-not-allowed disabled:opacity-50"
            >
              Continue to Register Participating Bidders
              <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      )}

      {/* STEP 3: PARTICIPATING BIDDERS REGISTRATION */}
      {currentStep === 3 && (
        <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-xs space-y-6 dark:border-slate-800 dark:bg-slate-900">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-100 pb-3 dark:border-slate-800">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wide dark:text-slate-100">
                  Stage 3 — Register Participating Bidders for this Tender
                </h2>
                <Badge variant="outline" className="text-xs font-mono">
                  {bidders.length} Registered
                </Badge>
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Register participating vendors so the tender dossier immediately includes bidders ready for document ingestion and cross-checking.
              </p>
            </div>

            <div className="flex flex-col items-start sm:items-end gap-1">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleLoadSampleBidders}
                className="h-8 text-xs font-medium border-slate-300 text-slate-800 bg-slate-50 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:bg-slate-900 dark:hover:bg-slate-800"
              >
                <Users className="mr-1.5 h-3.5 w-3.5 text-blue-700 dark:text-blue-400" />
                Load Demo Participating Bidders
              </Button>
              <p className="text-[11px] text-slate-500 dark:text-slate-400">
                Need sample data for a demonstration? Load preconfigured fictional bidders.
              </p>
            </div>
          </div>

          {/* Document-based Bidder Registration */}
          <div className="rounded-lg border border-blue-100 bg-blue-50/30 p-4 space-y-4 dark:border-blue-900 dark:bg-blue-950/30">
            <div className="flex items-center justify-between border-b border-blue-200/60 pb-2 dark:border-blue-900/60">
              <span className="text-xs font-bold text-blue-950 uppercase tracking-wider dark:text-blue-100">
                Upload Bidder Registration Documents
              </span>
              <span className="text-[11px] text-blue-800 dark:text-blue-300">PDF only — AI classification &amp; extraction</span>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 -mt-2">
              Upload PDF documents containing the bidder/company registration details.
            </p>

            {/* Drop zone */}
            <div
              role="button"
              tabIndex={0}
              onClick={() => regFileInput.current?.click()}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') regFileInput.current?.click(); }}
              onDragOver={(e) => { e.preventDefault(); setRegDragOver(true); }}
              onDragLeave={() => setRegDragOver(false)}
              onDrop={(e) => { e.preventDefault(); setRegDragOver(false); handleRegFiles(e.dataTransfer.files); }}
              className={`flex flex-col items-center justify-center gap-1.5 rounded-lg border-2 border-dashed px-4 py-6 text-center cursor-pointer transition-colors ${
                regDragOver
                  ? 'border-blue-500 bg-blue-50 dark:bg-blue-950/60'
                  : 'border-slate-300 dark:border-slate-600 bg-white/60 dark:bg-slate-900/60 hover:border-blue-400 dark:hover:border-blue-500'
              }`}
            >
              <Upload className="h-6 w-6 text-blue-700 dark:text-blue-400" />
              <p className="text-xs font-semibold text-slate-700 dark:text-slate-200">
                Drag &amp; drop registration PDFs here, or click to browse
              </p>
              <p className="text-[11px] text-slate-500 dark:text-slate-400">
                e.g. PAN Card, GST Certificate, Udyam / Incorporation Certificate
              </p>
              <input
                ref={regFileInput}
                type="file"
                accept=".pdf"
                multiple
                className="hidden"
                onChange={(e) => { handleRegFiles(e.target.files); e.target.value = ''; }}
              />
            </div>

            {/* Per-file extraction status */}
            {regDocs.length > 0 && (
              <div className="space-y-1.5">
                {regDocs.map((d) => (
                  <div
                    key={d.id}
                    className="flex items-center gap-2 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-2.5 py-1.5 text-xs"
                  >
                    <FileText className="h-3.5 w-3.5 shrink-0 text-slate-400" />
                    <span className="min-w-0 flex-1 truncate font-medium text-slate-700 dark:text-slate-200" title={d.file.name}>
                      {d.file.name}
                    </span>
                    {d.status === 'processing' && (
                      <span className="inline-flex items-center gap-1 text-blue-700 dark:text-blue-300">
                        <Loader2 className="h-3.5 w-3.5 animate-spin" /> Extracting…
                      </span>
                    )}
                    {d.status === 'done' && (
                      <Badge variant="outline" className="text-[10px]">
                        {d.classification ? `Classified: ${d.classification}` : 'Extracted'}
                      </Badge>
                    )}
                    {d.status === 'failed' && (
                      <span className="text-[11px] text-rose-600 dark:text-rose-400 truncate max-w-xs" title={d.error}>
                        {d.error}
                      </span>
                    )}
                    <button
                      type="button"
                      onClick={() => handleRemoveRegDoc(d.id)}
                      className="p-1 text-slate-400 hover:text-rose-600 dark:hover:text-rose-400"
                      title="Remove document"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Review extracted details */}
            {regDocs.length > 0 && (
              <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-3.5 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-800 uppercase tracking-wider dark:text-slate-200">
                    Review Extracted Details
                  </span>
                  <span className="text-[11px] text-slate-500 dark:text-slate-400">
                    Verify before registration — correct only where needed
                  </span>
                </div>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {(
                    [
                      { key: 'legal_name', label: 'Legal Enterprise / Company Name', required: true, span: true },
                      { key: 'trade_name', label: 'Trade Name / Brand Alias' },
                      { key: 'pan', label: 'PAN', mono: true },
                      { key: 'gstin', label: 'GSTIN', mono: true },
                      { key: 'udyam', label: 'Udyam Registration (MSME)', mono: true },
                      { key: 'cin', label: 'CIN', mono: true },
                      { key: 'registered_address', label: 'Registered Corporate Address', span: true },
                      { key: 'contact_name', label: 'Authorized Contact Person' },
                      { key: 'contact_email', label: 'Official Email Address', type: 'email' },
                      { key: 'contact_phone', label: 'Contact Phone', type: 'tel' },
                    ] as {
                      key: keyof typeof review;
                      label: string;
                      required?: boolean;
                      span?: boolean;
                      mono?: boolean;
                      type?: string;
                    }[]
                  ).map((f) => {
                    const val = review[f.key];
                    const src = reviewSources[f.key];
                    return (
                      <div key={f.key} className={f.span ? 'sm:col-span-2 lg:col-span-2' : ''}>
                        <label className="block text-xs font-semibold text-slate-700 mb-1 dark:text-slate-300">
                          {f.label}{' '}
                          {f.required && <span className="text-rose-600 dark:text-rose-400">*</span>}
                          {!val && (
                            <span className="ml-1 font-normal text-amber-600 dark:text-amber-400">(not extracted)</span>
                          )}
                        </label>
                        <Input
                          type={f.type ?? 'text'}
                          value={val}
                          onChange={(e) =>
                            setReview((prev) => ({ ...prev, [f.key]: e.target.value }))
                          }
                          placeholder={val ? undefined : 'Enter manually'}
                          className={`text-xs bg-white dark:bg-slate-950 dark:border-slate-700 dark:text-slate-100 ${
                            f.mono ? 'font-mono uppercase' : ''
                          } ${!val ? 'border-dashed' : ''}`}
                        />
                        {src && val && (
                          <p className="mt-0.5 text-[10px] text-slate-400 dark:text-slate-500 truncate" title={src}>
                            Extracted from {src}
                          </p>
                        )}
                      </div>
                    );
                  })}
                </div>
                <div className="flex items-center justify-end gap-2 pt-1">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleClearRegistration}
                    className="h-8 text-xs"
                  >
                    Clear
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    onClick={handleRegisterBidder}
                    disabled={regBusy}
                    className="h-8 text-xs bg-blue-800 hover:bg-blue-900 text-white font-medium"
                  >
                    <Plus className="mr-1.5 h-3.5 w-3.5" />
                    Register Bidder
                  </Button>
                </div>
              </div>
            )}
          </div>

          {/* Registered Bidders Table */}
          <div className="space-y-2">
            <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider dark:text-slate-200">
              Bidders Queued for Evaluation ({bidders.length})
            </h3>

            {bidders.length === 0 ? (
              <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-xs text-slate-500 dark:border-slate-700 dark:text-slate-400">
                <Users className="mx-auto h-8 w-8 text-slate-400 mb-2 dark:text-slate-500" />
                <p className="font-semibold text-slate-700 dark:text-slate-200">No Bidders Registered Yet</p>
                <p className="mt-1">Upload registration documents above or click "Load Demo Participating Bidders".</p>
              </div>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
                <Table>
                  <TableHeader>
                    <tr className="border-b border-slate-200 bg-slate-50 text-[10.5px] font-bold text-slate-600 uppercase tracking-wider dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
                      <TableHead>Bidder Enterprise</TableHead>
                      <TableHead>GSTIN / PAN</TableHead>
                      <TableHead>MSME / CIN</TableHead>
                      <TableHead>Contact Representative</TableHead>
                      <TableHead className="text-right">Action</TableHead>
                    </tr>
                  </TableHeader>
                  <TableBody>
                    {bidders.map((b) => (
                      <TableRow key={b.clientId} className="hover:bg-slate-50/50 text-xs dark:hover:bg-slate-800/50">
                        <TableCell>
                          <p className="font-semibold text-slate-900 dark:text-slate-100">{b.legal_name}</p>
                          {b.trade_name && <p className="text-[11px] text-slate-500 dark:text-slate-400">{b.trade_name}</p>}
                        </TableCell>
                        <TableCell className="font-mono text-xs">
                          <div>GST: <span className="font-semibold text-slate-800 dark:text-slate-200">{b.gstin || '—'}</span></div>
                          <div>PAN: <span className="font-semibold text-slate-800 dark:text-slate-200">{b.pan || '—'}</span></div>
                        </TableCell>
                        <TableCell className="font-mono text-xs">
                          <div>UDYAM: <span className="text-slate-800 dark:text-slate-200">{b.udyam || '—'}</span></div>
                          <div>CIN: <span className="text-slate-800 dark:text-slate-200">{b.cin || '—'}</span></div>
                        </TableCell>
                        <TableCell className="text-xs">
                          <p className="font-medium text-slate-800 dark:text-slate-200">{b.contact_name || '—'}</p>
                          <p className="text-[11px] text-slate-500 dark:text-slate-400">{b.contact_email || '—'}</p>
                        </TableCell>
                        <TableCell className="text-right">
                          <button
                            type="button"
                            onClick={() => handleRemoveBidder(b.clientId)}
                            className="p-1 text-slate-400 hover:text-rose-600 dark:text-slate-500 dark:hover:text-rose-400"
                            title="Remove bidder"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </div>

          {/* Expected evidence per bidder (derived from the Stage 2 requirements) */}
          {bidders.length > 0 && (
            <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-4 dark:border-slate-800 dark:bg-slate-900/60">
              <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-600 dark:text-slate-400">
                Expected evidence per bidder
              </h4>
              <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                Derived from the current requirement list. Demo evidence is generated from the same mapping at publish time —
                missing evidence is never auto-marked uploaded or compliant.
              </p>
              <div className="mt-3 space-y-2">
                {bidders.map((b) => {
                  const docs = expectedDocsForRequirements(requirements, b.demo_profile_key);
                  return (
                    <div key={b.clientId} className="flex flex-col sm:flex-row sm:items-start gap-1 sm:gap-3 text-xs">
                      <span className="font-semibold text-slate-800 dark:text-slate-200 sm:w-56 shrink-0">
                        {b.legal_name}
                        {b.demo_profile_key === 'vertex' && (
                          <span className="ml-1.5 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold text-amber-800 dark:bg-amber-950/60 dark:text-amber-400">
                            intentionally missing evidence
                          </span>
                        )}
                      </span>
                      <span className="text-slate-600 dark:text-slate-400">
                        {docs.length > 0 ? docs.join(', ') : '— no evidence documents expected —'}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          <div className="flex items-center justify-between border-t border-slate-100 pt-4 dark:border-slate-800">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setCurrentStep(2)}
              className="text-xs"
            >
              <ArrowLeft className="mr-1.5 h-3.5 w-3.5" /> Back to Qualification Rules
            </Button>
            <Button
              type="button"
              onClick={() => setCurrentStep(4)}
              className="bg-blue-800 hover:bg-blue-900 text-white text-xs font-medium"
            >
              Continue to Review &amp; Publication
              <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      )}

      {/* Demo bidders selection modal (Stage 3) */}
      <DemoBiddersModal
        open={demoModalOpen}
        onOpenChange={setDemoModalOpen}
        existingNames={bidders.map((b) => normalizeBidderName(b.legal_name))}
        onLoad={handleLoadSelectedDemoBidders}
      />

      {/* STEP 4: REVIEW & PUBLICATION */}
      {currentStep === 4 && (
        <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-xs space-y-6 dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3 dark:border-slate-800">
            <div>
              <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wide dark:text-slate-100">
                Stage 4 — Executive Summary, Statutory Review &amp; Publication
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Verify package details before final publication and hash-chain registration.
              </p>
            </div>
            <SystemLayerTag layer="AUDIT_CHAIN" size="sm" />
          </div>

          {/* Package Overview Summary */}
          <div className="grid gap-4 md:grid-cols-3">
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 space-y-2 dark:border-slate-800 dark:bg-slate-900">
              <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider dark:text-slate-400">Package Identification</span>
              <p className="text-sm font-bold text-slate-900 font-mono dark:text-slate-100">{tenderNumber}</p>
              <p className="text-xs font-semibold text-slate-800 dark:text-slate-200">{title}</p>
              <p className="text-[11px] text-slate-600 dark:text-slate-400">{organization}</p>
              <p className="text-[11px] text-slate-500 dark:text-slate-400">Dept: {department}</p>
            </div>

            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 space-y-2 dark:border-slate-800 dark:bg-slate-900">
              <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider dark:text-slate-400">Commercial Terms</span>
              <p className="text-lg font-bold text-slate-900 font-mono dark:text-slate-100">{formatINR(estimatedValue)}</p>
              <p className="text-xs text-slate-700 dark:text-slate-200">Type: <strong className="font-semibold">{tenderType}</strong></p>
              <p className="text-xs text-slate-700 dark:text-slate-200">EMD: <strong className="font-mono">{emdAmount ? formatINR(Number(emdAmount)) : 'Exempted'}</strong></p>
              <p className="text-[11px] text-slate-500 dark:text-slate-400">Closes: {closingDate}</p>
            </div>

            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 space-y-2 dark:border-slate-800 dark:bg-slate-900">
              <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider dark:text-slate-400">Rules &amp; Participants</span>
              <div className="flex items-center justify-between text-xs">
                <span>Evaluation Rules:</span>
                <strong className="font-mono text-slate-900 dark:text-slate-100">{requirements.length} Criteria</strong>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span>Total Weight:</span>
                <strong className="font-mono text-emerald-800 dark:text-emerald-400">{totalWeight}%</strong>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span>Queued Bidders:</span>
                <strong className="font-mono text-blue-900 dark:text-blue-200">{bidders.length} Vendors</strong>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span>Audit Anchor:</span>
                <strong className="text-emerald-700 dark:text-emerald-400">SHA-256 Ledger</strong>
              </div>
            </div>
          </div>

          {/* Final requirements checklist — exactly what will be persisted */}
          <div className="rounded-lg border border-slate-200 p-4 bg-white dark:border-slate-800 dark:bg-slate-900">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200">
                Final Requirements ({requirements.length}) — persisted exactly as shown
              </h3>
              <button
                type="button"
                onClick={() => setCurrentStep(2)}
                className="text-xs font-semibold text-blue-700 hover:underline dark:text-blue-400"
              >
                Modify Rules
              </button>
            </div>
            <div className="mt-3 overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
              <Table>
                <TableHeader>
                  <tr className="border-b border-slate-200 bg-slate-50 text-[10.5px] font-bold text-slate-600 uppercase tracking-wider dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
                    <TableHead className="w-10 text-center">#</TableHead>
                    <TableHead>Requirement</TableHead>
                    <TableHead className="w-40">Threshold</TableHead>
                    <TableHead className="w-24 text-center">Mandatory</TableHead>
                    <TableHead className="w-24 text-center">Weight %</TableHead>
                    <TableHead className="w-32">Rule</TableHead>
                  </tr>
                </TableHeader>
                <TableBody>
                  {requirements.map((r, idx) => {
                    const problems = validateRequirementDraft(r);
                    return (
                      <TableRow key={idx} className="text-xs hover:bg-slate-50/50 dark:hover:bg-slate-800/50">
                        <TableCell className="text-center font-mono font-bold text-slate-400 dark:text-slate-500">
                          {idx + 1}
                        </TableCell>
                        <TableCell>
                          <p className="font-semibold text-slate-900 dark:text-slate-100">{r.requirement_name || '— untitled —'}</p>
                          {problems.length > 0 && (
                            <p className="text-[10px] text-rose-600 dark:text-rose-400">{problems.join(' ')}</p>
                          )}
                        </TableCell>
                        <TableCell className="font-mono text-[11px] text-slate-600 dark:text-slate-400">
                          {r.threshold || '—'}
                        </TableCell>
                        <TableCell className="text-center">
                          {r.mandatory ? (
                            <span className="rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-bold text-blue-800 dark:bg-blue-950/60 dark:text-blue-300">Yes</span>
                          ) : (
                            <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-bold text-slate-500 dark:bg-slate-800 dark:text-slate-400">No</span>
                          )}
                        </TableCell>
                        <TableCell className="text-center font-mono font-semibold text-slate-800 dark:text-slate-200">
                          {r.weight}%
                        </TableCell>
                        <TableCell className="font-mono text-[10px] text-slate-500 dark:text-slate-400">
                          {r.rule_type}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
            <p className="mt-2 text-[11px] text-slate-500 dark:text-slate-400">
              Total weight: <strong className={`font-mono ${isWeightValid ? 'text-emerald-700 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>{totalWeight}%</strong>
              {' '}· rule configurations are stored verbatim and evaluated by the deterministic rules engine.
            </p>
          </div>

          {/* Registered Bidders Pill Summary */}
          <div className="rounded-lg border border-slate-200 p-4 bg-white space-y-3 dark:border-slate-800 dark:bg-slate-900">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200">
                Registered Bidders ({bidders.length})
              </h3>
              <button
                type="button"
                onClick={() => setCurrentStep(3)}
                className="text-xs font-semibold text-blue-700 hover:underline dark:text-blue-400"
              >
                Modify Bidders
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {bidders.map((b) => (
                <div
                  key={b.clientId}
                  className="rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-800 flex items-center gap-2 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200"
                >
                  <Building2 className="h-3.5 w-3.5 text-slate-500 dark:text-slate-400" />
                  <span>{b.legal_name}</span>
                  {b.gstin && <span className="font-mono text-[10px] text-slate-500 dark:text-slate-400">({b.gstin})</span>}
                </div>
              ))}
            </div>
          </div>

          {/* Statutory Declaration Checkbox */}
          <div className="rounded-lg border border-blue-200 bg-blue-50/50 p-4 space-y-2 dark:border-blue-800 dark:bg-blue-950/40">
            <div className="flex items-start gap-3">
              <input
                id="gfr-declaration"
                type="checkbox"
                checked={gfrDeclaration}
                onChange={(e) => setGfrDeclaration(e.target.checked)}
                className="mt-0.5 h-4 w-4 rounded border-blue-300 text-blue-800 focus:ring-blue-500 dark:border-blue-700 dark:text-blue-300"
              />
              <label htmlFor="gfr-declaration" className="text-xs leading-relaxed text-slate-800 dark:text-slate-200">
                <strong className="font-semibold text-slate-900 dark:text-slate-100">
                  Statutory Declaration under General Financial Rules (GFR 2017) &amp; CPSE Guidelines:
                </strong>{' '}
                I confirm that this tender specification complies with open procurement transparency standards, non-restrictive technical specifications, and fair evaluation rules. The registered participating bidders will be evaluated deterministically with full immutable audit logging.
              </label>
            </div>
          </div>

          {/* Publish readiness checklist */}
          {publishBlockers.length > 0 && (
            <div className="rounded-lg border border-rose-200 bg-rose-50/60 p-4 dark:border-rose-900 dark:bg-rose-950/40">
              <p className="text-xs font-bold uppercase tracking-wider text-rose-800 dark:text-rose-300">
                Publication blocked — resolve the following
              </p>
              <ul className="mt-2 list-disc pl-5 text-xs text-rose-700 dark:text-rose-400 space-y-1">
                {publishBlockers.map((b, i) => (
                  <li key={i}>{b}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex items-center justify-between border-t border-slate-100 pt-4 dark:border-slate-800">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setCurrentStep(3)}
              className="text-xs"
            >
              <ArrowLeft className="mr-1.5 h-3.5 w-3.5" /> Back to Bidders
            </Button>
            <Button
              type="button"
              loading={publishing}
              disabled={!canPublish}
              title={!canPublish ? 'Resolve the blockers above or confirm the statutory declaration.' : undefined}
              onClick={handlePublishTender}
              className="bg-emerald-700 hover:bg-emerald-800 text-white text-xs font-semibold px-6 shadow-sm disabled:cursor-not-allowed disabled:opacity-50"
            >
              <ShieldCheck className="mr-1.5 h-4 w-4" />
              Publish Tender &amp; Register Bidders
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
