/**
 * Typed access to the authoritative requirement catalogue
 * (`requirement-catalogue.json`).
 *
 * The JSON file is the single source of truth for requirement templates used
 * by BOTH the Create Tender wizard (pages/CreateTender.tsx) and the legacy
 * TenderWizard dialog (components/tenders/TenderWizard.tsx). Both UIs build
 * their default requirement drafts from `defaultTemplate()` below, so they
 * can no longer silently produce different rule configurations for
 * equivalent requirements.
 *
 * Every entry's `rule_config` uses the exact schema consumed by the backend
 * deterministic rules engine. `backend/tests/test_requirement_catalogue.py`
 * validates the JSON against the engine — edit the JSON, not the UI.
 */
import catalogueJson from './requirement-catalogue.json';
import type {
  AdapterSource,
  RequirementCategory,
  RequirementDraft,
  RuleType,
  TenderType,
} from '../types';

export type Applicability = 'REQUIRED' | 'CONDITIONAL' | 'OPTIONAL';

export interface CatalogueEntry {
  key: string;
  requirement_name: string;
  category: RequirementCategory;
  description: string;
  applicability: Applicability;
  applicability_note: string;
  applicable_tender_types: TenderType[];
  default_mandatory: boolean;
  rule_type: RuleType;
  rule_config: Record<string, unknown>;
  threshold: string;
  expected_value?: string | null;
  verification_source?: AdapterSource | null;
  default_weight: number;
  policy_reference?: string | null;
  expected_document_types: string[];
  in_default_template: boolean;
  demo_note?: string;
}

interface CatalogueFile {
  meta: {
    name: string;
    version: number;
    description: string;
    weight_note: string;
    applicability: Record<Applicability, string>;
  };
  entries: CatalogueEntry[];
}

const catalogue = catalogueJson as unknown as CatalogueFile;

export function getCatalogueMeta() {
  return catalogue.meta;
}

export function getCatalogue(): CatalogueEntry[] {
  return catalogue.entries;
}

export function getCatalogueEntry(key: string): CatalogueEntry | undefined {
  return catalogue.entries.find((e) => e.key === key);
}

/**
 * The demo default template: catalogue entries flagged `in_default_template`,
 * mapped to the `RequirementDraft` shape the wizard edits and POSTs.
 * Default weights total exactly 100 (enforced by the backend contract test).
 */
export function defaultTemplate(): RequirementDraft[] {
  return catalogue.entries
    .filter((e) => e.in_default_template)
    .map((e) => ({
      requirement_name: e.requirement_name,
      category: e.category,
      description: e.description,
      mandatory: e.default_mandatory,
      rule_type: e.rule_type,
      rule_config: { ...e.rule_config },
      threshold: e.threshold,
      expected_value: e.expected_value ?? undefined,
      verification_source: e.verification_source ?? null,
      weight: e.default_weight,
      policy_reference: e.policy_reference ?? undefined,
    }));
}

export function defaultTemplateWeightTotal(): number {
  return catalogue.entries
    .filter((e) => e.in_default_template)
    .reduce((sum, e) => sum + e.default_weight, 0);
}

/** Document types the evidence pipeline is expected to produce for a requirement. */
export function expectedDocTypesFor(entry: CatalogueEntry): string[] {
  return entry.expected_document_types ?? [];
}

/**
 * Whether a catalogue entry applies to a tender type. Entries whose
 * `applicable_tender_types` omit the tender type are shown as inapplicable
 * (the officer can still add them explicitly).
 */
export function isApplicableTo(entry: CatalogueEntry, tenderType: TenderType | undefined): boolean {
  if (!tenderType) return true;
  return entry.applicable_tender_types.includes(tenderType);
}

const KNOWN_RULE_TYPES: RuleType[] = [
  'EXISTENCE', 'DOCUMENT_REQUIRED', 'EQUALITY', 'MATCH', 'MINIMUM', 'MAXIMUM',
  'DATE_VALIDITY', 'DATE_RANGE', 'CONTAINS', 'BOOLEAN', 'REGISTRATION_STATUS',
  'IDENTITY_MATCH', 'CUSTOM_RULE',
];

/** Keys every rule type's rule_config must carry (mirrors rules_engine.py). */
const REQUIRED_CONFIG_KEYS: Record<RuleType, string[]> = {
  EXISTENCE: ['value_source'],
  DOCUMENT_REQUIRED: ['document_types'],
  EQUALITY: ['value_source', 'expected'],
  MATCH: ['value_source', 'pattern'],
  MINIMUM: ['value_source', 'operator', 'value'],
  MAXIMUM: ['value_source', 'operator', 'value'],
  DATE_VALIDITY: ['value_source'],
  DATE_RANGE: ['value_source'],
  CONTAINS: ['value_source', 'substring'],
  BOOLEAN: ['value_source', 'expected'],
  REGISTRATION_STATUS: ['source', 'identifier_field', 'require_status'],
  IDENTITY_MATCH: [],
  CUSTOM_RULE: ['expression'],
};

const VALUE_SOURCE_PREFIXES = ['extracted.', 'bidder.', 'verification.'];

/**
 * Structural validation of a requirement's rule configuration against the
 * deterministic engine's contract. Returns human-readable problems (empty =
 * valid). Used to block publication of misconfigured mandatory requirements
 * and mirrored by `backend/tests/test_requirement_catalogue.py`.
 */
