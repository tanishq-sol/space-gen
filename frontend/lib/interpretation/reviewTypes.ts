import type { OpeningKind } from '@/lib/contracts';

export type ReviewKind = 'wall' | 'opening' | 'detection';
export type ReviewStatus = 'auto' | 'verified' | 'corrected' | 'rejected';

/** Stored on every Pascal node that came from a RoomInterpretation (`node.metadata.review`). */
export interface ReviewMeta {
  sourceId: string;
  kind: ReviewKind;
  confidence: number;
  status: ReviewStatus;
  provenance: 'auto' | 'user';
  openingKind?: OpeningKind;
  category?: string;
  sill?: number;
}

/** Interpretation items below this confidence are listed first and flagged for review. */
export const LOW_CONFIDENCE = 0.9;

export const TRUSTED_STATUSES: ReadonlySet<ReviewStatus> = new Set(['verified', 'corrected']);

export function nodeIdFor(kind: 'wall' | 'door' | 'window' | 'item', sourceId: string): string {
  return `${kind}_${sourceId}`;
}
