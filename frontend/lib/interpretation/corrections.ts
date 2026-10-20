import { DoorNode, WindowNode, useScene, WallNode, type AnyNodeId } from '@pascal-app/core';
import type { MaskRegion, OrientedBoundingBox } from '@/lib/contracts';
import { computeObbForItemNode } from '@/lib/splat/splatMasking';
import { reviewMetaOf } from './review';
import { nodeIdFor, type ReviewMeta, type ReviewStatus } from './reviewTypes';

type Nodes = Record<string, any>;
type Point2 = [number, number];
type Update = { id: AnyNodeId; data: any };

const EPS = 1e-3;
const nodes = (): Nodes => useScene.getState().nodes as Nodes;
const scanNode = () => Object.values(nodes()).find((n) => n?.type === 'scan');

function metaPatch(node: any, patch: Partial<ReviewMeta>): Record<string, any> {
  const meta = reviewMetaOf(node);
  if (!meta) throw new Error(`Node ${node?.id} is not an interpretation element.`);
  return { ...(node.metadata || {}), review: { ...meta, ...patch } };
}

/** User edits always become provenance=user, status=corrected. */
const CORRECTED: Partial<ReviewMeta> = { provenance: 'user', status: 'corrected' };

function element(id: string, type?: string): any {
  const node = nodes()[id];
  if (!node || (type && node.type !== type) || !reviewMetaOf(node)) throw new Error(`Interpretation element not found: ${id}`);
  return node;
}

function maskUpdate(item: any, patch: (mask: MaskRegion) => MaskRegion): Update[] {
  const scan = scanNode();
  const masks: MaskRegion[] = scan?.metadata?.maskRegions ?? [];
  if (!scan || !masks.some((m) => m.itemId === item.id)) return [];
  return [{
    id: scan.id,
    data: { metadata: { ...scan.metadata, maskRegions: masks.map((m) => (m.itemId === item.id ? patch(m) : m)) } },
  }];
}

function apply(updates: Update[], extra: { create?: any[]; delete?: AnyNodeId[] } = {}) {
  useScene.getState().applyNodeChanges({ update: updates, create: extra.create ?? [], delete: extra.delete ?? [] } as any);
}

/** Marks an element as confirmed by the user without changing its geometry. */
export function verifyElement(nodeId: string): void {
  const node = element(nodeId);
  const status: ReviewStatus = reviewMetaOf(node)!.status === 'corrected' ? 'corrected' : 'verified';
  apply([{ id: nodeId as AnyNodeId, data: { metadata: metaPatch(node, { status }) } }]);
}

/** Rejects a detection: the item is hidden and its mask disabled so the original splat shows through. */
export function rejectDetection(nodeId: string): void {
  const item = element(nodeId, 'item');
  apply([
    { id: nodeId as AnyNodeId, data: { visible: false, metadata: metaPatch(item, { status: 'rejected', provenance: 'user' }) } },
    ...maskUpdate(item, (m) => ({ ...m, enabled: false })),
  ]);
}

/** Restores a rejected detection as corrected. */
export function restoreDetection(nodeId: string): void {
  const item = element(nodeId, 'item');
  apply([
    { id: nodeId as AnyNodeId, data: { visible: true, metadata: metaPatch(item, CORRECTED) } },
    ...maskUpdate(item, (m) => ({ ...m, enabled: true })),
  ]);
}

export function relabelDetection(nodeId: string, label: string, category?: string): void {
  const item = element(nodeId, 'item');
  const nextCategory = category?.trim() || reviewMetaOf(item)!.category;
  apply([{
    id: nodeId as AnyNodeId,
    data: {
      name: label,
      asset: { ...item.asset, name: label, category: nextCategory ?? item.asset?.category },
      metadata: metaPatch(item, { ...CORRECTED, category: nextCategory }),
    },
  }]);
}

