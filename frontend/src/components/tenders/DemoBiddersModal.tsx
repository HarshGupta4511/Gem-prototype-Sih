import * as React from 'react';
import { Building2, FlaskConical } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '../ui/dialog';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';

/** Fictional demo bidder profile shown in the Stage 3 demo modal. */
export interface DemoBidderProfile {
  /** Backend evidence-profile key: 'apex' | 'vertex' | 'nova' | 'primetech'. */
  profile_key: 'apex' | 'vertex' | 'nova' | 'primetech';
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
  scenario: string;
  scenario_tone: 'success' | 'warning' | 'mismatch' | 'critical';
  scenario_description: string;
}

/**
 * Preconfigured fictional bidder profiles for jury/demo presentations.
 * All identifiers are masked and fictional — intended only for demonstration.
 */
export const DEMO_BIDDER_PROFILES: DemoBidderProfile[] = [
  {
    profile_key: 'apex',
    legal_name: 'Apex Flow Systems Pvt. Ltd.',
    trade_name: 'Apex Industrial Solutions',
    pan: 'AAXCA0001A',
    gstin: '27XXXXXXX001Z5',
    udyam: 'UDYAM-MH-XX-XXXXXXX',
    cin: 'U29100MH2015PTCXXXXXX',
    registered_address: 'Plot 42, MIDC Industrial Area, Bhosari, Pune - 411026',
    contact_name: 'R. Ramanathan, Director',
    contact_email: 'contracts@apexflow-demo.in',
    contact_phone: '+91 98400 10001',
    scenario: 'Mostly Compliant',
    scenario_tone: 'success',
    scenario_description:
      'Complete dossier with valid GST, PAN and Udyam records. Intended demo arc: mostly-pass compliance with a minor review item on a non-mandatory requirement.',
  },
  {
    profile_key: 'vertex',
    legal_name: 'Vertex Industrial Solutions Pvt. Ltd.',
    trade_name: 'Vertex Engineering',
    pan: 'BAXCB0002B',
    gstin: '27XXXXXXX002Z5',
    udyam: 'UDYAM-MH-XX-XXXXXXX',
    cin: 'U28110MH2016PTCXXXXXX',
    registered_address: '14/B, TTC Industrial Area, MIDC, Navi Mumbai - 400705',
    contact_name: 'S. Iyer, Partner',
    contact_email: 'tenders@vertex-demo.in',
    contact_phone: '+91 98410 20002',
    scenario: 'Missing / Incomplete Evidence',
    scenario_tone: 'warning',
    scenario_description:
      'Key evidence documents absent from the dossier. Intended demo arc: missing evidence surfaces as MISSING / REVIEW_REQUIRED with a reduced compliance score.',
  },
  {
    profile_key: 'nova',
    legal_name: 'Nova Engineering Works Pvt. Ltd.',
    trade_name: 'Nova Works',
    pan: 'CAXCC0003C',
    gstin: '27XXXXXXX003Z5',
    udyam: 'UDYAM-MH-XX-XXXXXXX',
    cin: 'U29120MH2017PTCXXXXXX',
    registered_address: 'Gat 154, Chakan Industrial Area Phase II, Pune - 410501',
    contact_name: 'N. Kulkarni, Proprietor',
    contact_email: 'bids@nova-demo.in',
    contact_phone: '+91 98200 30003',
    scenario: 'Verification Mismatch',
    scenario_tone: 'mismatch',
    scenario_description:
      'Portal registry records carry a conflicting legal name. Intended demo arc: cross-verification raises MISMATCH flags during verification.',
  },
  {
    profile_key: 'primetech',
    legal_name: 'PrimeTech Industrial Systems Pvt. Ltd.',
    trade_name: 'PrimeTech Systems',
    pan: 'DAXCD0004D',
    gstin: '27XXXXXXX004Z5',
    udyam: 'UDYAM-MH-XX-XXXXXXX',
    cin: 'U29200MH2014PTCXXXXXX',
    registered_address: 'Plot 88, MIDC Waluj, Aurangabad - 431136',
    contact_name: 'P. Deshmukh, Director',
    contact_email: 'contact@primetech-demo.in',
    contact_phone: '+91 98400 40004',
    scenario: 'High Risk / Verification Issue',
    scenario_tone: 'critical',
    scenario_description:
      'Adverse registry record (blacklisted). Intended demo arc: critical risk assessment and a not-recommended outcome, independent of the compliance score.',
  },
];

/** Normalizes a bidder legal name for duplicate comparison. */
export function normalizeBidderName(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]/g, '');
}

const SCENARIO_STYLES: Record<DemoBidderProfile['scenario_tone'], string> = {
  success: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  warning: 'bg-amber-50 text-amber-800 border-amber-200',
  mismatch: 'bg-orange-50 text-orange-800 border-orange-200',
  critical: 'bg-red-50 text-red-800 border-red-200',
};

interface DemoBiddersModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Normalized legal names already present in the tender bidder queue. */
  existingNames: string[];
  /** Called with the selected profiles when the officer confirms. */
  onLoad: (selected: DemoBidderProfile[]) => void;
}

