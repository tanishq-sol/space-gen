import type { Matrix4 } from '@/lib/contracts/primitives';

type V3 = [number, number, number];

/**
 * Client-side gravity guess for scans loaded without the room-structure service (Instant Preview,
 * scene library). A reduced port of services/room_structure/analyzer.py: RANSAC the dominant planes,
 * vote for the up direction they explain (floor/ceiling parallel, walls perpendicular), take the sign
 * from furniture standing on the floor, then refine the tilt with a fit on the floor slab.
 * Returns a row-major scanToScene: Y-up, floor at y = 0, floor centred on the origin.
 */
export function autoLevelFromPoints(positions: Float32Array, opacity?: Float32Array, maxPoints = 30_000): Matrix4 | null {
  const total = Math.floor(positions.length / 3);
  const all: V3[] = [];
  for (let i = 0; i < total; i += 1) {
    if (opacity && opacity[i] < 0.3) continue;
    const p: V3 = [positions[i * 3], positions[i * 3 + 1], positions[i * 3 + 2]];
    if (p.every(Number.isFinite)) all.push(p);
  }
  // Drop floaters: keep points inside the 1-99 percentile box on every axis, then subsample.
  const box = [0, 1, 2].map((a) => percentiles(all.map((p) => p[a]), [1, 99]));
  const inBox = all.filter((p) => p.every((v, a) => v >= box[a][0] && v <= box[a][1]));
  const step = Math.max(1, Math.ceil(inBox.length / maxPoints));
  const pts = inBox.filter((_, i) => i % step === 0);
  if (pts.length < 500) return null;

  const rand = lcg(1);
  let up = estimateUp(pts, rand);
  let h = pts.map((p) => dot(p, up));
  const peaks = planePeaks(h);
  if (!peaks.length) return null;
  let lo = Math.min(...peaks);
  let hi = Math.max(...peaks);
  if (upSign(pts, up, h, lo, hi) < 0) {
    up = neg(up);
    h = h.map((v) => -v);
    [lo, hi] = [-hi, -lo];
  }

  // Remove residual tilt with a plane fit on the floor slab, if it stays close to the voted up.
  const slab = pts.filter((_, i) => Math.abs(h[i] - lo) < 0.1);
  if (slab.length >= 200) {
    let normal = smallestEigenvector(slab);
    if (dot(normal, up) < 0) normal = neg(normal);
    if (dot(normal, up) > Math.cos((10 * Math.PI) / 180)) up = normal;
  }

  // Rows (x, up, z) with x × up = z: a right-handed rotation taking `up` to +Y.
  const [x, z] = basis(up);
  const floorPts = slab.length >= 50 ? slab : pts;
  const floorY = median(floorPts.map((p) => dot(p, up)));
  const centerX = median(floorPts.map((p) => dot(p, x)));
  const centerZ = median(floorPts.map((p) => dot(p, z)));
  return [
    x[0], x[1], x[2], -centerX,
    up[0], up[1], up[2], -floorY,
    z[0], z[1], z[2], -centerZ,
    0, 0, 0, 1,
  ];
}

