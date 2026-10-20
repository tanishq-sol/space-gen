import { beforeEach, describe, expect, it } from 'vitest';
import { useScene } from '@pascal-app/core';
import fixture from '../fixtures/realistic_room.json';
import { ProjectManifestSchema, RoomInterpretationSchema, type RoomInterpretation } from '@/lib/contracts';
import { convertInterpretationToNodes, convertScanToEditableNodes, SAMPLE_ROOM_SCAN_MANIFEST } from '@/lib/pascal/scanConverter';
import { undoSceneAction } from '@/lib/pascal/sceneBridge';
import {
  addOpening, applyDetectionPose, deleteWall, moveOutlineVertex, moveWall, rejectDetection,
  relabelDetection, removeOpening, resizeOpening, setDetectionBox, splitWall, verifyElement,
} from '@/lib/interpretation/corrections';
import { deriveInterpretation, getPlaceableElements, getPlacementWarning, listReviewEntries } from '@/lib/interpretation/review';

const manifest = ProjectManifestSchema.parse(fixture);
const nodes = () => useScene.getState().nodes as Record<string, any>;
const clone = (): RoomInterpretation => structuredClone(manifest.interpretation);

function load(interpretation = clone()) {
  convertInterpretationToNodes(interpretation, { scan: manifest.scan, maskRegions: manifest.maskRegions });
  (useScene as any).temporal?.getState?.().clear?.();
  return interpretation;
}

