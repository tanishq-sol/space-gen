import { useScene, type AnyNode, type AnyNodeId } from '@pascal-app/core';
import type {
  DetectionInterpretation,
  DetectionStatus,
  MaskRegion,
  Matrix4,
  OpeningInterpretation,
  OpeningKind,
  Point2D,
  Provenance,
  RoomInterpretation,
  ScanAsset,
  ShellSurfaceTexture,
  WallInterpretation,
} from '@/lib/contracts';
import { IDENTITY_SCAN_TO_SCENE } from './scanAlignment';
import { asNode, asNodeData, nodeViews, type NodeView, type NodeViewMap } from './nodes';

/**
 * RoomInterpretation <-> Pascal node conversion.
 *
 * Walls, slab, zone and openings become Pascal nodes carrying their review state in
 * `metadata.interpretation`. Detections stay scan annotations (not furniture), so they live
 * on the ScanNode as `metadata.detections` next to the MaskRegions they link to. Everything is
 * written with one `applyNodeChanges`, so the conversion is a single undo step.
 */

export const INTERPRETATION_META_KEY = 'interpretation';

export type InterpretedKind = 'outline' | 'zone' | 'wall' | 'opening';

export interface InterpretationMeta {
  kind: InterpretedKind;
  sourceId: string;
  confidence: number;
  provenance: Provenance;
  status: DetectionStatus;
  /** Opening only: door | window | opening. */
  openingKind?: OpeningKind;
  /** Outline only: room-level fields needed to rebuild the RoomInterpretation. */
  floor?: RoomInterpretation['floor'];
  ceilingHeight?: number;
  roomProvenance?: Provenance;
}

type NodeMap = NodeViewMap;
type CreateOp = { node: AnyNode; parentId?: AnyNodeId };

export interface ConvertOptions {
  levelId?: string;
  /** Existing scan node to annotate with detections; one is created from `scan` otherwise. */
  scanNodeId?: string;
  scan?: Pick<ScanAsset, 'url' | 'format' | 'scanToScene'> & Partial<Pick<ScanAsset, 'scaleSource'>>;
  maskRegions?: MaskRegion[];
}

export interface ConversionPlan {
  creates: CreateOp[];
  updates: Array<{ id: AnyNodeId; data: Record<string, unknown> }>;
  levelId: string;
  slabId: string;
  zoneId: string;
  wallIds: Record<string, string>;
  openingIds: Record<string, string>;
  scanNodeId: string;
}

export function prefixedId(prefix: string, id: string): string {
  return id.startsWith(`${prefix}_`) ? id : `${prefix}_${id}`;
}

type WithMetadata = { metadata?: object } | null | undefined;

export function getInterpretationMeta(node: WithMetadata): InterpretationMeta | null {
  const meta = (node?.metadata as Record<string, unknown> | undefined)?.[INTERPRETATION_META_KEY];
  return meta && typeof meta === 'object' ? (meta as InterpretationMeta) : null;
}

export function withInterpretationMeta(node: WithMetadata, patch: Partial<InterpretationMeta>) {
  const current = getInterpretationMeta(node);
  return {
    ...(node?.metadata || {}),
    [INTERPRETATION_META_KEY]: { ...current, ...patch },
  };
}

export function wallLength(start: Point2D, end: Point2D): number {
  return Math.hypot(end[0] - start[0], end[1] - start[1]);
}

/**
 * Pascal hosts openings at their centre: [u along wall, v centre height, 0].
 * `offset` follows the contract: distance from wall start to the opening's centre.
 */
export function openingPosition(offset: number, height: number, sill: number): [number, number, number] {
  return [offset, sill + height / 2, 0];
}

/** Keeps an opening of `width` centred at `offset` fully on a wall of `wallLen`. */
export function clampOpeningCenter(offset: number, width: number, wallLen: number): number {
  return Math.min(Math.max(offset, width / 2), Math.max(width / 2, wallLen - width / 2));
}

function openingNode(op: OpeningInterpretation, id: string, wallNodeId: string, wallLen: number, meta: InterpretationMeta) {
  const width = Math.min(op.width, wallLen);
  const offset = clampOpeningCenter(op.offset, width, wallLen);
  const isWindow = op.kind === 'window';
  return asNode({
    id,
    type: isWindow ? 'window' : 'door',
    name: isWindow ? 'Window' : op.kind === 'opening' ? 'Opening' : 'Door',
    wallId: wallNodeId,
    position: openingPosition(offset, op.height, op.sill),
    rotation: [0, 0, 0],
    width,
    height: op.height,
    ...(op.kind === 'opening' ? { openingKind: 'opening' } : {}),
    metadata: { [INTERPRETATION_META_KEY]: meta },
  });
}