/** Vote over plane normals (and the cross products of perpendicular pairs) as in the backend's estimate_up. */
function estimateUp(pts: V3[], rand: () => number): V3 {
  const planes = extractPlanes(pts, rand);
  const candidates: V3[] = planes.length ? planes.map((p) => p.normal) : [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
  for (let i = 0; i < planes.length; i += 1) {
    for (let j = i + 1; j < planes.length; j += 1) {
      if (Math.abs(dot(planes[i].normal, planes[j].normal)) < 0.15) candidates.push(unit(cross(planes[i].normal, planes[j].normal)));
    }
  }
  const unique = candidates.filter((c, i) => !candidates.slice(0, i).some((u) => Math.abs(dot(c, u)) > 0.995));
  const extents = unique.map((u) => {
    const [a, b] = percentiles(pts.map((p) => dot(p, u)), [2, 98]);
    return b - a;
  });
  const maxExtent = Math.max(...extents);
  const cosPar = Math.cos((6 * Math.PI) / 180);
  const sinPerp = Math.sin((6 * Math.PI) / 180);
  let best = unique[0];
  let bestScore = -1;
  unique.forEach((u, k) => {
    let votes = 0;
    for (const plane of planes) {
      const d = Math.abs(dot(plane.normal, u));
      votes += plane.count * (d > cosPar ? 1 : d < sinPerp ? 0.6 : 0);
    }
    // Rooms are wider than tall; with no planes this alone picks the shortest axis.
    const score = (votes + 1) * (1 + 0.5 * (1 - extents[k] / maxExtent));
    if (score > bestScore) { bestScore = score; best = u; }
  });
  return best;
}

/** Sequential RANSAC: up to 8 planes holding >= 2% of the points each (2 cm threshold). */
function extractPlanes(pts: V3[], rand: () => number) {
  const planes: { normal: V3; count: number }[] = [];
  let rest = pts;
  const minCount = Math.max(100, 0.02 * pts.length);
  for (let n = 0; n < 8 && rest.length >= minCount; n += 1) {
    let best: { normal: V3; d: number; count: number } | null = null;
    for (let iter = 0; iter < 300; iter += 1) {
      const [a, b, c] = [0, 1, 2].map(() => rest[Math.floor(rand() * rest.length)]);
      const raw = cross(sub(b, a), sub(c, a));
      if (Math.hypot(...raw) < 1e-9) continue;
      const normal = unit(raw);
      const d = -dot(normal, a);
      let count = 0;
      for (const p of rest) if (Math.abs(dot(normal, p) + d) < 0.02) count += 1;
      if (!best || count > best.count) best = { normal, d, count };
    }
    if (!best || best.count < minCount) break;
    const plane = best;
    planes.push({ normal: plane.normal, count: plane.count });
    rest = rest.filter((p) => Math.abs(dot(plane.normal, p) + plane.d) >= 0.02);
  }
  return planes;
}

/** Up to two plane-like height peaks (2 cm bins), the strongest first; a second only if >= 1.5 m away. */
function planePeaks(h: number[], bin = 0.02): number[] {
  const [lo, hi] = percentiles(h, [0.5, 99.5]);
  const n = Math.max(1, Math.ceil((hi - lo) / bin) + 2);
  if (n > 20_000) return [];
  const hist = new Float64Array(n);
  for (const v of h) {
    const i = Math.floor((v - lo) / bin) + 1;
    if (i >= 0 && i < n) hist[i] += 1;
  }
  const smooth = hist.map((_, i) => ((hist[i - 1] ?? 0) + hist[i] + (hist[i + 1] ?? 0)) / 3);
  const top = Math.max(...smooth);
  const peaks: { at: number; size: number }[] = [];
  for (let i = 0; i < n; i += 1) {
    if (smooth[i] >= (smooth[i - 1] ?? 0) && smooth[i] > (smooth[i + 1] ?? 0) && smooth[i] >= 0.15 * top) {
      peaks.push({ at: lo + (i - 0.5) * bin, size: smooth[i] });
    }
  }
  peaks.sort((a, b) => b.size - a.size);
  if (!peaks.length) return [];
  const second = peaks.find((p) => Math.abs(p.at - peaks[0].at) >= 1.5);
  return second ? [peaks[0].at, second.at] : [peaks[0].at];
}

/** +1 if `up` points floor → ceiling. Furniture stacks on the floor; walls are excluded by using the interior. */
function upSign(pts: V3[], up: V3, h: number[], lo: number, hi: number): 1 | -1 {
  if (hi - lo >= 1.5) {
    const axes = basis(up);
    const ranges = axes.map((a) => percentiles(pts.map((p) => dot(p, a)), [15, 85]));
    let nLo = 0;
    let nHi = 0;
    pts.forEach((p, i) => {
      if (!axes.every((a, k) => { const v = dot(p, a); return v >= ranges[k][0] && v <= ranges[k][1]; })) return;
      if (h[i] > lo + 0.15 && h[i] < lo + 1.2) nLo += 1;
      if (h[i] < hi - 0.15 && h[i] > hi - 1.2) nHi += 1;
    });
    if (Math.max(nLo, nHi) >= 100 && Math.max(nLo, nHi) >= 1.5 * Math.min(nLo, nHi)) return nHi > nLo ? -1 : 1;
    // Undecided: most of a room's content sits nearer the floor.
    return median(h) - lo <= hi - median(h) ? 1 : -1;
  }
  // One plane seen: it is the floor when more content lies clearly above it than below (the plane itself is excluded).
  const above = h.filter((v) => v > lo + 0.15).length;
  const below = h.filter((v) => v < lo - 0.15).length;
  return above >= below ? 1 : -1;
}

/** (x, z) completing `up` to a right-handed frame with x × up = z. */
function basis(up: V3): [V3, V3] {
  const helper: V3 = Math.abs(up[0]) < 0.9 ? [1, 0, 0] : [0, 0, 1];
  const x = unit(sub(helper, scale(up, dot(helper, up))));
  return [x, cross(x, up)];
}

function smallestEigenvector(pts: V3[]): V3 {
  const c = [0, 0, 0];
  for (const p of pts) for (let i = 0; i < 3; i += 1) c[i] += p[i] / pts.length;
  const m = new Array<number>(9).fill(0);
  for (const p of pts) {
    const d = [p[0] - c[0], p[1] - c[1], p[2] - c[2]];
    for (let r = 0; r < 3; r += 1) for (let k = 0; k < 3; k += 1) m[r * 3 + k] += d[r] * d[k];
  }
  // Power iteration on (tr + 1)I - C converges to C's smallest-eigenvalue vector.
  const shift = m[0] + m[4] + m[8] + 1;
  let v: V3 = [0.3, 0.9, 0.3];
  for (let iter = 0; iter < 60; iter += 1) {
    v = unit([0, 1, 2].map((r) => shift * v[r] - (m[r * 3] * v[0] + m[r * 3 + 1] * v[1] + m[r * 3 + 2] * v[2])) as V3);
  }
  return v;
}

function percentiles(values: number[], ps: number[]): number[] {
  const sorted = Float64Array.from(values).sort();
  return ps.map((p) => sorted[Math.min(sorted.length - 1, Math.max(0, Math.round((p / 100) * (sorted.length - 1))))]);
}
function lcg(seed: number) {
  let s = seed;
  return () => (s = (s * 16807) % 2147483647) / 2147483647;
}
const median = (values: number[]) => percentiles(values, [50])[0];
const dot = (a: V3, b: V3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const sub = (a: V3, b: V3): V3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const scale = (a: V3, k: number): V3 => [a[0] * k, a[1] * k, a[2] * k];
const neg = (a: V3): V3 => [-a[0], -a[1], -a[2]];
const cross = (a: V3, b: V3): V3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const unit = (v: V3): V3 => {
  const length = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / length, v[1] / length, v[2] / length];
};