describe('T12 interpretation → Pascal nodes', () => {
  beforeEach(() => {
    useScene.getState().clearScene();
    (useScene as any).temporal?.getState?.().clear?.();
  });

  it('creates slab, zone, walls, openings, items and masks with prefixed ids', () => {
    const interp = load();
    const all = Object.values(nodes());
    const count = (type: string) => all.filter((n) => n.type === type).length;
    expect(count('slab')).toBe(1);
    expect(count('zone')).toBe(1);
    expect(count('wall')).toBe(interp.walls.length);
    expect(count('door')).toBe(2);
    expect(count('window')).toBe(1);
    expect(count('item')).toBe(interp.detections.length);
    const wall = nodes()[`wall_${interp.walls[0].id}`];
    expect(wall.start).toEqual([interp.walls[0].start[0], interp.walls[0].start[2]]);
    const window = Object.values(nodes()).find((n: any) => n.type === 'window') as any;
    expect(nodes()[window.parentId].type).toBe('wall');
    expect(nodes()[window.parentId].children).toContain(window.id);
    const scan = all.find((n) => n.type === 'scan');
    expect(scan.metadata.maskRegions).toHaveLength(interp.detections.length);
    const sofa = nodes()[`item_${interp.detections[0].id}`];
    expect(sofa.asset.src).toMatch(/\.glb$/);
    expect(sofa.metadata.review.status).toBe('verified');
  });

  it('is a single undo step', () => {
    useScene.getState().clearScene();
    (useScene as any).temporal?.getState?.().clear?.();
    convertInterpretationToNodes(clone(), { scan: manifest.scan });
    undoSceneAction();
    expect(Object.values(nodes()).filter((n) => n.type === 'wall')).toHaveLength(0);
  });

  it('round-trips through deriveInterpretation', () => {
    const interp = load();
    const derived = deriveInterpretation(nodes(), interp);
    expect(() => RoomInterpretationSchema.parse(derived)).not.toThrow();
    expect(derived.walls.map((w) => w.id).sort()).toEqual(interp.walls.map((w) => w.id).sort());
    const op = derived.openings.find((o) => o.id === interp.openings[2].id)!;
    expect(op.offset).toBeCloseTo(interp.openings[2].offset);
    expect(op.sill).toBeCloseTo(interp.openings[2].sill);
    const det = derived.detections.find((d) => d.id === interp.detections[1].id)!;
    expect(det.obb.center[1]).toBeCloseTo(interp.detections[1].obb.center[1]);
    expect(det.obb.size).toEqual(interp.detections[1].obb.size);
    expect(det.obb.yaw).toBeCloseTo(interp.detections[1].obb.yaw);
  });

  it('keeps the legacy raw-manifest converter working', () => {
    const result = convertScanToEditableNodes(SAMPLE_ROOM_SCAN_MANIFEST);
    expect(result.wallCount).toBe(4);
    expect(result.itemCount).toBe(5);
    expect(result.openingCount).toBe(2);
  });

  describe('corrections', () => {
    it('moves a wall, marks it user/corrected and survives derive', () => {
      const interp = load();
      const id = `wall_${interp.walls[0].id}`;
      moveWall(id, [0, 0.4], [8, 0.4]);
      expect(nodes()[id].metadata.review).toMatchObject({ provenance: 'user', status: 'corrected' });
      const derived = deriveInterpretation(nodes(), interp);
      const wall = derived.walls.find((w) => w.id === interp.walls[0].id)!;
      expect(wall.start).toEqual([0, 0, 0.4]);
      expect(wall.provenance).toBe('user');
      undoSceneAction();
      expect(nodes()[id].start).toEqual([interp.walls[0].start[0], interp.walls[0].start[2]]);
    });

    it('splits a wall, moving later openings to the new wall', () => {
      const interp = load();
      const id = `wall_${interp.walls[0].id}`; // 8 m wall with a window at 3.0
      const newId = splitWall(id, 2);
      expect(nodes()[id].end).toEqual([2, 0]);
      expect(nodes()[newId].start).toEqual([2, 0]);
      const window = Object.values(nodes()).find((n: any) => n.type === 'window') as any;
      expect(window.parentId).toBe(newId);
      expect(window.position[0]).toBeCloseTo(1);
      expect(nodes()[newId].children).toContain(window.id);
    });

    it('deletes a wall with its openings', () => {
      const interp = load();
      deleteWall(`wall_${interp.walls[0].id}`);
      expect(Object.values(nodes()).some((n: any) => n.type === 'window')).toBe(false);
      expect(deriveInterpretation(nodes(), interp).walls).toHaveLength(3);
    });

    it('adds, resizes and removes openings', () => {
      const interp = load();
      const wallId = `wall_${interp.walls[3].id}`;
      const id = addOpening(wallId, { kind: 'door', offset: 1, width: 0.9, height: 2.1, sill: 0 });
      expect(nodes()[id].metadata.review).toMatchObject({ provenance: 'user', status: 'corrected' });
      resizeOpening(id, { width: 1.2, height: 2.0 });
      expect(nodes()[id].width).toBe(1.2);
      const derived = deriveInterpretation(nodes(), interp);
      expect(derived.openings.find((o) => o.provenance === 'user')).toMatchObject({ width: 1.2, height: 2, wallId: interp.walls[3].id });
      removeOpening(id);
      expect(nodes()[id]).toBeUndefined();
    });

    it('moves the outline vertex together with slab, zone and wall endpoints', () => {
      const interp = load();
      moveOutlineVertex(2, [9, 7]);
      expect(nodes().slab_room.polygon[2]).toEqual([9, 7]);
      expect(nodes().zone_room.polygon[2]).toEqual([9, 7]);
      expect(nodes()[`wall_${interp.walls[1].id}`].end).toEqual([9, 7]);
      expect(nodes()[`wall_${interp.walls[2].id}`].start).toEqual([9, 7]);
      expect(deriveInterpretation(nodes(), interp).outline[2]).toEqual([9, 7]);
    });

    it('moves/resizes/rotates a detection and keeps its mask linked', () => {
      const interp = load();
      const det = interp.detections[4];
      const id = `item_${det.id}`;
      setDetectionBox(id, { center: [5, 0.5, 2], size: [1.5, 1, 0.5], yaw: 0.8 });
      const mask = nodes().scan_room.metadata.maskRegions.find((m: any) => m.itemId === id);
      expect(mask.obb).toEqual({ center: [5, 0.5, 2], size: [1.5, 1, 0.5], yaw: 0.8 });
      expect(nodes()[id].metadata.review).toMatchObject({ provenance: 'user', status: 'corrected' });
      applyDetectionPose(id, { position: [1, 0, 1], rotation: [0, 0.2, 0], scale: [2, 1, 1] });
      const mask2 = nodes().scan_room.metadata.maskRegions.find((m: any) => m.itemId === id);
      expect(mask2.obb.center[0]).toBe(1);
      expect(mask2.obb.size[0]).toBeCloseTo(3);
      const derived = deriveInterpretation(nodes(), interp).detections.find((d) => d.id === det.id)!;
      expect(derived.obb).toEqual(mask2.obb);
      expect(derived.status).toBe('corrected');
      expect(derived.maskRegionId).toBe(mask2.id);
    });

    it('relabels, verifies and rejects detections', () => {
      const interp = load();
      const id = `item_${interp.detections[4].id}`;
      verifyElement(id);
      expect(nodes()[id].metadata.review.status).toBe('verified');
      relabelDetection(id, 'Sideboard', 'storage');
      expect(nodes()[id].name).toBe('Sideboard');
      expect(nodes()[id].metadata.review).toMatchObject({ status: 'corrected', provenance: 'user', category: 'storage' });
      rejectDetection(id);
      expect(nodes()[id].visible).toBe(false);
      expect(nodes().scan_room.metadata.maskRegions.find((m: any) => m.itemId === id).enabled).toBe(false);
      const det = deriveInterpretation(nodes(), interp).detections.find((d) => d.label === 'Sideboard')!;
      expect(det).toMatchObject({ status: 'rejected', category: 'storage', provenance: 'user' });
    });
  });

  describe('review list and placement', () => {
    it('lists low-confidence unreviewed items first', () => {
      const interp = clone();
      interp.detections[5].confidence = 0.4;
      interp.walls[1].confidence = 0.5;
      load(interp);
      const entries = listReviewEntries(nodes());
      expect(entries[0]).toMatchObject({ confidence: 0.4, lowConfidence: true });
      expect(entries[1]).toMatchObject({ confidence: 0.5 });
      expect(entries.at(-1)!.status).not.toBe('auto');
    });

    it('placement uses only verified/corrected elements and warns about the rest', () => {
      const interp = load();
      const before = getPlaceableElements(nodes());
      expect(before.detections).toHaveLength(4);
      expect(before.unverified.length).toBeGreaterThan(0);
      expect(getPlacementWarning(nodes())).toMatch(/unverified/);
      for (const e of before.unverified) verifyElement(e.nodeId);
      expect(getPlacementWarning(nodes())).toBeNull();
      expect(getPlaceableElements(nodes()).walls).toHaveLength(interp.walls.length);
      rejectDetection(`item_${interp.detections[0].id}`);
      expect(getPlaceableElements(nodes()).detections).toHaveLength(5);
    });
  });
});
