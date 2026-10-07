/**
 * Human-readable presentation for compliance values.
 * Presentation only — the underlying data is never mutated.
 */

/** 124000000 → "₹12.4 Crore", 100000000 → "₹10 Crore", 450000 → "₹4.5 Lakh" */
function inrWords(n: number): string {
  if (n >= 1e7) {
    const c = n / 1e7;
    return `₹${Number.isInteger(c) ? c.toFixed(0) : c.toFixed(1)} Crore`;
  }
  if (n >= 1e5) {
    const l = n / 1e5;
    return `₹${Number.isInteger(l) ? l.toFixed(0) : l.toFixed(1)} Lakh`;
  }
  return `₹${n.toLocaleString('en-IN')}`;
}

/**
 * Raw evidence value → officer-readable finding.
 * Examples: "124000000" → "₹12.4 Crore", "58" (+local-content field) → "58% local content",
 * "ACTIVE" → "Active (mock check)", null/None → "Not Available".
 */
export function displayActualValue(
  raw: string | null | undefined,
  fieldHint = ''
): string {
  if (raw == null) return 'Not Available';
  const v = String(raw).trim();
  if (v === '' || v.toLowerCase() === 'none' || v.toLowerCase() === 'null') {
    return 'Not Available';
  }
  const upper = v.toUpperCase();
  if (upper === 'ACTIVE') return 'Active (mock check)';
  if (upper === 'INACTIVE') return 'Inactive';
  if (upper === 'VERIFIED') return 'Verified';
  if (upper === 'MISSING') return 'Evidence Not Found';
  if (upper === 'MISMATCH') return 'Verification Mismatch';
  if (upper === 'NOT_FOUND' || upper === 'NOT FOUND') return 'Not Found';
  if (/^-?\d+(\.\d+)?$/.test(v)) {
    const n = Number(v);
    const hint = fieldHint.toLowerCase();
    if (/(local.?content|percent|_pct|percentage)/.test(hint)) {
      return `${Number.isInteger(n) ? n.toFixed(0) : n}% local content`;
    }
    if (/(year|experience|month|day)/.test(hint)) {
      return `${n} ${/year|experience/.test(hint) ? 'years' : /month/.test(hint) ? 'months' : 'days'}`;
    }
    if (/(turnover|amount|inr|value|price|_rs|emd|capital)/.test(hint) || n >= 1e5) {
      return inrWords(n);
    }
    return v;
  }
  return v;
}

/** Tender threshold → display text. Never a bare "—" for a genuinely missing threshold. */
export function displayThreshold(threshold: string | null | undefined): string {
  const t = (threshold ?? '').trim();
  if (t === '' || t === '—') return 'No specific threshold';
  return t;
}

/** Statutory source code → readable label without mangling acronyms (GSTN stays GSTN). */
export function displaySource(source: string | null | undefined): string {
  if (!source) return '—';
  const s = source.trim();
  if (/^[A-Z0-9][A-Z0-9/._-]{1,}$/.test(s) && s === s.toUpperCase()) return s;
  return s
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(' ');
}