/** Builds the Pascal node payloads for an interpretation without touching the store. */
export function planInterpretationNodes(
  interpretation: RoomInterpretation,
  nodes: NodeMap,
  options: ConvertOptions = {},
): ConversionPlan {
  const creates: CreateOp[] = [];
  const updates: ConversionPlan['updates'] = [];
  const existingLevel = options.levelId || Object.values(nodes).find((n) => n?.type === 'level')?.id;
  const levelId = existingLevel || 'level_scan';

  if (!existingLevel) {
    creates.push({ node: asNode({ id: 'site_scan', type: 'site', name: 'Site' }) });
    creates.push({ node: asNode({ id: 'building_scan', type: 'building', name: 'Building' }), parentId: 'site_scan' as AnyNodeId });
    creates.push({
      node: asNode({ id: levelId, type: 'level', name: 'Scanned level', elevation: 0, height: interpretation.ceilingHeight }),
      parentId: 'building_scan' as AnyNodeId,
    });
  }

  const outlineStatus: DetectionStatus = interpretation.outlineStatus || 'auto';
  const outlineConfidence = interpretation.walls.length
    ? Math.min(...interpretation.walls.map((w) => w.confidence))
    : 0;
  const slabId = 'slab_scan_outline';
  const existingScan = options.scanNodeId
    ? nodes[options.scanNodeId]
    : Object.values(nodes).find((n) => n?.type === 'scan');
  // GPU-baked floor texture in Pascal's world-planar slab UVs (ADR 002 §4); walls are a follow-up.
  const floorTexture = (existingScan?.metadata?.shellTextures as ShellSurfaceTexture[] | undefined)?.find((s) => s.target === 'slab');
  creates.push({
    node: asNode({
      id: slabId,
      type: 'slab',
      name: 'Scanned floor',
      thickness: 0.05,
      ...(floorTexture ? { material: { texture: { url: floorTexture.textureAsset, repeat: floorTexture.repeat } } } : {}),
      polygon: interpretation.outline.map((p) => [p[0], p[1]]),
      metadata: {
        [INTERPRETATION_META_KEY]: {
          kind: 'outline',
          sourceId: 'outline',
          confidence: outlineConfidence,
          provenance: interpretation.provenance,
          roomProvenance: interpretation.provenance,
          status: outlineStatus,
          floor: interpretation.floor,
          ceilingHeight: interpretation.ceilingHeight,
        } satisfies InterpretationMeta,
      },
    }),
    parentId: levelId as AnyNodeId,
  });

  const zoneId = 'zone_scan_room';
  creates.push({
    node: asNode({
      id: zoneId,
      type: 'zone',
      name: 'Scanned room',
      polygon: interpretation.outline.map((p) => [p[0], p[1]]),
      ceilingHeight: interpretation.ceilingHeight,
      metadata: {
        [INTERPRETATION_META_KEY]: {
          kind: 'zone',
          sourceId: 'outline',
          confidence: outlineConfidence,
          provenance: interpretation.provenance,
          status: outlineStatus,
        } satisfies InterpretationMeta,
      },
    }),
    parentId: levelId as AnyNodeId,
  });

  const wallIds: Record<string, string> = {};
  const wallLengths: Record<string, number> = {};
  for (const wall of interpretation.walls) {
    const id = prefixedId('wall', wall.id);
    const start: Point2D = [wall.start[0], wall.start[2]];
    const end: Point2D = [wall.end[0], wall.end[2]];
    wallIds[wall.id] = id;
    wallLengths[wall.id] = wallLength(start, end);
    creates.push({
      node: asNode({
        id,
        type: 'wall',
        name: `Wall ${wall.id.replace(/^wall_/, '')}`,
        start,
        end,
        height: wall.height,
        thickness: wall.thickness,
        visible: wall.status !== 'rejected',
        metadata: {
          [INTERPRETATION_META_KEY]: {
            kind: 'wall',
            sourceId: wall.id,
            confidence: wall.confidence,
            provenance: wall.provenance,
            status: wall.status || 'auto',
          } satisfies InterpretationMeta,
        },
      }),
      parentId: levelId as AnyNodeId,
    });
  }

  const openingIds: Record<string, string> = {};
  for (const op of interpretation.openings) {
    const wallNodeId = wallIds[op.wallId];
    if (!wallNodeId) continue;
    const id = prefixedId(op.kind === 'window' ? 'window' : 'door', op.id);
    openingIds[op.id] = id;
    const node = openingNode(op, id, wallNodeId, wallLengths[op.wallId], {
      kind: 'opening',
      sourceId: op.id,
      confidence: op.confidence,
      provenance: op.provenance,
      status: op.status || 'auto',
      openingKind: op.kind,
    });
    if (op.status === 'rejected') node.visible = false;
    creates.push({ node, parentId: wallNodeId as AnyNodeId });
  }

  const scanNodeId = existingScan?.id || 'scan_room';
  const detections = interpretation.detections.map((d) => ({ ...d }));
  if (existingScan) {
    const currentMasks: MaskRegion[] = existingScan.metadata?.maskRegions || [];
    updates.push({
      id: scanNodeId as AnyNodeId,
      data: {
        // A root scan beside the new site would be dropped on load (Pascal keeps only site roots).
        // shortcut: a level created in this same change can't be a reparent target (updates apply first).
        ...(existingLevel && !existingScan.parentId ? { parentId: levelId } : {}),
        metadata: {
          ...(existingScan.metadata || {}),
          detections,
          maskRegions: currentMasks.length ? currentMasks : options.maskRegions || [],
        },
      },
    });
  } else {
    const url = options.scan?.url || '';
    creates.push({
      node: asNode({
        id: scanNodeId,
        type: 'scan',
        name: 'Room scan',
        url,
        visible: true,
        opacity: 100,
        position: [0, 0, 0],
        rotation: [0, 0, 0],
        scale: 1,
        // Spark owns splat rendering; keep Pascal's glTF scan loader off (see scanNodes.ts).
        layers: { model: false },
        metadata: {
          format: options.scan?.format || 'sog',
          scanToScene: [...((options.scan?.scanToScene as Matrix4) || IDENTITY_SCAN_TO_SCENE)],
          maskRegions: options.maskRegions || [],
          detections,
          ...(options.scan?.scaleSource ? { scaleSource: options.scan.scaleSource } : {}),
        },
      }),
      parentId: levelId as AnyNodeId,
    });
  }

  return { creates, updates, levelId, slabId, zoneId, wallIds, openingIds, scanNodeId };
}

