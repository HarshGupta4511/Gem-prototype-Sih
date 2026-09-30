import type { NavigateFunction } from 'react-router-dom';

/**
 * Contextual return destination for the document viewer.
 *
 * The viewer must return the user to wherever the document was opened from —
 * never to a hardcoded global route. Callers pass this context when opening
 * the viewer; the viewer resolves it with safe fallbacks for deep links.
 */
export interface ViewerReturnContext {
  /** Router path to navigate back to. */
  path: string;
  /** Back-button label, e.g. "Back to Bid Documents". */
  label: string;
  /** Optional router state to hand back (e.g. { tab: 'documents' }). */
  state?: Record<string, unknown>;
}

type LocationState = { from?: Partial<ViewerReturnContext> } | null | undefined;

/** Open the document viewer, remembering where to return afterwards. */
export function openDocumentViewer(
  navigate: NavigateFunction,
  docId: number,
  returnTo: ViewerReturnContext,
): void {
  navigate(`/app/documents/${docId}`, { state: { from: returnTo } });
}

/**
 * Resolve the viewer's back target:
 * 1. explicit context passed by the opener (preferred),
 * 2. the document's own bid dossier,
 * 3. the Document Verification Lab (only for context-less deep links).
 */
export function resolveViewerReturn(
  locationState: unknown,
  docBidId?: number | null,
): ViewerReturnContext {
  const from = (locationState as LocationState)?.from;
  if (from?.path) {
    return { path: from.path, label: from.label ?? 'Back', state: from.state };
  }
  if (docBidId) {
    return { path: `/app/bids/${docBidId}`, label: 'Back to Bid' };
  }
  return { path: '/app/documents', label: 'Back to Document Verification Lab' };
}
