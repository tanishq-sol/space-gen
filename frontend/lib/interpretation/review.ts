import type {
  DetectionInterpretation,
  MaskRegion,
  OpeningInterpretation,
  RoomInterpretation,
  WallInterpretation,
} from '@/lib/contracts';
import { computeObbForItemNode } from '@/lib/splat/splatMasking';
import { LOW_CONFIDENCE, TRUSTED_STATUSES, type ReviewKind, type ReviewMeta, type ReviewStatus } from './reviewTypes';

type Nodes = Record<string, any>;

export interface ReviewEntry {
  nodeId: string;
  kind: ReviewKind;
  label: string;
  sourceId: string;
  confidence: number;
  status: ReviewStatus;
  provenance: 'auto' | 'user';
  lowConfidence: boolean;
}

export type ConfidenceTier = 'low' | 'medium' | 'high' | 'verified' | 'rejected';

export const TIER_COLORS: Record<ConfidenceTier, string> = {
  low: '#ef4444',
  medium: '#f59e0b',
  high: '#22c55e',
  verified: '#38bdf8',
  rejected: '#6b7280',
};

export function reviewMetaOf(node: any): ReviewMeta | null {
  const review = node?.metadata?.review;
  return review && typeof review === 'object' ? (review as ReviewMeta) : null;
}

export function confidenceTier(entry: Pick<ReviewEntry, 'confidence' | 'status'>): ConfidenceTier {
  if (entry.status === 'rejected') return 'rejected';
  if (TRUSTED_STATUSES.has(entry.status)) return 'verified';
  if (entry.confidence < 0.6) return 'low';
  if (entry.confidence < LOW_CONFIDENCE) return 'medium';
  return 'high';
}

function entryFor(node: any, nodes: Nodes): ReviewEntry | null {
  const meta = reviewMetaOf(node);
  if (!meta) return null;
  let label = node.name || meta.sourceId;
  if (meta.kind === 'wall') label = node.name || 'Wall';
  if (meta.kind === 'opening') {
    const wall = nodes[node.wallId ?? node.parentId];
    label = `${node.name || 'Opening'}${wall?.name ? ` on ${wall.name}` : ''}`;
  }
  return {
    nodeId: node.id,
    kind: meta.kind,
    label,
    sourceId: meta.sourceId,
    confidence: meta.confidence,
    status: meta.status,
    provenance: meta.provenance,
    lowConfidence: meta.status === 'auto' && meta.confidence < LOW_CONFIDENCE,
  };
}

const STATUS_ORDER: Record<ReviewStatus, number> = { auto: 0, corrected: 1, verified: 2, rejected: 3 };

/** Needs-review items first (lowest confidence first), then reviewed ones, rejected last. */
export function listReviewEntries(nodes: Nodes): ReviewEntry[] {
  return Object.values(nodes)
    .map((node) => entryFor(node, nodes))
    .filter((e): e is ReviewEntry => !!e)
    .sort(
      (a, b) =>
        Number(b.lowConfidence) - Number(a.lowConfidence) ||
        STATUS_ORDER[a.status] - STATUS_ORDER[b.status] ||
        a.confidence - b.confidence ||
        a.label.localeCompare(b.label),
    );
}

export interface PlaceableElements {
  walls: ReviewEntry[];
  openings: ReviewEntry[];
  detections: ReviewEntry[];
  /** Elements that exist but are not verified/corrected, so placement must not rely on them. */
  unverified: ReviewEntry[];
}

/** Elements placement may rely on: only verified or corrected ones; rejected ones are ignored entirely. */
export function getPlaceableElements(nodes: Nodes): PlaceableElements {
  const result: PlaceableElements = { walls: [], openings: [], detections: [], unverified: [] };
  for (const entry of listReviewEntries(nodes)) {
    if (entry.status === 'rejected') continue;
    if (!TRUSTED_STATUSES.has(entry.status)) {
      result.unverified.push(entry);
      continue;
    }
    if (entry.kind === 'wall') result.walls.push(entry);
    else if (entry.kind === 'opening') result.openings.push(entry);
    else result.detections.push(entry);
  }
  return result;
}

/** Message to show before placement when it would rely on unreviewed elements; null when all are trusted. */
export function getPlacementWarning(nodes: Nodes): string | null {
  const { unverified } = getPlaceableElements(nodes);
  if (unverified.length === 0) return null;
  const noun = unverified.length === 1 ? 'element is' : 'elements are';
  return `${unverified.length} detected ${noun} still unverified. Placement uses only verified or corrected elements; review them first or continue knowing they are ignored.`;
}

function toVec3([x, z]: [number, number]): [number, number, number] {
  return [x, 0, z];
}

/** Rebuilds the saved RoomInterpretation from the Pascal scene, which is the source of truth. */
export function deriveInterpretation(nodes: Nodes, base: RoomInterpretation): RoomInterpretation {
  const all = Object.values(nodes);
  const slab = all.find((n) => n?.type === 'slab' && n.id === 'slab_room') ?? all.find((n) => n?.type === 'slab');
  const walls: WallInterpretation[] = [];
  const openings: OpeningInterpretation[] = [];
  const detections: DetectionInterpretation[] = [];
  const masks: MaskRegion[] = all.find((n) => n?.type === 'scan')?.metadata?.maskRegions ?? [];

  for (const node of all) {
    const meta = reviewMetaOf(node);
    if (!meta) continue;
    const provenance = meta.provenance;
    if (node.type === 'wall') {
      walls.push({
        id: meta.sourceId,
        start: toVec3(node.start),
        end: toVec3(node.end),
        height: node.height,
        thickness: node.thickness,
        confidence: meta.confidence,
        provenance,
      });
    } else if (node.type === 'door' || node.type === 'window') {
      const wall = nodes[node.wallId ?? node.parentId];
      const wallMeta = reviewMetaOf(wall);
      if (!wallMeta) continue;
      const sill = Math.max(0, (node.position?.[1] ?? 0) - node.height / 2);
      openings.push({
        id: meta.sourceId,
        wallId: wallMeta.sourceId,
        kind: meta.openingKind ?? node.type,
        offset: Math.max(0, node.position?.[0] ?? 0),
        width: node.width,
        height: node.height,
        sill,
        confidence: meta.confidence,
        provenance,
      });
    } else if (node.type === 'item') {
      const mask = masks.find((m) => m.itemId === node.id || m.id === node.metadata?.maskRegionId);
      detections.push({
        id: meta.sourceId,
        category: meta.category ?? node.asset?.category ?? 'item',
        label: node.name,
        obb: computeObbForItemNode(node),
        confidence: meta.confidence,
        maskRegionId: mask?.id ?? node.metadata?.maskRegionId ?? null,
        status: meta.status,
        provenance,
      });
    }
  }

  return {
    ...base,
    outline: slab?.polygon ? slab.polygon.map((p: [number, number]) => [p[0], p[1]] as [number, number]) : base.outline,
    walls,
    openings,
    detections,
  };
}

/** Drops interpretation-derived walls/items that placement must not rely on (unverified or rejected). */
export function filterToPlaceable<T extends { walls: Array<{ id: string }>; items: Array<{ id: string }> }>(summary: T, nodes: Nodes): T {
  const trusted = (id: string) => {
    const meta = reviewMetaOf(nodes[id]);
    return !meta || TRUSTED_STATUSES.has(meta.status);
  };
  return { ...summary, walls: summary.walls.filter((w) => trusted(w.id)), items: summary.items.filter((i) => trusted(i.id)) };
}
