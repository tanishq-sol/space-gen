import { describe, expect, it } from 'vitest';
import { autoLevelFromPoints } from '@/lib/scan/autoLevel';
import { transformPoint } from '@/lib/pascal/scanAlignment';
import type { Vector3 } from '@/lib/contracts/primitives';

/** Y-up room, floor y=0, ceiling 2.6 m, 5 x 4 m walls, a sofa and table on the floor. */
function room(): Vector3[] {
  let seed = 7;
  const rand = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const pts: Vector3[] = [];
  const plane = (n: number, f: (u: number, v: number) => Vector3) => { for (let i = 0; i < n; i += 1) pts.push(f(rand(), rand())); };
  plane(8000, (u, v) => [u * 5 - 2.5, 0, v * 4 - 2]);
  plane(5000, (u, v) => [u * 5 - 2.5, 2.6, v * 4 - 2]);
  plane(3000, (u, v) => [-2.5, v * 2.6, u * 4 - 2]);
  plane(3000, (u, v) => [2.5, v * 2.6, u * 4 - 2]);
  plane(3000, (u, v) => [u * 5 - 2.5, v * 2.6, -2]);
  plane(3000, (u, v) => [u * 5 - 2.5, v * 2.6, 2]);
  plane(4000, (u, v) => [u * 2 - 1, v * 0.8, 0.5 + rand() * 0.9]); // sofa
  plane(2000, (u, v) => [u * 1.2 - 0.6, 0.15 + v * 0.3, -0.8 + rand() * 0.6]); // table
  return pts;
}

const SOFA_TOP: Vector3 = [0, 0.8, 1];
const FLOOR: Vector3 = [1, 0, -1];

function level(transform: (p: Vector3) => Vector3) {
  const source = room().map(transform);
  const positions = Float32Array.from(source.flat());
  const matrix = autoLevelFromPoints(positions);
  expect(matrix).not.toBeNull();
  return (p: Vector3) => transformPoint(matrix!, transform(p));
}

describe('autoLevelFromPoints', () => {
  it('rights an upside-down (COLMAP / OpenCV, Y-down) scan and puts the floor at y=0', () => {
    const toScene = level(([x, y, z]) => [x + 3, -y + 1.2, -z - 4]);
    expect(toScene(FLOOR)[1]).toBeCloseTo(0, 1);
    expect(toScene(SOFA_TOP)[1]).toBeCloseTo(0.8, 1);
  });

  it('levels a Z-up scan with a small tilt', () => {
    const t = (8 * Math.PI) / 180;
    const toScene = level(([x, y, z]) => {
      const [a, b, c] = [x, -z, y];
      return [a, b * Math.cos(t) - c * Math.sin(t), b * Math.sin(t) + c * Math.cos(t)];
    });
    expect(toScene(FLOOR)[1]).toBeCloseTo(0, 1);
    expect(toScene([2, 0, 1.5])[1]).toBeCloseTo(0, 1);
    expect(toScene(SOFA_TOP)[1]).toBeCloseTo(0.8, 1);
  });

  it('keeps an already Y-up scan upright and centres the floor', () => {
    const toScene = level((p) => p);
    expect(toScene(FLOOR)[1]).toBeCloseTo(0, 1);
    expect(toScene(SOFA_TOP)[1]).toBeCloseTo(0.8, 1);
    expect(Math.hypot(toScene([0, 0, 0])[0], toScene([0, 0, 0])[2])).toBeLessThan(0.3);
  });

  it('rights an upside-down scan whose ceiling was not captured', () => {
    const source = room().filter(([, y]) => y < 2.5).map(([x, y, z]): Vector3 => [x, -y + 1.5, -z]);
    const matrix = autoLevelFromPoints(Float32Array.from(source.flat()));
    expect(transformPoint(matrix!, [1, 1.5, 1])[1]).toBeCloseTo(0, 1);
    expect(transformPoint(matrix!, [0, 0.7, -1])[1]).toBeCloseTo(0.8, 1);
  });

  it('returns null for too few points', () => {
    expect(autoLevelFromPoints(new Float32Array(30))).toBeNull();
  });
});
