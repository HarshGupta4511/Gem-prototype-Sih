import { useEffect, useState } from 'react';
import { bidsApi } from '../../lib/api';
import { cn } from '../../lib/utils';

type Size = 'sm' | 'md' | 'lg';

const SIZE_CLASSES: Record<Size, string> = {
  sm: 'h-7 w-7 text-[10px]',
  md: 'h-10 w-10 text-xs',
  lg: 'h-14 w-14 text-base',
};

function initialsOf(legalName: string): string {
  const words = legalName.split(/\s+/).filter((w) => /[a-zA-Z]/.test(w[0] ?? ''));
  return (words.slice(0, 2).map((w) => w[0]).join('') || 'CO').toUpperCase();
}

interface BidderLogoProps {
  /** Direct bidder id (preferred). */
  bidderId?: number;
  /** Fallback: resolved to a bidder id via the bid detail endpoint. */
  bidId?: number;
  legalName: string;
  size?: Size;
  className?: string;
}

/**
 * Display-only bidder logo. Fetches the image as an authenticated blob
 * (the endpoint requires an officer token, so <img> can't hit it directly)
 * and falls back to an initials avatar when no logo exists.
 * The logo never affects compliance, verification, risk or scoring.
 */
export function BidderLogo({ bidderId, bidId, legalName, size = 'md', className }: BidderLogoProps) {
  const [resolvedId, setResolvedId] = useState<number | null>(bidderId ?? null);
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    if (bidderId != null) {
      setResolvedId(bidderId);
      return;
    }
    if (bidId == null) return;
    let alive = true;
    bidsApi
      .get(bidId)
      .then((detail) => {
        if (alive) setResolvedId(detail.bidder.id);
      })
      .catch(() => {
        /* stay on the initials fallback */
      });
    return () => {
      alive = false;
    };
  }, [bidderId, bidId]);

  useEffect(() => {
    if (resolvedId == null) return;
    let alive = true;
    let objectUrl: string | null = null;
    bidsApi
      .getBidderLogoBlob(resolvedId)
      .then((blob) => {
        if (!alive) return;
        objectUrl = URL.createObjectURL(blob);
        setSrc(objectUrl);
      })
      .catch(() => {
        if (alive) setSrc(null);
      });
    return () => {
      alive = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [resolvedId]);

  const base = 'shrink-0 overflow-hidden rounded-lg ring-1 ring-slate-200 dark:ring-slate-700 bg-slate-100 dark:bg-slate-800 flex items-center justify-center';

  if (src) {
    return (
      <img
        src={src}
        alt={`${legalName} logo`}
        className={cn(base, 'object-cover', SIZE_CLASSES[size], className)}
      />
    );
  }
  return (
    <div
      className={cn(base, SIZE_CLASSES[size], className)}
      aria-label={`${legalName} (no logo)`}
      title={legalName}
    >
      <span className="font-bold text-slate-500 dark:text-slate-400 select-none">
        {initialsOf(legalName)}
      </span>
    </div>
  );
}
