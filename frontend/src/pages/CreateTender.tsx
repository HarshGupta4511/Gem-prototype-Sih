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
  Plus,
  RefreshCw,
  Scale,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Trash2,
  Upload,
  UserCheck,
  Users,
} from 'lucide-react';
import { tendersApi, bidsApi, getErrorMessage } from '../lib/api';
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
import type {
  CreateTenderRequest,
  RequirementDraft,
  RequirementCategory,
  RuleType,
  AdapterSource,
  SuggestedRequirement,
  TenderType,
  BidType,
  CreateBidRequest,
} from '../types';

interface QueuedBidder {
  clientId: string;
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

const DEFAULT_REQUIREMENTS: RequirementDraft[] = [
  {
    requirement_name: 'Active GST Registration (Form GST REG-06)',
    category: 'STATUTORY',
    description: 'Active GST registration certificate in the state of supply; status verified with GSTN portal.',
    mandatory: true,
    rule_type: 'REGISTRATION_STATUS',
    rule_config: { status: 'ACTIVE' },
    verification_source: 'GSTN',
    weight: 15,
    policy_reference: 'GFR 2017 Rule 144(i) & GeM General Terms',
  },
  {
    requirement_name: 'Valid Income Tax PAN & Compliance',
    category: 'STATUTORY',
    description: 'Permanent Account Number in bidder entity name; PAN-Aadhaar linking and active taxpayer status.',
    mandatory: true,
    rule_type: 'IDENTITY_MATCH',
    rule_config: { match_field: 'pan' },
    verification_source: 'PAN_IT',
    weight: 10,
    policy_reference: 'Income Tax Act 1961 Section 139A',
  },
  {
    requirement_name: 'Minimum 3-Year Average Annual Turnover',
    category: 'FINANCIAL',
    description: 'Average annual financial turnover during last 3 consecutive financial years must meet required threshold.',
    mandatory: true,
    rule_type: 'MINIMUM',
    rule_config: { field: 'turnover_inr', operator: '>=' },
    threshold: '₹1.50 Crore',
    expected_value: '15000000',
    verification_source: null,
    weight: 25,
    policy_reference: 'CPCL Procurement Manual §4.2',
  },
  {
    requirement_name: 'Prior Relevant Experience & Commissioning',
    category: 'EXPERIENCE',
    description: 'Satisfactory completion of similar supply or execution contracts with PSUs or industrial refineries.',
    mandatory: true,
    rule_type: 'EXISTENCE',
    rule_config: { document_type: 'EXPERIENCE_CERTIFICATE' },
    verification_source: null,
    weight: 20,
    policy_reference: 'Public Procurement Policy for CPSEs §3.1',
  },
  {
    requirement_name: 'MSME / Udyam Registration (If claiming benefit)',
    category: 'REGISTRATION',
    description: 'Valid Udyam Registration Certificate for micro/small enterprise benefits under Public Procurement Policy.',
    mandatory: false,
    rule_type: 'REGISTRATION_STATUS',
    rule_config: { status: 'ACTIVE' },
    verification_source: 'UDYAM',
    weight: 10,
    policy_reference: 'Public Procurement Policy for MSEs Order 2012',
  },
  {
    requirement_name: 'Make in India (MII) Local Content Declaration',
    category: 'LOCAL_CONTENT',
    description: 'Self-certification or CA certificate indicating minimum 50% local value addition under PPP-MII order.',
    mandatory: true,
    rule_type: 'MINIMUM',
    rule_config: { field: 'local_content_pct', operator: '>=' },
    threshold: '50% Local Content',
    expected_value: '50',
    verification_source: null,
    weight: 20,
    policy_reference: 'DPIIT Order No. P-45021/2/2017-PP (BE-II)',
  },
];

const SAMPLE_DEMO_BIDDERS: Omit<QueuedBidder, 'clientId'>[] = [
  {
    legal_name: 'Apex Flow Systems Pvt Ltd',
    trade_name: 'Apex Industrial Solutions',
    pan: 'AAACA1234A',
    gstin: '33AAACA1234A1Z5',
    udyam: 'UDYAM-TN-02-0012345',
    cin: 'U29100TN2015PTC099887',
    registered_address: 'Plot 42, SIDCO Industrial Estate, Ambattur, Chennai - 600058',
    contact_name: 'R. Ramanathan',
    contact_email: 'contracts@apexflow.co.in',
    contact_phone: '+91 98400 12345',
  },
  {
    legal_name: 'Bharat Mech Works',
    trade_name: 'Bharat Engineering',
    pan: 'BBBCB5678B',
    gstin: '33BBBCB5678B1Z2',
    udyam: 'UDYAM-TN-02-0054321',
    cin: 'U28110TN2012PTC084512',
    registered_address: '14/B G.S.T. Road, Guindy, Chennai - 600032',
    contact_name: 'S. Sundaram',
    contact_email: 'sales@bharatmech.in',
    contact_phone: '+91 98410 56789',
  },
  {
    legal_name: 'Crestline Pumps Pvt Ltd',
    trade_name: 'Crestline India',
    pan: 'CCCC1234C',
    gstin: '27CCCC1234C1Z9',
    udyam: 'UDYAM-MH-01-0098765',
    cin: 'U29120MH2018PTC112233',
    registered_address: 'TTC Industrial Area, MIDC, Navi Mumbai - 400705',
    contact_name: 'A. K. Sharma',
    contact_email: 'tenders@crestlinepumps.com',
    contact_phone: '+91 98200 45678',
  },
];

export default function CreateTender() {
  const navigate = useNavigate();
  const { toast } = useToast();

  const [currentStep, setCurrentStep] = React.useState(1);
  const [publishing, setPublishing] = React.useState(false);
  const [aiGenerating, setAiGenerating] = React.useState(false);
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
  const [bidType, setBidType] = React.useState<BidType>('TWO_PACKET');
  const [emdAmount, setEmdAmount] = React.useState<string>('900000');
  const [deliveryPeriod, setDeliveryPeriod] = React.useState('20 Weeks');
  const [placeOfDelivery, setPlaceOfDelivery] = React.useState(
    'CPCL Refinery Complex, Manali, Chennai - 600068'
  );

  // Step 2 State: Requirements
  const [requirements, setRequirements] = React.useState<RequirementDraft[]>(DEFAULT_REQUIREMENTS);

  // Step 3 State: Participating Bidders
  const [bidders, setBidders] = React.useState<QueuedBidder[]>(() =>
    SAMPLE_DEMO_BIDDERS.map((b, i) => ({ ...b, clientId: `bidder-${i}-${Date.now()}` }))
  );

  // Bidder form state
  const [newBidderName, setNewBidderName] = React.useState('');
  const [newBidderTrade, setNewBidderTrade] = React.useState('');
  const [newBidderPan, setNewBidderPan] = React.useState('');
  const [newBidderGstin, setNewBidderGstin] = React.useState('');
  const [newBidderUdyam, setNewBidderUdyam] = React.useState('');
  const [newBidderCin, setNewBidderCin] = React.useState('');
  const [newBidderAddress, setNewBidderAddress] = React.useState('');
  const [newBidderContactName, setNewBidderContactName] = React.useState('');
  const [newBidderContactEmail, setNewBidderContactEmail] = React.useState('');
  const [newBidderContactPhone, setNewBidderContactPhone] = React.useState('');

  // Step 4 State: Declaration
  const [gfrDeclaration, setGfrDeclaration] = React.useState(false);

  const totalWeight = React.useMemo(
    () => requirements.reduce((acc, r) => acc + (Number(r.weight) || 0), 0),
    [requirements]
  );

  // Add bidder to queue
  const handleAddBidder = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newBidderName.trim()) {
      toast({ title: 'Validation Notice', description: 'Legal Business Name is required.' });
      return;
    }
    const newEntry: QueuedBidder = {
      clientId: `bidder-${Date.now()}`,
      legal_name: newBidderName.trim(),
      trade_name: newBidderTrade.trim() || undefined,
      pan: newBidderPan.trim().toUpperCase() || undefined,
      gstin: newBidderGstin.trim().toUpperCase() || undefined,
      udyam: newBidderUdyam.trim() || undefined,
      cin: newBidderCin.trim().toUpperCase() || undefined,
      registered_address: newBidderAddress.trim() || undefined,
      contact_name: newBidderContactName.trim() || undefined,
      contact_email: newBidderContactEmail.trim() || undefined,
      contact_phone: newBidderContactPhone.trim() || undefined,
    };