export function validateRuleConfig(
  ruleType: RuleType,
  ruleConfig: Record<string, unknown> | undefined | null,
): string[] {
  const problems: string[] = [];
  if (!KNOWN_RULE_TYPES.includes(ruleType)) {
    problems.push(`Unknown rule type '${ruleType}'.`);
    return problems;
  }
  const cfg = ruleConfig ?? {};
  for (const key of REQUIRED_CONFIG_KEYS[ruleType]) {
    if (cfg[key] === undefined || cfg[key] === null || cfg[key] === '') {
      problems.push(`Rule type ${ruleType} requires rule_config.${key}.`);
    }
  }
  const vs = cfg['value_source'];
  if (typeof vs === 'string' && vs) {
    if (!VALUE_SOURCE_PREFIXES.some((p) => vs.startsWith(p))) {
      problems.push(
        `value_source '${vs}' must start with one of ${VALUE_SOURCE_PREFIXES.join(', ')}.`,
      );
    }
  }
  const dt = cfg['document_types'];
  if (dt !== undefined && (!Array.isArray(dt) || dt.length === 0)) {
    problems.push('document_types must be a non-empty array.');
  }
  if (ruleType === 'CUSTOM_RULE' && typeof cfg['expression'] === 'string') {
    const expr = cfg['expression'] as string;
    if (/\b(import|exec|eval|open|__)\b/.test(expr)) {
      problems.push('Custom rule expression contains disallowed constructs.');
    }
  }
  return problems;
}

/** Full-draft validation used by the Stage 4 publish gate. */
export function validateRequirementDraft(d: RequirementDraft): string[] {
  const problems: string[] = [];
  if (!d.requirement_name?.trim()) problems.push('Requirement name is required.');
  if (typeof d.weight !== 'number' || Number.isNaN(d.weight) || d.weight < 0) {
    problems.push(`'${d.requirement_name || 'Unnamed'}': weight must be a non-negative number.`);
  }
  if (d.mandatory) {
    const cfgProblems = validateRuleConfig(d.rule_type, d.rule_config);
    for (const p of cfgProblems) problems.push(`'${d.requirement_name || 'Unnamed'}': ${p}`);
  }
  return problems;
}

/**
 * Expected evidence document types for a requirement list, mirroring the
 * backend demo-evidence builder (`build_dossier_sections` in
 * backend/app/seed/demo_bidder_profiles.py). Display-only: the backend
 * builder is authoritative at seeding time.
 *
 * `demoProfileKey === 'vertex'` reproduces the missing-evidence scenario
 * (only turnover + experience sections are generated).
 */
export function expectedDocsForRequirements(
  requirements: RequirementDraft[],
  demoProfileKey?: string,
): string[] {
  const docs = new Set<string>();
  const isVertex = demoProfileKey === 'vertex';
  const REG_DOC: Record<string, string> = {
    GSTN: 'GST_CERTIFICATE',
    PAN_IT: 'PAN_CERTIFICATE',
    UDYAM: 'UDYAM_CERTIFICATE',
    EPFO: 'EPFO_CERTIFICATE',
    ESIC: 'ESIC_CERTIFICATE',
    MCA21: 'MCA21_CERTIFICATE',
  };
  const FIELD_DOC: Record<string, string> = {
    'extracted.turnover_inr': 'BALANCE_SHEET',
    'extracted.experience_years': 'EXPERIENCE_CERTIFICATE',
    'extracted.past_performance_pct': 'PAST_PERFORMANCE_CERTIFICATE',
    'extracted.local_content_pct': 'MII_DECLARATION',
    'extracted.emd_amount_inr': 'EMD_RECEIPT',
    'extracted.itr_financial_year': 'ITR_DOCUMENT',
    'extracted.iso_valid_until': 'ISO_9001_CERTIFICATE',
  };
  for (const r of requirements) {
    const cfg = (r.rule_config ?? {}) as Record<string, unknown>;
    if (isVertex) {
      const vs = cfg['value_source'];
      if (typeof vs === 'string' && FIELD_DOC[vs] &&
          (vs === 'extracted.turnover_inr' || vs === 'extracted.experience_years')) {
        docs.add(FIELD_DOC[vs]);
      }
      continue;
    }
    if (r.rule_type === 'REGISTRATION_STATUS') {
      const doc = REG_DOC[String(cfg['source'] ?? '')];
      if (doc) docs.add(doc);
    } else if (r.rule_type === 'MINIMUM' || r.rule_type === 'EXISTENCE') {
      const doc = FIELD_DOC[String(cfg['value_source'] ?? '')];
      if (doc) docs.add(doc);
    } else if (r.rule_type === 'BOOLEAN' &&
               cfg['value_source'] === 'extracted.oem_authorization_valid') {
      docs.add('OEM_AUTHORIZATION');
    } else if (r.rule_type === 'DOCUMENT_REQUIRED') {
      const types = cfg['document_types'];
      if (Array.isArray(types)) for (const t of types) docs.add(String(t));
    }
  }
  // The demo evidence builder attaches a non-debarment declaration for every
  // profile except the missing-evidence one.
  if (!isVertex) docs.add('NON_DEBARMENT_DECLARATION');
  return [...docs];
}