export default function DemoBiddersModal({
  open,
  onOpenChange,
  existingNames,
  onLoad,
}: DemoBiddersModalProps) {
  const [selected, setSelected] = React.useState<number[]>([]);

  // Reset selection each time the modal opens.
  React.useEffect(() => {
    if (open) setSelected([]);
  }, [open ]);

  const isAlreadyLoaded = (p: DemoBidderProfile) =>
    existingNames.includes(normalizeBidderName(p.legal_name));

  const selectableCount = DEMO_BIDDER_PROFILES.filter((p) => !isAlreadyLoaded(p)).length;
  const allSelectableSelected =
    selectableCount > 0 &&
    DEMO_BIDDER_PROFILES.filter((p) => !isAlreadyLoaded(p)).every((p) =>
      selected.includes(DEMO_BIDDER_PROFILES.indexOf(p))
    );

  const toggle = (idx: number) =>
    setSelected((prev) => (prev.includes(idx) ? prev.filter((i) => i !== idx) : [...prev, idx]));

  const toggleSelectAll = () => {
    if (allSelectableSelected) {
      setSelected([]);
    } else {
      setSelected(
        DEMO_BIDDER_PROFILES.map((p, i) => ({ p, i }))
          .filter(({ p }) => !isAlreadyLoaded(p))
          .map(({ i }) => i)
      );
    }
  };

  const handleLoad = () => {
    onLoad(selected.map((i) => DEMO_BIDDER_PROFILES[i]));
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl bg-white max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-md bg-blue-800 text-white shrink-0">
              <Building2 className="h-4 w-4" />
            </div>
            <div>
              <DialogTitle className="text-base font-bold text-slate-900">
                Load Demo Participating Bidders
              </DialogTitle>
              <DialogDescription className="text-xs text-slate-500 mt-0.5">
                Use preconfigured fictional bidder profiles to quickly demonstrate the bid
                verification and compliance workflow.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        {/* Demo data banner */}
        <div className="flex items-start gap-2.5 rounded-md border border-amber-200 bg-amber-50 px-3.5 py-2.5">
          <FlaskConical className="h-4 w-4 text-amber-700 mt-0.5 shrink-0" />
          <div>
            <p className="text-xs font-bold tracking-wide text-amber-900">DEMO DATA</p>
            <p className="text-xs text-amber-800 mt-0.5">
              These bidder profiles are fictional and intended only for demonstration/testing.
            </p>
          </div>
        </div>

        {/* Bidder selection list */}
        <div className="space-y-2">
          {DEMO_BIDDER_PROFILES.map((profile, idx) => {
            const alreadyLoaded = isAlreadyLoaded(profile);
            const checked = selected.includes(idx);
            return (
              <label
                key={profile.legal_name}
                className={`flex items-start gap-3 rounded-lg border p-3.5 transition-colors ${
                  alreadyLoaded
                    ? 'border-slate-200 bg-slate-50 opacity-70 cursor-not-allowed'
                    : checked
                      ? 'border-blue-300 bg-blue-50/50 cursor-pointer'
                      : 'border-slate-200 bg-white hover:border-slate-300 cursor-pointer'
                }`}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={alreadyLoaded}
                  onChange={() => toggle(idx)}
                  className="mt-1 h-4 w-4 shrink-0 accent-blue-800 cursor-pointer disabled:cursor-not-allowed"
                  aria-label={`Select ${profile.legal_name}`}
                />
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-slate-100 text-slate-600">
                  <Building2 className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-slate-900">
                      {String(idx + 1).padStart(2, '0')} — {profile.legal_name}
                    </span>
                    <Badge
                      variant="outline"
                      className={`text-[10.5px] font-semibold ${SCENARIO_STYLES[profile.scenario_tone]}`}
                    >
                      {profile.scenario}
                    </Badge>
                    {alreadyLoaded && (
                      <Badge variant="outline" className="text-[10.5px] text-slate-500 border-slate-300">
                        In queue
                      </Badge>
                    )}
                  </div>
                  <p className="mt-1 font-mono text-[11px] text-slate-600">
                    GSTIN: {profile.gstin} <span className="text-slate-300 mx-1">|</span> Udyam:{' '}
                    {profile.udyam}
                  </p>
                  <p className="mt-1 text-xs text-slate-500 leading-relaxed">
                    {profile.scenario_description}
                  </p>
                </div>
              </label>
            );
          })}
        </div>

        {selectableCount === 0 && (
          <p className="text-xs text-slate-500 bg-slate-50 border border-slate-200 rounded-md px-3 py-2">
            All demo bidders are already in the tender queue. No duplicates will be created.
          </p>
        )}

        <DialogFooter className="flex-col sm:flex-row gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={toggleSelectAll}
            disabled={selectableCount === 0}
            className="text-xs text-blue-800 hover:text-blue-950 sm:mr-auto"
          >
            {allSelectableSelected ? 'Clear Selection' : 'Select All Demo Bidders'}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => onOpenChange(false)}
            className="text-xs"
          >
            Cancel
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={handleLoad}
            disabled={selected.length === 0}
            className="bg-blue-800 hover:bg-blue-900 text-white text-xs font-medium"
          >
            Load Selected Bidders{selected.length > 0 ? ` (${selected.length})` : ''}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
