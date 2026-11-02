"""Stage 1b — local faces: walls off the building's directions, curved walls as chords.

The main pass (`find_faces`) projects the whole storey along each building-wide
direction. A wall that follows none of them (a curved façade, a wing at an odd
angle too small to make its own direction) leaves vertical returns no face
explains. This pass takes those returns, cuts them into `local_tile` tiles
(half-overlapping), and where a tile's returns share one orientation and stand a
wall's height it runs the same `find_faces` on that tile along that local
direction, rounded to `local_dir_step` so the two faces of one curved wall share a
direction and can pair in stage 2. Every accepted face passed the same tests as
any other (band run, height, rms, cover, density); a curved wall comes out as a
chain of straight chords — a 2.5 m chord of a 25 m radius arc sags 3 cm.

Overlapping tiles find the same surface twice, and neighbouring chords of a curve
overlap. Chords are taken strongest first, and each is trimmed to the longest
stretch that does not lie on an already kept face (main-pass faces included);
a stretch shorter than `local_min_piece` is dropped. Tile rejections are kept,
tagged `local`, so recall reporting sees this pass too.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from ..config import Config
from ..model import Face


def _frame(direction: float) -> tuple[np.ndarray, np.ndarray]:
    t = np.deg2rad(direction)
    u = np.array([np.cos(t), np.sin(t)])
    return u, np.array([-u[1], u[0]])


def _explained(xy: np.ndarray, faces: list[Face], tol: float) -> np.ndarray:
    """Points within `tol` of an accepted face's line, inside its extent (+0.1 m).
    One projection per direction, then each face reads only its own slice of the
    sorted along-coordinate (review R6-H3)."""
    hit = np.zeros(len(xy), bool)
    by_dir: dict[float, list[Face]] = {}
    for f in faces:
        by_dir.setdefault(f.direction, []).append(f)
    for d, group in by_dir.items():
        u, v = _frame(d)
        r = xy @ v
        order = np.argsort(r, kind="stable")
        r_sorted = r[order]
        s = None
        for f in group:
            i0, i1 = np.searchsorted(r_sorted, [f.r0 - 0.1, f.r1 + 0.1])
            if i1 <= i0:
                continue
            if s is None:
                s = xy @ u
            idx = order[i0:i1]
            hit[idx[np.abs(s[idx] - (f.k * r[idx] + f.c)) < tol]] = True
    return hit


def _tile_direction(normals: np.ndarray, cfg: Config) -> float | None:
    """The tile's one orientation (normal angle mod 180), when enough of its
    returns share it, rounded to `local_dir_step`."""
    ang = np.degrees(np.arctan2(normals[:, 1], normals[:, 0])) % 180.0
    hist, _ = np.histogram(ang, bins=180, range=(0.0, 180.0))
    smooth = np.convolve(np.r_[hist[-3:], hist, hist[:3]], np.ones(7), mode="valid")
    peak = int(np.argmax(smooth)) + 0.5
    d = (ang - peak + 90.0) % 180.0 - 90.0
    near = np.abs(d) < 3.0
    if near.mean() < cfg.local_min_share:
        return None
    exact = (peak + d[near].mean()) % 180.0
    return float(round(exact / cfg.local_dir_step) * cfg.local_dir_step % 180.0)


def _segment(f: Face) -> tuple[np.ndarray, np.ndarray]:
    u, v = _frame(f.direction)
    return (f.k * f.r0 + f.c) * u + f.r0 * v, (f.k * f.r1 + f.c) * u + f.r1 * v


def _dist_to_segment(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    ab = b - a
    t = np.clip(((p - a) @ ab) / max(float(ab @ ab), 1e-12), 0.0, 1.0)
    return np.hypot(*(p - (a + t[:, None] * ab)).T)


def _trim(f: Face, kept: list[Face], cfg: Config) -> Face | None:
    """`f` minus every stretch lying on a kept face (within `local_dup_dist`):
    the longest free stretch, or None if it is shorter than `local_min_piece`."""
    u, v = _frame(f.direction)
    rs = np.arange(f.r0, f.r1 + 1e-9, 0.05)
    pts = (f.k * rs + f.c)[:, None] * u + rs[:, None] * v
    taken = np.zeros(len(rs), bool)
    for g in kept:
        a, b = _segment(g)
        taken |= _dist_to_segment(pts, a, b) < cfg.local_dup_dist
    if not taken.any():
        return f
    free = np.r_[False, ~taken, False].astype(np.int8)
    d = np.diff(free)
    starts, ends = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
    if not len(starts):
        return None
    k = int(np.argmax(ends - starts))
    r0, r1 = float(rs[starts[k]]), float(rs[ends[k] - 1])
    if r1 - r0 < cfg.local_min_piece:
        return None
    return replace(f, r0=r0, r1=r1, length=r1 - r0, offset=float(f.k * (r0 + r1) / 2 + f.c),
                   points=int(round(f.points * (r1 - r0) / max(f.length, 1e-9))),
                   bridged=[x for x in f.bridged if r0 <= x[0] and x[1] <= r1],
                   pier_bridged=[x for x in f.pier_bridged if r0 <= x[0] and x[1] <= r1])


def local_faces(band: np.ndarray, normals: np.ndarray, faces: list[Face], directions: list[float],
                cfg: Config, floor_z: float, ceilings, stations=None, scan=None,
                rejected: list[dict] | None = None) -> tuple[list[Face], dict]:
    from .s1_faces import find_faces  # local import: s1_faces calls this module

    stats = {"tiles": 0, "tiles_oriented": 0, "faces": 0, "length_m": 0.0}
    vertical = np.abs(normals[:, 2]) < 0.25
    idx = np.flatnonzero(vertical)
    if len(idx) == 0:
        return [], stats
    idx = idx[~_explained(band[idx, :2], faces, cfg.local_explained)]
    if len(idx) < cfg.face_min_points:
        return [], stats

    half = cfg.local_tile / 2.0
    key = np.floor(band[idx, :2] / half).astype(np.int64)
    order = np.lexsort((key[:, 1], key[:, 0]))
    idx, key = idx[order], key[order]
    cells, start, count = np.unique(key, axis=0, return_index=True, return_counts=True)
    where = {(int(c[0]), int(c[1])): (int(s), int(n)) for c, s, n in zip(cells, start, count)}
    tile_cfg = cfg.with_(face_tile=0.0, face_min_length=cfg.local_min_length, face_trim=cfg.local_face_trim)
    found: list[Face] = []
    tiles = sorted({(int(c[0]) + a, int(c[1]) + b) for c in cells for a in (-1, 0) for b in (-1, 0)})
    for ci, cj in tiles:
        parts = []
        for dc in ((0, 0), (1, 0), (0, 1), (1, 1)):  # a tile is 2 x 2 half-tile cells
            hit = where.get((ci + dc[0], cj + dc[1]))
            if hit is not None:
                parts.append(idx[hit[0]:hit[0] + hit[1]])
        if not parts:
            continue
        pick = np.concatenate(parts)
        if len(pick) < cfg.face_min_points:
            continue
        z = band[pick, 2]
        if np.percentile(z, 98) - np.percentile(z, 2) < cfg.face_min_zspread:
            continue  # nothing wall-high stands here: clutter (review R6-M4)
        stats["tiles"] += 1
        d = _tile_direction(normals[pick], cfg)
        if d is None or min(abs((d - g + 90.0) % 180.0 - 90.0) for g in directions) < cfg.local_min_offaxis:
            continue  # no single surface here, or one the main pass already searched
        stats["tiles_oriented"] += 1
        rej: list[dict] = []
        found += find_faces(
            band[pick], normals[pick], d, tile_cfg, floor_z=floor_z, ceilings=ceilings, rejected=rej,
            stations=stations, scan=None if scan is None else scan[pick],
        )
        if rejected is not None:
            rejected += [{**x, "pass": "local"} for x in rej]

    kept: list[Face] = []
    for f in sorted(found, key=lambda x: -x.points):
        piece = _trim(f, list(faces) + kept, cfg)
        if piece is not None:
            kept.append(piece)
    stats["faces"] = len(kept)
    stats["length_m"] = round(sum(f.length for f in kept), 2)
    return kept, stats