    setBidders((prev) => [...prev, newEntry]);
    setNewBidderName('');
    setNewBidderTrade('');
    setNewBidderPan('');
    setNewBidderGstin('');
    setNewBidderUdyam('');
    setNewBidderCin('');
    setNewBidderAddress('');
    setNewBidderContactName('');
    setNewBidderContactEmail('');
    setNewBidderContactPhone('');

    toast({
      title: 'Bidder Added',
      description: `${newEntry.legal_name} added to tender participant queue.`,
    });
  };

  const handleRemoveBidder = (clientId: string) => {
    setBidders((prev) => prev.filter((b) => b.clientId !== clientId));
  };

  const handleLoadSampleBidders = () => {
    const fresh = SAMPLE_DEMO_BIDDERS.map((b, i) => ({
      ...b,
      clientId: `sample-${i}-${Date.now()}`,
    }));
    setBidders(fresh);
    toast({
      title: 'Sample Bidders Queued',
      description: 'Loaded 3 pre-configured demonstration enterprise bidders.',
    });
  };

  // AI Suggest Requirements
  const handleSuggestRequirements = async () => {
    if (!description.trim()) {
      toast({
        title: 'Input Required',
        description: 'Provide a tender scope description first to derive requirement rules.',
      });
      return;
    }
    setAiGenerating(true);
    try {
      const res = await tendersApi.suggestRequirements({
        title,
        description,
        department,
      });
      const suggested = res.requirements || [];
      if (suggested.length > 0) {
        const mapped: RequirementDraft[] = suggested.map((s: SuggestedRequirement) => ({
          requirement_name: s.requirement_name,
          category: 'TECHNICAL',
          description: s.description || 'Verified according to technical specifications.',
          mandatory: s.mandatory,
          rule_type: 'CUSTOM_RULE',
          rule_config: {},
          threshold: s.threshold || null,
          verification_source: null,
          weight: s.weight || 10,
        }));
        setRequirements(mapped);
        toast({
          title: 'Requirements Synthesized',
          description: `${mapped.length} qualification rules derived from tender description.`,
        });
      }
    } catch (err) {
      toast({
        title: 'Advisory Engine Notice',
        description: 'Could not fetch external suggestions; keeping standard CPSE template.',
      });
    } finally {
      setAiGenerating(false);
    }
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
        bid_type: bidType,
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
          threshold: r.threshold,
          expected_value: r.expected_value,
          verification_source: r.verification_source,
          weight: Number(r.weight) || 5,
          policy_reference: r.policy_reference,
        })),
      };

      const createdTender = await tendersApi.create(req);
      const tenderId = createdTender.id;

      // 2. Register Queued Bidders for this Tender
      let registeredBiddersCount = 0;
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
          await bidsApi.create(bidPayload);
          registeredBiddersCount++;
        } catch (bidErr) {
          console.warn(`Could not register bidder ${b.legal_name}:`, bidErr);
        }
      }

      toast({
        title: 'Tender Package Published',
        description: `Tender #${createdTender.tender_number} published with ${registeredBiddersCount} participating bidder(s).`,
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
      <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-xs">
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <Link
              to="/app/tenders"
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-blue-800 hover:text-blue-950 transition-colors"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              <span>Return to Procurement Directory</span>
            </Link>
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs text-slate-500 font-semibold">TENDER CREATION WORKSPACE</span>
              <SystemLayerTag layer="RULE_ENGINE" size="sm" />
            </div>
          </div>

          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 border-t border-slate-100 pt-4">
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-slate-900 font-serif">
                Create Tender Package &amp; Register Bidders
              </h1>
              <p className="mt-0.5 text-xs text-slate-600">
                Define technical specifications, configure qualification criteria, and register participating enterprise bidders for automated compliance analysis.
              </p>
            </div>

            <div className="flex items-center gap-2">
              <span className="rounded bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-900 border border-blue-200">
                GFR 2017 &amp; GeM Protocol Compliant
              </span>
            </div>
          </div>
        </div>

        {/* 2. Four-Stage Process Stepper */}
        <div className="mt-6 border-t border-slate-100 pt-5">
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
                      ? 'border-blue-700 bg-blue-50/60 shadow-2xs'
                      : isPast
                      ? 'border-emerald-200 bg-emerald-50/30'
                      : 'border-slate-200 bg-slate-50/50 hover:bg-slate-100/60'
                  }`}
                >
                  <div
                    className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md font-mono text-xs font-bold ${
                      isActive
                        ? 'bg-blue-800 text-white'
                        : isPast
                        ? 'bg-emerald-600 text-white'
                        : 'bg-slate-200 text-slate-700'
                    }`}
                  >
                    {isPast ? <CheckCircle2 className="h-4 w-4" /> : `0${st.n}`}
                  </div>
                  <div className="min-w-0">
                    <p className={`text-xs font-bold leading-tight ${isActive ? 'text-blue-950' : 'text-slate-900'}`}>
                      {st.title}
                    </p>
                    <p className="truncate text-[11px] text-slate-500 mt-0.5">{st.desc}</p>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {errorMsg && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-xs text-red-900 flex items-center gap-2">
          <ShieldAlert className="h-4 w-4 text-red-600 shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* 3. STEP CONTENT */}

      {/* STEP 1: SPECIFICATIONS */}
      {currentStep === 1 && (
        <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-xs space-y-6">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <div>
              <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wide">
                Stage 1 — Tender Scope &amp; Procurement Identification
              </h2>
              <p className="text-xs text-slate-500">
                Establish the administrative credentials, monetary threshold, and timelines for this procurement.
              </p>
            </div>
            <span className="font-mono text-xs font-semibold text-slate-400">Step 1 of 4</span>
          </div>

          <div className="grid gap-5 md:grid-cols-2">
            <div>
              <label className="block text-xs font-semibold text-slate-800 mb-1">
                Tender Reference Number *
              </label>
              <Input
                value={tenderNumber}
                onChange={(e) => setTenderNumber(e.target.value)}
                placeholder="e.g. CPCL-2026-004"
                className="font-mono text-xs uppercase"
              />
              <p className="mt-1 text-[11px] text-slate-500">Unique statutory reference code under GeM/CPSE ledger.</p>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-800 mb-1">
                Procuring Organization *
              </label>
              <Input
                value={organization}
                onChange={(e) => setOrganization(e.target.value)}
                className="text-xs"
              />
            </div>

            <div className="md:col-span-2">
              <label className="block text-xs font-semibold text-slate-800 mb-1">
                Tender Package Title *
              </label>
              <Input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Brief formal title describing the procurement scope"
                className="text-xs font-medium"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-800 mb-1">
                Executing Department *
              </label>
              <Input
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
                className="text-xs"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-800 mb-1">
                Estimated Contract Value (INR) *
              </label>
              <div className="flex items-center gap-2">
                <Input
                  type="number"
                  value={estimatedValue}
                  onChange={(e) => setEstimatedValue(Number(e.target.value))}
                  className="text-xs font-mono"
                />
                <span className="shrink-0 rounded bg-slate-100 px-2.5 py-1 text-xs font-mono font-bold text-slate-800 border border-slate-200">
                  {formatINR(estimatedValue)}
                </span>
              </div>
            </div>

            <div className="md:col-span-2">
              <label className="block text-xs font-semibold text-slate-800 mb-1">
                Detailed Scope of Work &amp; Technical Specifications *
              </label>
              <Textarea
                rows={4}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Detail technical standards, delivery parameters, ISO/API codes, inspection checkpoints..."
                className="text-xs"
              />
              <p className="mt-1 text-[11px] text-slate-500">
                This scope is analyzed by the deterministic rule engine and AI assistant to synthesize compliance requirements.
              </p>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-800 mb-1">
                Tender Category
              </label>
              <Select
                value={tenderType}
                onChange={(e) => setTenderType(e.target.value as TenderType)}
                className="text-xs"
              >
                <option value="GOODS">Goods &amp; Equipment Supply</option>
                <option value="SERVICES">Consultancy &amp; Technical Services</option>
                <option value="WORKS">Works Contract &amp; Construction</option>
              </Select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-800 mb-1">
                Bidding System
              </label>
              <Select
                value={bidType}
                onChange={(e) => setBidType(e.target.value as BidType)}
                className="text-xs"
              >
                <option value="TWO_PACKET">Two-Packet System (Technical + Financial)</option>
                <option value="SINGLE_PACKET">Single-Packet System</option>
              </Select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-800 mb-1">
                Bid Submission Closing Date *
              </label>
              <Input
                type="date"
                value={closingDate}
                onChange={(e) => setClosingDate(e.target.value)}
                className="text-xs font-mono"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-800 mb-1">
                Earnest Money Deposit (EMD in INR)
              </label>
              <Input
                type="number"
                value={emdAmount}
                onChange={(e) => setEmdAmount(e.target.value)}
                placeholder="e.g. 1000000"
                className="text-xs font-mono"
              />
              <p className="mt-1 text-[11px] text-slate-500">Exemptions automatically apply for verified MSME / Startups.</p>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-800 mb-1">
                Delivery / Contract Duration
              </label>
              <Input
                value={deliveryPeriod}
                onChange={(e) => setDeliveryPeriod(e.target.value)}
                placeholder="e.g. 24 Weeks"
                className="text-xs"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-800 mb-1">
                Place of Delivery &amp; Inspection
              </label>
              <Input
                value={placeOfDelivery}
                onChange={(e) => setPlaceOfDelivery(e.target.value)}
                className="text-xs"
              />
            </div>
          </div>

          <div className="flex items-center justify-between border-t border-slate-100 pt-4">
            <span className="text-xs text-slate-500">All fields marked with * are required under CPSE procurement audit standards.</span>
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
        <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-xs space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-100 pb-3">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wide">
                  Stage 2 — Bidder Qualification &amp; Compliance Rules
                </h2>
                <SystemLayerTag layer="RULE_ENGINE" size="sm" />
              </div>
              <p className="text-xs text-slate-500">
                Configure deterministic evaluation rules. Weights must equal 100% for scored criteria.
              </p>
            </div>

            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                loading={aiGenerating}
                onClick={handleSuggestRequirements}
                className="h-8 text-xs font-medium border-blue-200 text-blue-900 bg-blue-50/50 hover:bg-blue-100"
              >
                <Sparkles className="mr-1.5 h-3.5 w-3.5 text-blue-600" />
                AI Suggest from Scope
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={addManualRequirement}
                className="h-8 text-xs font-medium border-slate-300 text-slate-700"
              >
                <Plus className="mr-1 h-3.5 w-3.5" />
                Add Custom Rule
              </Button>
            </div>
          </div>

          {/* Weight Counter Bar */}
          <div className="rounded-lg border border-slate-200 bg-slate-50/80 p-3 flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <Scale className="h-4 w-4 text-slate-600" />
              <span className="font-semibold text-slate-800">Total Scored Weight:</span>
              <span
                className={`font-mono font-bold text-sm ${
                  totalWeight === 100 ? 'text-emerald-700' : 'text-amber-700'
                }`}
              >
                {totalWeight}% / 100%
              </span>
            </div>
            {totalWeight === 100 ? (
              <span className="flex items-center gap-1 text-[11px] font-semibold text-emerald-700">
                <CheckCircle2 className="h-3.5 w-3.5" /> Perfectly Balanced
              </span>
            ) : (
              <span className="text-[11px] text-amber-700 font-medium">
                Adjust requirement weights so the total equals 100%.
              </span>
            )}
          </div>

          {/* Requirements Table */}
          <div className="overflow-x-auto rounded-lg border border-slate-200">
            <Table>
              <TableHeader>
                <tr className="border-b border-slate-200 bg-slate-50 text-[10.5px] font-bold text-slate-600 uppercase tracking-wider">
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
                  <TableRow key={idx} className="hover:bg-slate-50/50 text-xs">
                    <TableCell className="text-center font-mono text-slate-400 font-bold">
                      {idx + 1}
                    </TableCell>
                    <TableCell className="space-y-1">
                      <Input
                        value={r.requirement_name}
                        onChange={(e) => updateRequirement(idx, { requirement_name: e.target.value })}
                        placeholder="Requirement title"
                        className="text-xs font-semibold h-8"
                      />
                      <Input
                        value={r.description || ''}
                        onChange={(e) => updateRequirement(idx, { description: e.target.value })}
                        placeholder="Detailed verification criteria"
                        className="text-[11px] text-slate-500 h-7"
                      />
                    </TableCell>
                    <TableCell>
                      <Select
                        value={r.category}
                        onChange={(e) => updateRequirement(idx, { category: e.target.value as RequirementCategory })}
                        className="text-xs h-8"
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
                        className="text-xs font-mono h-8"
                      />
                    </TableCell>
                    <TableCell className="text-center">
                      <input
                        type="checkbox"
                        checked={r.mandatory}
                        onChange={(e) => updateRequirement(idx, { mandatory: e.target.checked })}
                        className="h-4 w-4 rounded border-slate-300 text-blue-800 focus:ring-blue-500"
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        type="number"
                        value={r.weight}
                        onChange={(e) => updateRequirement(idx, { weight: Number(e.target.value) })}
                        className="text-xs font-mono text-center h-8"
                        min={0}
                        max={100}
                      />
                    </TableCell>
                    <TableCell className="text-right">
                      <button
                        type="button"
                        onClick={() => removeRequirement(idx)}
                        className="text-slate-400 hover:text-rose-600 p-1"
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

          <div className="flex items-center justify-between border-t border-slate-100 pt-4">
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
              className="bg-blue-800 hover:bg-blue-900 text-white text-xs font-medium"
            >
              Continue to Register Participating Bidders
              <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      )}

      {/* STEP 3: PARTICIPATING BIDDERS REGISTRATION */}
      {currentStep === 3 && (
        <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-xs space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-100 pb-3">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wide">
                  Stage 3 — Register Participating Bidders for this Tender
                </h2>
                <Badge variant="outline" className="text-xs font-mono">
                  {bidders.length} Registered
                </Badge>
              </div>
              <p className="text-xs text-slate-500">
                Register participating vendors so the tender dossier immediately includes bidders ready for document ingestion and cross-checking.
              </p>
            </div>

            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleLoadSampleBidders}
              className="h-8 text-xs font-medium border-slate-300 text-slate-800 bg-slate-50 hover:bg-slate-100"
            >
              <Users className="mr-1.5 h-3.5 w-3.5 text-blue-700" />
              Load Demo Participating Bidders
            </Button>
          </div>

          {/* Quick Registration Form */}
          <form onSubmit={handleAddBidder} className="rounded-lg border border-blue-100 bg-blue-50/30 p-4 space-y-4">
            <div className="flex items-center justify-between border-b border-blue-200/60 pb-2">
              <span className="text-xs font-bold text-blue-950 uppercase tracking-wider">
                Add New Bidder to Tender Submission Queue
              </span>
              <span className="text-[11px] text-blue-800">All statutory registries (GST/PAN/Udyam/CIN) supported</span>
            </div>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <div className="lg:col-span-2">
                <label className="block text-xs font-semibold text-slate-800 mb-1">
                  Legal Enterprise / Company Name *
                </label>
                <Input
                  value={newBidderName}
                  onChange={(e) => setNewBidderName(e.target.value)}
                  placeholder="e.g. Apex Flow Systems Private Limited"
                  className="text-xs bg-white"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-800 mb-1">
                  Trade Name / Brand Alias
                </label>
                <Input
                  value={newBidderTrade}
                  onChange={(e) => setNewBidderTrade(e.target.value)}
                  placeholder="e.g. Apex Industrial Solutions"
                  className="text-xs bg-white"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-800 mb-1">
                  PAN (Permanent Account Number)
                </label>
                <Input
                  value={newBidderPan}
                  onChange={(e) => setNewBidderPan(e.target.value)}
                  placeholder="e.g. AAACA1234A"
                  maxLength={10}
                  className="text-xs font-mono uppercase bg-white"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-800 mb-1">
                  GSTIN (15-Digit GST Number)
                </label>
                <Input
                  value={newBidderGstin}
                  onChange={(e) => setNewBidderGstin(e.target.value)}
                  placeholder="e.g. 33AAACA1234A1Z5"
                  maxLength={15}
                  className="text-xs font-mono uppercase bg-white"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-800 mb-1">
                  Udyam Registration (MSME)
                </label>
                <Input
                  value={newBidderUdyam}
                  onChange={(e) => setNewBidderUdyam(e.target.value)}
                  placeholder="e.g. UDYAM-TN-02-0012345"
                  className="text-xs font-mono uppercase bg-white"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-800 mb-1">
                  Corporate Identification (CIN)
                </label>
                <Input
                  value={newBidderCin}
                  onChange={(e) => setNewBidderCin(e.target.value)}
                  placeholder="e.g. U29100TN2015PTC099887"
                  className="text-xs font-mono uppercase bg-white"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-800 mb-1">
                  Authorized Contact Person
                </label>
                <Input
                  value={newBidderContactName}
                  onChange={(e) => setNewBidderContactName(e.target.value)}
                  placeholder="e.g. R. Ramanathan, Director"
                  className="text-xs bg-white"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-800 mb-1">
                  Official Email Address
                </label>
                <Input
                  type="email"
                  value={newBidderContactEmail}
                  onChange={(e) => setNewBidderContactEmail(e.target.value)}
                  placeholder="contracts@company.com"
                  className="text-xs bg-white"
                />
              </div>

              <div className="sm:col-span-2 lg:col-span-2">
                <label className="block text-xs font-semibold text-slate-800 mb-1">
                  Registered Corporate Address
                </label>
                <Input
                  value={newBidderAddress}
                  onChange={(e) => setNewBidderAddress(e.target.value)}
                  placeholder="Registered address as per MCA/GSTN filing"
                  className="text-xs bg-white"
                />
              </div>

              <div className="flex items-end">
                <Button
                  type="submit"
                  size="sm"
                  className="w-full h-8 text-xs bg-blue-800 hover:bg-blue-900 text-white font-medium"
                >
                  <Plus className="mr-1.5 h-3.5 w-3.5" />
                  Add Bidder to Queue
                </Button>
              </div>
            </div>
          </form>

          {/* Registered Bidders Table */}
          <div className="space-y-2">
            <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
              Bidders Queued for Evaluation ({bidders.length})
            </h3>

            {bidders.length === 0 ? (
              <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-xs text-slate-500">
                <Users className="mx-auto h-8 w-8 text-slate-400 mb-2" />
                <p className="font-semibold text-slate-700">No Bidders Registered Yet</p>
                <p className="mt-1">Add participating bidders using the form above or click "Load Demo Participating Bidders".</p>
              </div>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-slate-200">
                <Table>
                  <TableHeader>
                    <tr className="border-b border-slate-200 bg-slate-50 text-[10.5px] font-bold text-slate-600 uppercase tracking-wider">
                      <TableHead>Bidder Enterprise</TableHead>
                      <TableHead>GSTIN / PAN</TableHead>
                      <TableHead>MSME / CIN</TableHead>
                      <TableHead>Contact Representative</TableHead>
                      <TableHead className="text-right">Action</TableHead>
                    </tr>
                  </TableHeader>
                  <TableBody>
                    {bidders.map((b) => (
                      <TableRow key={b.clientId} className="hover:bg-slate-50/50 text-xs">
                        <TableCell>
                          <p className="font-semibold text-slate-900">{b.legal_name}</p>
                          {b.trade_name && <p className="text-[11px] text-slate-500">{b.trade_name}</p>}
                        </TableCell>
                        <TableCell className="font-mono text-xs">
                          <div>GST: <span className="font-semibold text-slate-800">{b.gstin || '—'}</span></div>
                          <div>PAN: <span className="font-semibold text-slate-800">{b.pan || '—'}</span></div>
                        </TableCell>
                        <TableCell className="font-mono text-xs">
                          <div>UDYAM: <span className="text-slate-800">{b.udyam || '—'}</span></div>
                          <div>CIN: <span className="text-slate-800">{b.cin || '—'}</span></div>
                        </TableCell>
                        <TableCell className="text-xs">
                          <p className="font-medium text-slate-800">{b.contact_name || '—'}</p>
                          <p className="text-[11px] text-slate-500">{b.contact_email || '—'}</p>
                        </TableCell>
                        <TableCell className="text-right">
                          <button
                            type="button"
                            onClick={() => handleRemoveBidder(b.clientId)}
                            className="p-1 text-slate-400 hover:text-rose-600"
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

          <div className="flex items-center justify-between border-t border-slate-100 pt-4">
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

      {/* STEP 4: REVIEW & PUBLICATION */}
      {currentStep === 4 && (
        <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-xs space-y-6">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <div>
              <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wide">
                Stage 4 — Executive Summary, Statutory Review &amp; Publication
              </h2>
              <p className="text-xs text-slate-500">
                Verify package details before final publication and hash-chain registration.
              </p>
            </div>
            <SystemLayerTag layer="AUDIT_CHAIN" size="sm" />
          </div>

          {/* Package Overview Summary */}
          <div className="grid gap-4 md:grid-cols-3">
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 space-y-2">
              <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Package Identification</span>
              <p className="text-sm font-bold text-slate-900 font-mono">{tenderNumber}</p>
              <p className="text-xs font-semibold text-slate-800">{title}</p>
              <p className="text-[11px] text-slate-600">{organization}</p>
              <p className="text-[11px] text-slate-500">Dept: {department}</p>
            </div>

            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 space-y-2">
              <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Commercial Terms</span>
              <p className="text-lg font-bold text-slate-900 font-mono">{formatINR(estimatedValue)}</p>
              <p className="text-xs text-slate-700">Type: <strong className="font-semibold">{tenderType}</strong> • System: <strong className="font-semibold">{bidType}</strong></p>
              <p className="text-xs text-slate-700">EMD: <strong className="font-mono">{emdAmount ? formatINR(Number(emdAmount)) : 'Exempted'}</strong></p>
              <p className="text-[11px] text-slate-500">Closes: {closingDate}</p>
            </div>

            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 space-y-2">
              <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Rules &amp; Participants</span>
              <div className="flex items-center justify-between text-xs">
                <span>Evaluation Rules:</span>
                <strong className="font-mono text-slate-900">{requirements.length} Criteria</strong>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span>Total Weight:</span>
                <strong className="font-mono text-emerald-800">{totalWeight}%</strong>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span>Queued Bidders:</span>
                <strong className="font-mono text-blue-900">{bidders.length} Vendors</strong>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span>Audit Anchor:</span>
                <strong className="text-emerald-700">SHA-256 Ledger</strong>
              </div>
            </div>
          </div>

          {/* Registered Bidders Pill Summary */}
          <div className="rounded-lg border border-slate-200 p-4 bg-white space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                Registered Bidders ({bidders.length})
              </h3>
              <button
                type="button"
                onClick={() => setCurrentStep(3)}
                className="text-xs font-semibold text-blue-700 hover:underline"
              >
                Modify Bidders
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {bidders.map((b) => (
                <div
                  key={b.clientId}
                  className="rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-800 flex items-center gap-2"
                >
                  <Building2 className="h-3.5 w-3.5 text-slate-500" />
                  <span>{b.legal_name}</span>
                  {b.gstin && <span className="font-mono text-[10px] text-slate-500">({b.gstin})</span>}
                </div>
              ))}
            </div>
          </div>

          {/* Statutory Declaration Checkbox */}
          <div className="rounded-lg border border-blue-200 bg-blue-50/50 p-4 space-y-2">
            <div className="flex items-start gap-3">
              <input
                id="gfr-declaration"
                type="checkbox"
                checked={gfrDeclaration}
                onChange={(e) => setGfrDeclaration(e.target.checked)}
                className="mt-0.5 h-4 w-4 rounded border-blue-300 text-blue-800 focus:ring-blue-500"
              />
              <label htmlFor="gfr-declaration" className="text-xs leading-relaxed text-slate-800">
                <strong className="font-semibold text-slate-900">
                  Statutory Declaration under General Financial Rules (GFR 2017) &amp; CPSE Guidelines:
                </strong>{' '}
                I confirm that this tender specification complies with open procurement transparency standards, non-restrictive technical specifications, and fair evaluation rules. The registered participating bidders will be evaluated deterministically with full immutable audit logging.
              </label>
            </div>
          </div>

          <div className="flex items-center justify-between border-t border-slate-100 pt-4">
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
              disabled={!gfrDeclaration}
              onClick={handlePublishTender}
              className="bg-emerald-700 hover:bg-emerald-800 text-white text-xs font-semibold px-6 shadow-sm"
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