/** Sets a detection's oriented box (world frame) and keeps the linked mask in sync. */
export function setDetectionBox(nodeId: string, patch: Partial<OrientedBoundingBox>): void {
  const item = element(nodeId, 'item');
  const current = computeObbForItemNode(item);
  const obb: OrientedBoundingBox = {
    center: patch.center ?? current.center,
    size: (patch.size ?? current.size).map((v) => Math.max(0.01, v)) as OrientedBoundingBox['size'],
    yaw: patch.yaw ?? current.yaw,
  };
  apply([
    {
      id: nodeId as AnyNodeId,
      data: {
        position: [obb.center[0], obb.center[1] - obb.size[1] / 2, obb.center[2]],
        rotation: [0, obb.yaw, 0],
        scale: [1, 1, 1],
        asset: { ...item.asset, dimensions: obb.size },
        metadata: metaPatch(item, CORRECTED),
      },
    },
    ...maskUpdate(item, (m) => ({ ...m, obb })),
  ]);
}

/** Records a gizmo transform of a detection item: node, linked mask and review state in one undo step. */
export function applyDetectionPose(
  nodeId: string,
  pose: { position: [number, number, number]; rotation: [number, number, number]; scale: [number, number, number] },
): void {
  const item = element(nodeId, 'item');
  const next = { ...item, ...pose };
  const obb = computeObbForItemNode(next);
  apply([
    { id: nodeId as AnyNodeId, data: { ...pose, metadata: metaPatch(item, CORRECTED) } },
    ...maskUpdate(item, (m) => ({ ...m, obb })),
  ]);
}

function wallLength(wall: any): number {
  return Math.hypot(wall.end[0] - wall.start[0], wall.end[1] - wall.start[1]);
}

function openingsOf(wall: any): any[] {
  return Object.values(nodes()).filter((n) => (n?.type === 'door' || n?.type === 'window') && (n.parentId === wall.id || n.wallId === wall.id));
}

/** Moves a wall's endpoints ([x, z]); openings keep their offset, clamped to the new length. */
export function moveWall(nodeId: string, start: Point2, end: Point2): void {
  const wall = element(nodeId, 'wall');
  const length = Math.hypot(end[0] - start[0], end[1] - start[1]);
  if (length < 0.1) throw new Error('A wall must be at least 0.1 m long.');
  const updates: Update[] = [{ id: nodeId as AnyNodeId, data: { start, end, metadata: metaPatch(wall, CORRECTED) } }];
  for (const opening of openingsOf(wall)) {
    const half = opening.width / 2;
    const x = Math.min(Math.max(opening.position[0], half), Math.max(half, length - half));
    if (Math.abs(x - opening.position[0]) > EPS) {
      updates.push({ id: opening.id, data: { position: [x, opening.position[1], opening.position[2]] } });
    }
  }
  apply(updates);
}

/** Splits a wall at `distance` metres from its start; openings past the split move to the new wall. */
export function splitWall(nodeId: string, distance?: number): string {
  const wall = element(nodeId, 'wall');
  const length = wallLength(wall);
  const d = distance ?? length / 2;
  if (d < 0.1 || d > length - 0.1) throw new Error('Split point must be at least 0.1 m from either end.');
  const t = d / length;
  const mid: Point2 = [wall.start[0] + (wall.end[0] - wall.start[0]) * t, wall.start[1] + (wall.end[1] - wall.start[1]) * t];
  const meta = reviewMetaOf(wall)!;
  let n = 1;
  while (nodes()[nodeIdFor('wall', `${meta.sourceId}_split${n}`)]) n++;
  const sourceId = `${meta.sourceId}_split${n}`;
  const newId = nodeIdFor('wall', sourceId);
  const updates: Update[] = [{ id: nodeId as AnyNodeId, data: { end: mid, metadata: metaPatch(wall, CORRECTED) } }];
  const moved: string[] = [];
  for (const opening of openingsOf(wall)) {
    if (opening.position[0] > d) {
      moved.push(opening.id);
      updates.push({
        id: opening.id,
        data: { parentId: newId, wallId: newId, position: [opening.position[0] - d, opening.position[1], opening.position[2]] },
      });
    }
  }
  // The new wall does not exist yet when the reparenting updates run, so it carries its children itself.
  const created = {
    ...WallNode.parse({ id: newId, name: `${wall.name || 'Wall'} (split)`, start: mid, end: wall.end, height: wall.height, thickness: wall.thickness, children: moved }),
    metadata: { review: { ...meta, ...CORRECTED, sourceId } },
  };
  apply(updates, { create: [{ node: created, parentId: wall.parentId }] });
  return newId;
}