/** True once an interpretation has been converted into the current scene. */
export function hasInterpretationNodes(nodes: NodeMap): boolean {
  return Object.values(nodes).some((n) => getInterpretationMeta(n)?.kind === 'outline');
}

/** Converts a RoomInterpretation into Pascal nodes as one undoable scene change. */
export function applyInterpretationToScene(interpretation: RoomInterpretation, options: ConvertOptions = {}): ConversionPlan {
  const scene = useScene.getState();
  const nodes = nodeViews(scene.nodes);
  if (hasInterpretationNodes(nodes)) throw new Error('The scan interpretation is already in the scene.');
  const plan = planInterpretationNodes(interpretation, nodes, options);
  scene.applyNodeChanges({
    create: plan.creates,
    update: plan.updates.length ? plan.updates.map((u) => ({ id: u.id, data: asNodeData(u.data) })) : undefined,
  });
  return plan;
}

function round(value: number): number {
  return Math.round(value * 1e6) / 1e6;
}

/** Rebuilds the RoomInterpretation contract from Pascal nodes, including user corrections. */
export function deriveInterpretationFromScene(nodes: NodeMap, base?: RoomInterpretation): RoomInterpretation | null {
  const all = Object.values(nodes).filter((n): n is NodeView => Boolean(n));
  const outlineNode = all.find((n) => getInterpretationMeta(n)?.kind === 'outline');
  if (!outlineNode) return null;
  const outlineMeta = getInterpretationMeta(outlineNode)!;

  const walls: WallInterpretation[] = [];
  const openings: OpeningInterpretation[] = [];
  let anyUser = outlineMeta.provenance === 'user';

  for (const node of all) {
    const meta = getInterpretationMeta(node);
    if (!meta) continue;
    if (meta.provenance === 'user') anyUser = true;
    if (meta.kind === 'wall' && node.type === 'wall') {
      const height = node.height ?? outlineMeta.ceilingHeight ?? 2.5;
      walls.push({
        id: meta.sourceId,
        start: [round(node.start[0]), 0, round(node.start[1])],
        end: [round(node.end[0]), 0, round(node.end[1])],
        height,
        thickness: node.thickness ?? 0.2,
        confidence: meta.confidence,
        provenance: meta.provenance,
        status: meta.status,
      });
    }
  }

  for (const node of all) {
    const meta = getInterpretationMeta(node);
    if (meta?.kind !== 'opening') continue;
    const host = nodes[node.wallId || node.parentId || ''];
    const hostMeta = getInterpretationMeta(host);
    if (!host || !hostMeta) continue;
    const width = node.width ?? 0.9;
    const height = node.height ?? 2.1;
    openings.push({
      id: meta.sourceId,
      wallId: hostMeta.sourceId,
      kind: meta.openingKind || (node.type === 'window' ? 'window' : 'door'),
      offset: round(Math.max(0, node.position?.[0] ?? width / 2)),
      width,
      height,
      sill: round(Math.max(0, (node.position?.[1] ?? height / 2) - height / 2)),
      confidence: meta.confidence,
      provenance: meta.provenance,
      status: meta.status,
    });
  }

  const scan = all.find((n) => n.type === 'scan' && Array.isArray(n.metadata?.detections));
  const detections: DetectionInterpretation[] = (scan?.metadata?.detections || []).map((d: DetectionInterpretation) => ({ ...d }));
  if (detections.some((d) => d.provenance === 'user')) anyUser = true;

  return {
    provenance: anyUser ? 'user' : outlineMeta.roomProvenance || base?.provenance || 'auto',
    floor: outlineMeta.floor || base?.floor || { normal: [0, 1, 0], constant: 0, provenance: 'auto' },
    ceilingHeight: outlineMeta.ceilingHeight || base?.ceilingHeight || 2.5,
    outline: (outlineNode.polygon || []).map((p: Point2D) => [round(p[0]), round(p[1])] as Point2D),
    outlineStatus: outlineMeta.status,
    walls,
    openings,
    detections,
  };
}
