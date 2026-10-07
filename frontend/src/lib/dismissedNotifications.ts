import * as React from 'react';

// Dismissal state for the officer's notification work queue.
//
// The notifications themselves always come from the backend (dashboard work
// queue); this module only persists which items the officer has dismissed,
// in localStorage. Dismissed items stay dismissed across refreshes — they are
// not a separate notification system, just a dismissal preference layered on
// the real backend-driven queue.

export interface WorkQueueItemLike {
  category: string;
  bid_id?: number | null;
  tender_id?: number | null;
}

export function notificationKey(item: WorkQueueItemLike): string {
  return `${item.category}#${item.bid_id ?? ''}#${item.tender_id ?? ''}`;
}

const STORAGE_KEY = 'bidwise-dismissed-notifications';

function readStored(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    const arr = JSON.parse(raw);
    return new Set(Array.isArray(arr) ? arr.filter((x) => typeof x === 'string') : []);
  } catch {
    return new Set();
  }
}

let dismissed: Set<string> = readStored();
const listeners = new Set<() => void>();

function persist() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...dismissed]));
  } catch {
    // storage unavailable — dismissal just won't survive reload
  }
  listeners.forEach((l) => l());
}

function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

function getSnapshot(): Set<string> {
  return dismissed;
}

export function dismissNotification(key: string): void {
  if (!dismissed.has(key)) {
    dismissed = new Set(dismissed).add(key);
    persist();
  }
}

export function dismissAllNotifications(keys: string[]): void {
  const next = new Set(dismissed);
  keys.forEach((k) => next.add(k));
  dismissed = next;
  persist();
}

export function useDismissedNotifications(): Set<string> {
  return React.useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}
