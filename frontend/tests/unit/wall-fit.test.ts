import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import fs from 'fs';
import path from 'path';
import { useScene } from '@pascal-app/core';
import { ProjectManifestSchema, type RoomInterpretation } from '@/lib/contracts';
import { applyInterpretationToScene, deriveInterpretationFromScene, getInterpretationMeta } from '@/lib/pascal/scanConverter';
import { getWallFit, moveWall, setWallFit } from '@/lib/pascal/interpretationReview';
import { formatWallFit } from '@/lib/measurement/accuracy';

const manifest = ProjectManifestSchema.parse(
  JSON.parse(fs.readFileSync(path.resolve(__dirname, '../fixtures/realistic_room.json'), 'utf-8')),
);
const nodes = () => useScene.getState().nodes as Record<string, any>;

/** The fixture room with its east wall leaning 1 degree (as built) and squared at x = 8.05. */
function leaningRoom(): RoomInterpretation {
  const base = manifest.interpretation;
  const lean = (id: string, start: [number, number], end: [number, number]) => {
    const w = base.walls.find((x) => x.id === id)!;
    return { ...w, start: [start[0], 0, start[1]] as [number, number, number], end: [end[0], 0, end[1]] as [number, number, number] };
  };
  const walls = [
    { ...lean('wall_north', [0, 0], [8, 0]), rmseCm: 0.8, inlierRatio: 0.92 },
    lean('wall_east', [8, 0], [8.1, 6]),
    lean('wall_south', [8.1, 6], [0, 6]),
    lean('wall_west', [0, 6], [0, 0]),
  ];
  const wallsSquare = [
    lean('wall_north', [0, 0], [8.05, 0]),
    lean('wall_east', [8.05, 0], [8.05, 6]),
    lean('wall_south', [8.05, 6], [0, 6]),
    lean('wall_west', [0, 6], [0, 0]),
  ];
  return { ...base, outline: [[0, 0], [8, 0], [8.1, 6], [0, 6]], walls, wallsSquare };
}

describe('Square (CAD) and As-built wall fits', () => {
  beforeEach(() => {
    applyInterpretationToScene(leaningRoom(), { scan: manifest.scan, maskRegions: manifest.maskRegions });
    (useScene as any).temporal.getState().clear();
  });
  afterEach(() => {
    useScene.getState().clearScene();
    (useScene as any).temporal.getState().clear();
  });

  it('starts as built and switches walls, outline and room together without marking a correction', () => {
    expect(getWallFit(nodes())).toBe('asBuilt');
    setWallFit('square');
    expect(getWallFit(nodes())).toBe('square');
    expect(nodes().wall_east.start).toEqual([8.05, 0]);
    expect(nodes().wall_east.end).toEqual([8.05, 6]);
    expect(nodes().wall_north.end).toEqual([8.05, 0]);
    expect(nodes().wall_south.start).toEqual([8.05, 6]);
    expect(nodes().slab_scan_outline.polygon[2]).toEqual([8.05, 6]);
    expect(nodes().zone_scan_room.polygon[1]).toEqual([8.05, 0]);
    expect(getInterpretationMeta(nodes().wall_east)!.status).toBe('auto');

    setWallFit('asBuilt');
    expect(nodes().wall_east.end).toEqual([8.1, 6]);
    expect(nodes().slab_scan_outline.polygon[2]).toEqual([8.1, 6]);
  });

  it('saves the as-built walls and the square fit, whichever is on screen', () => {
    setWallFit('square');
    const derived = deriveInterpretationFromScene(nodes())!;
    expect(derived.walls.find((w) => w.id === 'wall_east')).toMatchObject({ start: [8, 0, 0], end: [8.1, 0, 6] });
    expect(derived.wallsSquare!.find((w) => w.id === 'wall_east')).toMatchObject({ start: [8.05, 0, 0], end: [8.05, 0, 6] });
    expect(derived.outline).toEqual([[0, 0], [8, 0], [8.1, 6], [0, 6]]);
    expect(derived.walls.find((w) => w.id === 'wall_north')).toMatchObject({ rmseCm: 0.8, inlierRatio: 0.92 });
  });

  it('after a wall is edited the edit is the room: the fit is locked and saved as edited', () => {
    setWallFit('square');
    moveWall('wall_west', [0.1, 0]);
    expect(() => setWallFit('asBuilt')).toThrow(/edited/);
    const derived = deriveInterpretationFromScene(nodes())!;
    expect(derived.wallsSquare).toBeUndefined();
    expect(derived.walls.find((w) => w.id === 'wall_east')).toMatchObject({ start: [8.05, 0, 0], end: [8.05, 0, 6] });
  });

  it('formats a wall fit for the review panel', () => {
    expect(formatWallFit(0.84, 0.917)).toBe('Surface fit ±0.8 cm · seen along 92%');
    expect(formatWallFit(12.4, null)).toBe('Surface fit ±12 cm');
    expect(formatWallFit(null, null)).toBeNull();
  });
});