/** Deletes a wall together with its openings. */
export function deleteWall(nodeId: string): void {
  const wall = element(nodeId, 'wall');
  apply([], { delete: [nodeId as AnyNodeId, ...openingsOf(wall).map((o) => o.id)] });
}

export interface OpeningSpec {
  kind: 'door' | 'window' | 'opening';
  offset: number;
  width: number;
  height: number;
  sill: number;
}

/** Adds a user-drawn opening (provenance=user, status=corrected) to a wall. */
export function addOpening(wallNodeId: string, spec: OpeningSpec): string {
  const wall = element(wallNodeId, 'wall');
  const type = spec.kind === 'window' ? 'window' : 'door';
  let n = 1;
  while (nodes()[nodeIdFor(type, `user_${n}`)]) n++;
  const sourceId = `user_${n}`;
  const id = nodeIdFor(type, sourceId);
  const node = {
    object: 'node', type, id, name: spec.kind === 'window' ? 'Window' : spec.kind === 'door' ? 'Door' : 'Opening',
    visible: true, parentId: wallNodeId, wallId: wallNodeId, children: [],
    position: [spec.offset, spec.sill + spec.height / 2, 0], rotation: [0, 0, 0],
    width: spec.width, height: spec.height,
    metadata: { review: { sourceId, kind: 'opening', confidence: 1, openingKind: spec.kind, sill: spec.sill, ...CORRECTED } },
  };
  const parsed = (type === 'window' ? WindowNode : DoorNode).parse(node as any);
  apply([], { create: [{ node: { ...parsed, metadata: node.metadata }, parentId: wall.id }] });
  return id;
}


export function removeOpening(nodeId: string): void {
  const node = element(nodeId);
  if (node.type !== 'door' && node.type !== 'window') throw new Error(`${nodeId} is not an opening.`);
  apply([], { delete: [nodeId as AnyNodeId] });
}

export function resizeOpening(nodeId: string, patch: Partial<Pick<OpeningSpec, 'offset' | 'width' | 'height' | 'sill'>>): void {
  const node = element(nodeId);
  if (node.type !== 'door' && node.type !== 'window') throw new Error(`${nodeId} is not an opening.`);
  const width = Math.max(0.1, patch.width ?? node.width);
  const height = Math.max(0.1, patch.height ?? node.height);
  const sill = Math.max(0, patch.sill ?? Math.max(0, node.position[1] - node.height / 2));
  const offset = Math.max(0, patch.offset ?? node.position[0]);
  apply([{
    id: nodeId as AnyNodeId,
    data: { width, height, position: [offset, sill + height / 2, node.position[2]], metadata: metaPatch(node, { ...CORRECTED, sill }) },
  }]);
}

/** Moves outline vertex `index`; the slab, room zone and any wall endpoint on that vertex follow. */
export function moveOutlineVertex(index: number, point: Point2): void {
  const all = Object.values(nodes());
  const slab = all.find((n) => n?.type === 'slab' && n.id === 'slab_room') ?? all.find((n) => n?.type === 'slab');
  if (!slab || !slab.polygon[index]) throw new Error(`Outline vertex ${index} does not exist.`);
  const old: Point2 = slab.polygon[index];
  const polygon = slab.polygon.map((p: Point2, i: number) => (i === index ? point : p));
  const updates: Update[] = [{ id: slab.id, data: { polygon } }];
  const zone = all.find((n) => n?.type === 'zone' && n.id === 'zone_room');
  if (zone) updates.push({ id: zone.id, data: { polygon } });
  const same = (p: Point2) => Math.abs(p[0] - old[0]) < EPS && Math.abs(p[1] - old[1]) < EPS;
  for (const wall of all) {
    if (wall?.type !== 'wall' || !reviewMetaOf(wall)) continue;
    const data: Record<string, any> = {};
    if (same(wall.start)) data.start = point;
    if (same(wall.end)) data.end = point;
    if (Object.keys(data).length) updates.push({ id: wall.id, data: { ...data, metadata: metaPatch(wall, CORRECTED) } });
  }
  apply(updates);
}
