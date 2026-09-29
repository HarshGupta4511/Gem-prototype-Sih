import { useEffect, useMemo, useState } from 'react';
import { useForm, type Resolver } from 'react-hook-form';
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
  Scale,
  ShieldCheck,
  Sparkles,
  Trash2,
  UserCheck,
} from 'lucide-react';
import { getErrorMessage, tendersApi } from '../../lib/api';
import { cn, formatDate, formatINR, labelize } from '../../lib/utils';
import { useToast } from '../ui/toaster';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Input, Select, Textarea } from '../ui/input';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../ui/table';
import type {
  CreateTenderRequest,
  RequirementDraft,
  SuggestedRequirement,
  SuggestRequirementsRequest,
  TenderType,
  BidType,
} from '../../types';
import { SystemLayerTag } from '../common/SystemLayerTag';

const todayStr = () => new Date().toISOString().slice(0, 10);

const step1Schema = z
  .object({
    tender_number: z.string().min(1, 'Tender number is required (e.g. CPCL-2026-004)'),
    title: z.string().min(1, 'Title is required'),
    organization: z.string().min(1, 'Organization is required'),
    department: z.string().min(1, 'Department is required'),
    description: z.string().min(1, 'Detailed description is required'),
    closing_date: z.string().min(1, 'Closing date is required'),
    estimated_value_inr: z.coerce
      .number({ invalid_type_error: 'Enter a valid amount' })
      .min(0, 'Estimated value must be non-negative'),
    tender_type: z.string(),
    bid_type: z.string(),
    emd_amount_inr: z.string(),
    delivery_period: z.string(),
    place_of_delivery: z.string(),
  })
  .refine((v) => v.closing_date > todayStr(), {
    message: 'Closing date must be strictly after the tender issue date.',
    path: ['closing_date'],
  })
  .refine((v) => v.emd_amount_inr === '' || (!Number.isNaN(Number(v.emd_amount_inr)) && Number(v.emd_amount_inr) >= 0), {
    message: 'EMD must be a valid non-negative number',
    path: ['emd_amount_inr'],
  });

type Step1Form = z.infer<typeof step1Schema>;

function zodResolver(schema: typeof step1Schema): Resolver<Step1Form> {
  return async (values) => {
    const result = schema.safeParse(values);
    if (result.success) return { values: result.data, errors: {} };
    const errors: Record<string, { type: string; message: string }> = {};
    for (const issue of result.error.issues) {
      const key = issue.path.join('.');
      if (!errors[key]) errors[key] = { type: issue.code, message: issue.message };
    }
    return { values: {}, errors };
  };
}

interface DraftRow extends RequirementDraft {
  clientId: string;
  autoWeight: number | null;
}

const STANDARD_TEMPLATE: RequirementDraft[] = [
  {
    requirement_name: 'GST Registration Status',
    category: 'STATUTORY',
    description: 'Bidder must hold an active GST registration without cancellation.',
    mandatory: true,
    rule_type: 'REGISTRATION_STATUS',
    rule_config: { source: 'GSTN', identifier_field: 'gstin', require_status: 'ACTIVE' },
    threshold: 'Active GST registration',
    verification_source: 'GSTN',
    weight: 10,
  },
  {
    requirement_name: 'PAN Statutory Verification',
    category: 'STATUTORY',
    description: 'Bidder PAN must be active and linked as per income tax database.',
    mandatory: true,
    rule_type: 'REGISTRATION_STATUS',
    rule_config: { source: 'PAN_IT', identifier_field: 'pan', require_status: 'ACTIVE' },
    threshold: 'Active PAN',
    verification_source: 'PAN_IT',
    weight: 5,
  },
  {
    requirement_name: 'Average Annual Turnover',
    category: 'FINANCIAL',
    description: 'Minimum average annual turnover over the last 3 financial years.',
    mandatory: true,
    rule_type: 'MINIMUM',
    rule_config: { value_source: 'extracted.turnover_inr', operator: '>=', value: 25000000 },
    threshold: '₹2,50,00,000',
    verification_source: null,
    weight: 15,
  },
  {
    requirement_name: 'Relevant Technical Experience',
    category: 'EXPERIENCE',
    description: 'Minimum years of experience in similar works or refinery supplies.',
    mandatory: true,
    rule_type: 'MINIMUM',
    rule_config: { value_source: 'extracted.experience_years', operator: '>=', value: 3 },
    threshold: '3 years',
    verification_source: null,
    weight: 15,
  },
  {
    requirement_name: 'Past Contract Performance',
    category: 'EXPERIENCE',
    description: 'Satisfactory completion of single contract of at least 40% bid value.',
    mandatory: true,
    rule_type: 'MINIMUM',
    rule_config: { value_source: 'extracted.past_performance_pct', operator: '>=', value: 40 },
    threshold: '40% single order',
    verification_source: null,
    weight: 10,
  },
  {
    requirement_name: 'OEM Authorization Undertaking',
    category: 'OEM',
    description: 'Manufacturer authorization form (MAF) signed by authorized signatory.',
    mandatory: true,
    rule_type: 'BOOLEAN',
    rule_config: { value_source: 'extracted.oem_authorization_valid', expected: true },
    threshold: 'Valid OEM MAF',
    verification_source: null,
    weight: 15,
  },
  {
    requirement_name: 'Make In India (MII) Local Content',
    category: 'LOCAL_CONTENT',
    description: 'Minimum local content under Public Procurement Order (PPO).',
    mandatory: false,
    rule_type: 'MINIMUM',
    rule_config: { value_source: 'extracted.local_content_pct', operator: '>=', value: 50 },
    threshold: '50% local content',
    verification_source: null,
    weight: 10,
  },
  {
    requirement_name: 'Earnest Money Deposit (EMD)',
    category: 'FINANCIAL',
    description: 'Submission of BG / Online payment receipt for EMD.',
    mandatory: true,
    rule_type: 'MINIMUM',
    rule_config: { value_source: 'extracted.emd_amount_inr', operator: '>=', value: 500000 },
    threshold: '₹5,00,000',
    verification_source: null,
    weight: 10,
  },
  {
    requirement_name: 'Consolidated Bid Dossier',
    category: 'DOCUMENT',
    description: 'Complete signed technical packet and statutory annexures.',
    mandatory: true,
    rule_type: 'DOCUMENT_REQUIRED',
    rule_config: { document_types: ['BID_DOSSIER'] },
    threshold: 'Complete Bid Dossier',
    verification_source: null,
    weight: 10,
  },
];

let clientSeq = 0;
function toDraftRow(d: RequirementDraft, autoWeight: number | null): DraftRow {
  clientSeq += 1;
  return {
    ...d,
    rule_config: d.rule_config ?? {},
    clientId: `draft-${Date.now()}-${clientSeq}`,
    autoWeight,
  };
}

const WIZARD_STEPS = [
  { n: 1, title: 'Basic Details', icon: FileText, desc: 'Package identification & dates' },
  { n: 2, title: 'Requirements', icon: ListChecks, desc: 'Statutory rules & weight distribution' },
  { n: 3, title: 'Review & Create', icon: ShieldCheck, desc: 'Verification & publication' },
];

interface TenderWizardProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: () => void;
}

export default function TenderWizard({ open, onOpenChange, onCreated }: TenderWizardProps) {
  const { toast } = useToast();
  const [step, setStep] = useState(1);
  const [drafts, setDrafts] = useState<DraftRow[]>(() =>
    STANDARD_TEMPLATE.map((r) => toDraftRow(r, r.weight))
  );
  const [suggesting, setSuggesting] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [confirmedDeclaration, setConfirmedDeclaration] = useState(false);

  const {
    register,
    handleSubmit,
    getValues,
    reset,
    formState: { errors },
  } = useForm<Step1Form>({
    resolver: zodResolver(step1Schema),
    defaultValues: {
      tender_number: `CPCL-2026-${Math.floor(100 + Math.random() * 900)}`,
      title: 'Procurement of Industrial Pumping Systems & Rotary Spares',
      organization: 'Chennai Petroleum Corporation Limited (CPCL)',
      department: 'Procurement - Mechanical & Projects',
      description:
        'Procurement of API 610 compliant centrifugal high-pressure pumps including testing, inspection, civil foundation verification, alignment, and commissioning at CPCL Manali Refinery.',
      closing_date: new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10),
      estimated_value_inr: 50000000,
      tender_type: 'OPEN',
      bid_type: 'TWO_PACKET',
      emd_amount_inr: '1000000',
      delivery_period: '24 Weeks',
      place_of_delivery: 'CPCL Manali Refinery, Chennai, Tamil Nadu',
    },
  });

  useEffect(() => {
    if (open) {
      setStep(1);
      setCreateError(null);
      setConfirmedDeclaration(false);
    }
  }, [open]);

  const step1Values = getValues();

  // Weight calculations
  const totalWeight = useMemo(() => {
    return drafts.reduce((sum, d) => sum + (Number.isFinite(d.weight) ? d.weight : 0), 0);
  }, [drafts]);

  const mandatoryCount = useMemo(() => drafts.filter((d) => d.mandatory).length, [drafts]);
  const isWeightValid = Math.round(totalWeight) === 100;
  const isStep2Valid = isWeightValid && drafts.length > 0 && drafts.every((d) => d.requirement_name.trim().length > 0);

  const onStep1Submit = () => {
    setStep(2);
  };

  const handleSuggest = async () => {
    const desc = step1Values.description;
    if (!desc || desc.length < 10) {
      toast({ title: 'Tender description needed', description: 'Please provide a descriptive scope in Step 1.' });
      return;
    }
    setSuggesting(true);
    try {
      const res = await tendersApi.suggestRequirements({
        title: step1Values.title || 'Procurement Tender',
        description: desc,
        department: step1Values.department,
      });
      const suggestions = res.requirements || [];
      if (suggestions && suggestions.length > 0) {
        const newRows = suggestions.map((s: SuggestedRequirement) =>
          toDraftRow(
            {
              requirement_name: s.requirement_name,
              category: 'TECHNICAL',
              description: s.description || '',
              mandatory: s.mandatory,
              rule_type: 'CUSTOM_RULE',
              rule_config: {},
              threshold: s.threshold || null,
              verification_source: null,
              weight: s.weight || 10,
            },
            s.weight || 10
          )
        );
        setDrafts(newRows);
        toast({ title: 'AI Requirements Generated', description: `${newRows.length} requirements generated from tender scope.` });
      }
    } catch {
      toast({ title: 'AI Assistant Notice', description: 'Could not fetch suggestions. Using standard template.' });
    } finally {
      setSuggesting(false);
    }
  };

  const addManualRow = () => {
    setDrafts((prev) => [
      ...prev,
      toDraftRow(
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
        5
      ),
    ]);
  };

  const updateDraft = (clientId: string, patch: Partial<DraftRow>) => {
    setDrafts((prev) => prev.map((d) => (d.clientId === clientId ? { ...d, ...patch } : d)));
  };

  const removeDraft = (clientId: string) => {
    setDrafts((prev) => prev.filter((d) => d.clientId !== clientId));
  };

  const handleCreate = async () => {
    if (!confirmedDeclaration) {
      setCreateError('You must confirm the statutory compliance declaration before publishing.');
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      const req: CreateTenderRequest = {
        tender_number: step1Values.tender_number,
        title: step1Values.title,
        organization: step1Values.organization,
        department: step1Values.department,
        description: step1Values.description,
        closing_date: step1Values.closing_date,
        estimated_value_inr: Number(step1Values.estimated_value_inr),
        tender_type: (step1Values.tender_type as TenderType) || null,
        bid_type: (step1Values.bid_type as BidType) || null,
        emd_amount_inr: step1Values.emd_amount_inr ? Number(step1Values.emd_amount_inr) : undefined,
        delivery_period: step1Values.delivery_period,
        place_of_delivery: step1Values.place_of_delivery,
        requirements: drafts.map((d) => ({
          requirement_name: d.requirement_name,
          category: d.category,
          description: d.description,
          mandatory: d.mandatory,
          rule_type: d.rule_type,
          rule_config: d.rule_config,
          threshold: d.threshold,
          verification_source: d.verification_source,
          weight: d.weight,
        })),
      };

      await tendersApi.create(req);
      toast({ title: 'Tender Published', description: `Tender ${req.tender_number} has been registered.` });
      onOpenChange(false);
      onCreated?.();
    } catch (err: unknown) {
      setCreateError(getErrorMessage(err));
    } finally {
      setCreating(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] flex flex-col p-0 overflow-hidden bg-white border border-slate-300">
        {/* Wizard Header */}
        <DialogHeader className="border-b border-slate-200 bg-slate-50/80 px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-blue-800 font-mono">
                  CPCL / GeM Tender Configuration
                </span>
                <span className="rounded bg-blue-100 px-2 py-0.2 text-[10px] font-semibold text-blue-900 border border-blue-200">
                  Step {step} of 3
                </span>
              </div>
              <DialogTitle className="mt-1 text-lg font-bold text-slate-900 font-serif">
                Create &amp; Publish Procurement Package
              </DialogTitle>
            </div>
            <div className="text-right hidden sm:block">
              <span className="text-xs font-mono text-slate-500">Date: {todayStr()}</span>
            </div>
          </div>

          {/* Stepper Progress Bar */}
          <div className="mt-4 grid grid-cols-3 gap-2 border-t border-slate-200 pt-3">
            {WIZARD_STEPS.map((s) => {
              const Icon = s.icon;
              const isActive = s.n === step;
              const isPast = s.n < step;
              return (
                <div
                  key={s.n}
                  className={`flex items-center gap-2.5 rounded border p-2 text-xs transition-colors ${
                    isActive
                      ? 'border-blue-700 bg-blue-50/70 text-blue-950 font-semibold'
                      : isPast
                      ? 'border-emerald-300 bg-emerald-50/50 text-emerald-950'
                      : 'border-slate-200 bg-white text-slate-400'
                  }`}
                >
                  <div
                    className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-bold ${
                      isActive
                        ? 'bg-blue-800 text-white'
                        : isPast
                        ? 'bg-emerald-600 text-white'
                        : 'bg-slate-200 text-slate-600'
                    }`}
                  >
                    {isPast ? <CheckCircle2 className="h-3.5 w-3.5" /> : s.n}
                  </div>
                  <div className="min-w-0">
                    <p className="truncate text-xs font-bold leading-tight">{s.title}</p>
                    <p className="truncate text-[10px] text-slate-500 font-normal">{s.desc}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </DialogHeader>

        {/* Wizard Step Body */}
        <DialogBody className="flex-1 overflow-y-auto p-6 bg-slate-50/40">
          {/* STEP 1: BASIC DETAILS */}
          {step === 1 && (
            <form id="wizard-step1" onSubmit={handleSubmit(onStep1Submit)} className="space-y-6">
              {/* Group 1: Tender Information */}
              <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-2xs">
                <div className="border-b border-slate-100 pb-2 mb-3">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center gap-1.5">
                    <FileText className="h-3.5 w-3.5 text-blue-700" />
                    Tender Package Identification
                  </h3>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1" htmlFor="tender_number">
                      Tender Reference Number *
                    </label>
                    <Input
                      id="tender_number"
                      placeholder="e.g. CPCL-2026-004"
                      className="border-slate-300 font-mono text-xs"
                      {...register('tender_number')}
                    />
                    {errors.tender_number && <p className="mt-1 text-xs text-rose-600">{errors.tender_number.message}</p>}
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1" htmlFor="department">
                      Procuring Department *
                    </label>
                    <Input
                      id="department"
                      placeholder="e.g. Procurement - Mechanical"
                      className="border-slate-300 text-xs"
                      {...register('department')}
                    />
                    {errors.department && <p className="mt-1 text-xs text-rose-600">{errors.department.message}</p>}
                  </div>

                  <div className="sm:col-span-2">
                    <label className="block text-xs font-semibold text-slate-700 mb-1" htmlFor="title">
                      Tender Package Title *
                    </label>
                    <Input
                      id="title"
                      placeholder="e.g. Supply, Installation & Commissioning of High-Pressure Pumps"
                      className="border-slate-300 text-xs"
                      {...register('title')}
                    />
                    {errors.title && <p className="mt-1 text-xs text-rose-600">{errors.title.message}</p>}
                  </div>

                  <div className="sm:col-span-2">
                    <label className="block text-xs font-semibold text-slate-700 mb-1" htmlFor="organization">
                      Procuring Entity / Organization *
                    </label>
                    <Input
                      id="organization"
                      placeholder="Chennai Petroleum Corporation Limited"
                      className="border-slate-300 text-xs"
                      {...register('organization')}
                    />
                    {errors.organization && <p className="mt-1 text-xs text-rose-600">{errors.organization.message}</p>}
                  </div>

                  <div className="sm:col-span-2">
                    <label className="block text-xs font-semibold text-slate-700 mb-1" htmlFor="description">
                      Technical Scope &amp; Objective *
                    </label>
                    <Textarea
                      id="description"
                      rows={3}
                      placeholder="Detail the technical specifications, standards (API/ISO), delivery requirements, and scope of work."
                      className="border-slate-300 text-xs leading-relaxed"
                      {...register('description')}
                    />
                    {errors.description && <p className="mt-1 text-xs text-rose-600">{errors.description.message}</p>}
                  </div>
                </div>
              </div>

              {/* Group 2: Financial & Operational */}
              <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-2xs">
                <div className="border-b border-slate-100 pb-2 mb-3">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center gap-1.5">
                    <Scale className="h-3.5 w-3.5 text-blue-700" />
                    Financial &amp; Commercial Terms
                  </h3>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1" htmlFor="estimated_value_inr">
                      Estimated Value (INR) *
                    </label>
                    <Input
                      id="estimated_value_inr"
                      type="number"
                      placeholder="50000000"
                      className="border-slate-300 font-mono text-xs"
                      {...register('estimated_value_inr')}
                    />
                    {errors.estimated_value_inr && (
                      <p className="mt-1 text-xs text-rose-600">{errors.estimated_value_inr.message}</p>
                    )}
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1" htmlFor="emd_amount_inr">
                      EMD Amount (INR)
                    </label>
                    <Input
                      id="emd_amount_inr"
                      placeholder="1000000"
                      className="border-slate-300 font-mono text-xs"
                      {...register('emd_amount_inr')}
                    />
                    {errors.emd_amount_inr && (
                      <p className="mt-1 text-xs text-rose-600">{errors.emd_amount_inr.message}</p>
                    )}
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1" htmlFor="delivery_period">
                      Delivery / Contract Period
                    </label>
                    <Input
                      id="delivery_period"
                      placeholder="e.g. 24 Weeks"
                      className="border-slate-300 text-xs"
                      {...register('delivery_period')}
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1" htmlFor="place_of_delivery">
                      Consignee / Delivery Location
                    </label>
                    <Input
                      id="place_of_delivery"
                      placeholder="CPCL Manali Refinery"
                      className="border-slate-300 text-xs"
                      {...register('place_of_delivery')}
                    />
                  </div>
                </div>
              </div>

              {/* Group 3: Configuration & Dates */}
              <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-2xs">
                <div className="border-b border-slate-100 pb-2 mb-3">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center gap-1.5">
                    <Calendar className="h-3.5 w-3.5 text-blue-700" />
                    Bidding Mode &amp; Deadlines
                  </h3>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1" htmlFor="tender_type">
                      Tender Type
                    </label>
                    <Select id="tender_type" className="border-slate-300 text-xs" {...register('tender_type')}>
                      <option value="OPEN">OPEN (Advertised)</option>
                      <option value="LIMITED">LIMITED (Empaneled)</option>
                      <option value="SINGLE">SINGLE TENDER</option>
                    </Select>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1" htmlFor="bid_type">
                      Evaluation Envelope
                    </label>
                    <Select id="bid_type" className="border-slate-300 text-xs" {...register('bid_type')}>
                      <option value="TWO_PACKET">Two-Packet (Tech + Price)</option>
                      <option value="SINGLE_PACKET">Single Packet</option>
                    </Select>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">
                      Issue Date (System Date)
                    </label>
                    <Input
                      value={todayStr()}
                      disabled
                      className="bg-slate-100 border-slate-300 font-mono text-xs text-slate-500 cursor-not-allowed"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1" htmlFor="closing_date">
                      Bid Closing Date *
                    </label>
                    <Input
                      id="closing_date"
                      type="date"
                      className="border-slate-300 font-mono text-xs"
                      {...register('closing_date')}
                    />
                    {errors.closing_date && (
                      <p className="mt-1 text-xs text-rose-600">{errors.closing_date.message}</p>
                    )}
                  </div>
                </div>
              </div>
            </form>
          )}

          {/* STEP 2: REQUIREMENTS & WEIGHTS */}
          {step === 2 && (
            <div className="space-y-5">
              {/* AI REQUIREMENT ASSISTANCE BLOCK */}
              <div className="rounded-lg border border-indigo-200 bg-indigo-50/50 p-4 shadow-2xs">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-indigo-100 pb-3">
                  <div className="flex items-center gap-2">
                    <span className="flex h-7 w-7 items-center justify-center rounded bg-indigo-600 text-white">
                      <Sparkles className="h-4 w-4" />
                    </span>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold uppercase tracking-wider text-indigo-950 font-serif">
                          AI Requirement Assistance
                        </span>
                        <SystemLayerTag layer="AI_ASSISTED" size="sm" />
                      </div>
                      <p className="text-[11px] text-indigo-900/80">
                        Synthesizes statutory &amp; technical criteria based on tender category and technical scope.
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => setDrafts(STANDARD_TEMPLATE.map((r) => toDraftRow(r, r.weight)))}
                      className="border-indigo-300 bg-white hover:bg-indigo-50 text-indigo-900 text-xs"
                    >
                      Reset Standard GeM Rules
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      onClick={handleSuggest}
                      loading={suggesting}
                      className="bg-indigo-700 hover:bg-indigo-800 text-white text-xs font-medium"
                    >
                      <Sparkles className="mr-1.5 h-3.5 w-3.5" />
                      Generate from Scope
                    </Button>
                  </div>
                </div>

                <div className="mt-2.5 flex items-center justify-between text-xs text-indigo-900">
                  <span>Advisory only: Procurement Officer retains full discretion to add, adjust weights, or remove criteria.</span>
                  <button
                    type="button"
                    onClick={addManualRow}
                    className="inline-flex items-center gap-1 font-semibold text-indigo-800 hover:underline"
                  >
                    <Plus className="h-3.5 w-3.5" /> Add Custom Rule
                  </button>
                </div>
              </div>

              {/* Requirements Registry Table */}
              <div className="rounded-lg border border-slate-200 bg-white overflow-hidden shadow-2xs">
                <Table>
                  <TableHeader>
                    <tr className="border-b border-slate-200 bg-slate-50/80 text-[10.5px] font-bold text-slate-600 uppercase tracking-wider">
                      <TableHead className="py-2.5 px-3">Requirement &amp; Description</TableHead>
                      <TableHead className="py-2.5 px-3">Rule Type</TableHead>
                      <TableHead className="py-2.5 px-3">Threshold / Criteria</TableHead>
                      <TableHead className="py-2.5 px-3 text-center">Mandatory</TableHead>
                      <TableHead className="py-2.5 px-3 text-right">Weight (%)</TableHead>
                      <TableHead className="py-2.5 px-3 text-right w-12" />
                    </tr>
                  </TableHeader>
                  <TableBody>
                    {drafts.map((d) => (
                      <TableRow key={d.clientId} className="hover:bg-slate-50/50">
                        <TableCell className="py-2.5 px-3">
                          <Input
                            value={d.requirement_name}
                            onChange={(e) => updateDraft(d.clientId, { requirement_name: e.target.value })}
                            placeholder="Requirement name"
                            className="text-xs font-medium border-slate-300"
                          />
                        </TableCell>
                        <TableCell className="py-2.5 px-3">
                          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-mono text-slate-700 border border-slate-200">
                            {d.rule_type}
                          </span>
                        </TableCell>
                        <TableCell className="py-2.5 px-3">
                          <Input
                            value={d.threshold ?? ''}
                            onChange={(e) => updateDraft(d.clientId, { threshold: e.target.value })}
                            placeholder="e.g. Active GST or ₹2.5 Cr"
                            className="text-xs border-slate-300"
                          />
                        </TableCell>
                        <TableCell className="py-2.5 px-3 text-center">
                          <Select
                            value={d.mandatory ? 'yes' : 'no'}
                            onChange={(e) => updateDraft(d.clientId, { mandatory: e.target.value === 'yes' })}
                            className="text-xs py-1 h-8"
                          >
                            <option value="yes">YES</option>
                            <option value="no">NO</option>
                          </Select>
                        </TableCell>
                        <TableCell className="py-2.5 px-3 text-right">
                          <Input
                            type="number"
                            min="0"
                            max="100"
                            value={Number.isFinite(d.weight) ? d.weight : ''}
                            onChange={(e) => updateDraft(d.clientId, { weight: Number(e.target.value) || 0 })}
                            className="w-16 text-right font-mono text-xs ml-auto border-slate-300"
                          />
                        </TableCell>
                        <TableCell className="py-2.5 px-3 text-right">
                          <button
                            type="button"
                            onClick={() => removeDraft(d.clientId)}
                            className="rounded p-1 text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors"
                            title="Remove criteria"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

              {/* Weight Distribution Tally Box */}
              <div
                className={`rounded-lg border p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                  isWeightValid
                    ? 'border-emerald-300 bg-emerald-50/60 text-emerald-950'
                    : 'border-rose-300 bg-rose-50/60 text-rose-950'
                }`}
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold uppercase tracking-wider">
                      Running Weight Tally:
                    </span>
                    <span className="font-mono text-base font-bold">
                      {Math.round(totalWeight)} / 100%
                    </span>
                    {isWeightValid ? (
                      <span className="inline-flex items-center gap-1 rounded bg-emerald-200/80 px-2 py-0.5 text-[10px] font-bold text-emerald-900">
                        <CheckCircle2 className="h-3 w-3" /> Exact 100%
                      </span>
                    ) : (
                      <span className="rounded bg-rose-200/80 px-2 py-0.5 text-[10px] font-bold text-rose-900">
                        Deviation: {Math.round(totalWeight) - 100}%
                      </span>
                    )}
                  </div>
                  <p className="text-xs mt-0.5 opacity-90">
                    {drafts.length} criteria defined • {mandatoryCount} mandatory disqualification rules
                  </p>
                </div>

                {!isWeightValid && (
                  <span className="text-xs font-semibold text-rose-800">
                    Weights must sum to exactly 100% before advancing.
                  </span>
                )}
              </div>
            </div>
          )}

          {/* STEP 3: REVIEW & CREATE */}
          {step === 3 && (
            <div className="space-y-5">
              {/* Government Dossier Summary Panel */}
              <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-2xs">
                <div className="border-b border-slate-100 pb-3 mb-4 flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wide">
                      Tender Package Dossier Summary
                    </h3>
                    <p className="text-xs text-slate-500">
                      Final verification of commercial, statutory, and delivery specifications
                    </p>
                  </div>
                  <span className="font-mono text-xs font-semibold text-blue-900 bg-blue-50 px-2.5 py-1 rounded border border-blue-200">
                    {step1Values.tender_number}
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-3 text-xs">
                  <div>
                    <span className="text-slate-500 block">Package Title:</span>
                    <span className="font-semibold text-slate-900">{step1Values.title}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Procuring Entity:</span>
                    <span className="font-medium text-slate-800">{step1Values.organization}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Department:</span>
                    <span className="font-medium text-slate-800">{step1Values.department}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Estimated Package Value:</span>
                    <span className="font-mono font-bold text-slate-900">
                      {formatINR(Number(step1Values.estimated_value_inr))}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">EMD Amount:</span>
                    <span className="font-mono font-medium text-slate-800">
                      {step1Values.emd_amount_inr ? formatINR(Number(step1Values.emd_amount_inr)) : 'Exempted / Zero'}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Closing Date &amp; Time:</span>
                    <span className="font-mono font-bold text-rose-800">
                      {formatDate(step1Values.closing_date)} (17:30 IST)
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Tender / Bid Envelope:</span>
                    <span className="font-medium text-slate-800">
                      {step1Values.tender_type} • {step1Values.bid_type}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Delivery Timeline:</span>
                    <span className="font-medium text-slate-800">{step1Values.delivery_period}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Consignee Location:</span>
                    <span className="font-medium text-slate-800">{step1Values.place_of_delivery}</span>
                  </div>
                </div>

                <div className="mt-4 border-t border-slate-100 pt-3">
                  <span className="text-slate-500 block text-xs">Scope of Supply:</span>
                  <p className="mt-1 text-xs text-slate-700 leading-relaxed bg-slate-50 p-2.5 rounded border border-slate-200">
                    {step1Values.description}
                  </p>
                </div>
              </div>

              {/* Requirements Breakdown Table */}
              <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-2xs">
                <div className="flex items-center justify-between border-b border-slate-100 pb-2 mb-3">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                    Active Evaluation Criteria ({drafts.length} rules)
                  </h4>
                  <span className="text-xs font-semibold text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                    Total Weight: 100%
                  </span>
                </div>

                <div className="max-h-48 overflow-y-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-slate-200 text-slate-500 font-semibold">
                        <th className="py-1.5 px-2">Rule Name</th>
                        <th className="py-1.5 px-2">Threshold</th>
                        <th className="py-1.5 px-2 text-center">Type</th>
                        <th className="py-1.5 px-2 text-right">Weight</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {drafts.map((d) => (
                        <tr key={d.clientId}>
                          <td className="py-1.5 px-2 font-medium text-slate-900">{d.requirement_name}</td>
                          <td className="py-1.5 px-2 text-slate-600">{d.threshold || '—'}</td>
                          <td className="py-1.5 px-2 text-center">
                            {d.mandatory ? (
                              <span className="text-[10px] font-bold text-rose-700 bg-rose-50 px-1.5 py-0.2 rounded border border-rose-200">
                                MANDATORY
                              </span>
                            ) : (
                              <span className="text-[10px] text-slate-500">Scored</span>
                            )}
                          </td>
                          <td className="py-1.5 px-2 text-right font-mono font-semibold">{d.weight}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Official Declaration Checkbox */}
              <div className="rounded-lg border border-blue-200 bg-blue-50/70 p-4">
                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={confirmedDeclaration}
                    onChange={(e) => setConfirmedDeclaration(e.target.checked)}
                    className="mt-0.5 h-4 w-4 rounded border-blue-300 text-blue-800 focus:ring-blue-700"
                  />
                  <div className="text-xs text-blue-950 leading-relaxed">
                    <strong className="block font-semibold text-blue-900 mb-0.5">
                      Statutory Procurement Officer Undertaking
                    </strong>
                    I confirm that these tender requirements, eligibility thresholds, and evaluation weights strictly adhere to CPCL procurement policy, GFR 2017 provisions, and GeM procurement guidelines.
                  </div>
                </label>
              </div>

              {createError && (
                <div className="rounded border border-rose-300 bg-rose-50 p-3 text-xs text-rose-800">
                  {createError}
                </div>
              )}
            </div>
          )}
        </DialogBody>

        {/* Wizard Footer Controls */}
        <DialogFooter className="border-t border-slate-200 bg-white px-6 py-3.5 flex items-center justify-between">
          <div>
            {step > 1 && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setStep((s) => s - 1)}
                disabled={creating}
                className="text-xs"
              >
                <ArrowLeft className="mr-1.5 h-3.5 w-3.5" />
                Previous Step
              </Button>
            )}
          </div>

          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => onOpenChange(false)}
              disabled={creating}
              className="text-xs text-slate-600"
            >
              Cancel
            </Button>

            {step === 1 && (
              <Button
                type="submit"
                form="wizard-step1"
                size="sm"
                className="bg-blue-800 hover:bg-blue-900 text-white text-xs font-medium"
              >
                Proceed to Requirements
                <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
              </Button>
            )}

            {step === 2 && (
              <Button
                type="button"
                size="sm"
                onClick={() => setStep(3)}
                disabled={!isStep2Valid}
                className="bg-blue-800 hover:bg-blue-900 text-white text-xs font-medium"
              >
                Proceed to Final Review
                <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
              </Button>
            )}

            {step === 3 && (
              <Button
                type="button"
                size="sm"
                onClick={handleCreate}
                disabled={creating || !confirmedDeclaration}
                className="bg-blue-800 hover:bg-blue-900 text-white text-xs font-medium shadow-xs"
              >
                {creating && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
                <ShieldCheck className="mr-1.5 h-3.5 w-3.5 text-blue-200" />
                Publish Tender Package
              </Button>
            )}
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
