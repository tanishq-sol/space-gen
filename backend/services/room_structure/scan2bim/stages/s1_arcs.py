"""Stage 1c — curved walls as arcs (accuracy round 16).

The chord pass (s1_local.py) fits a curved wall only where a straight piece of
`local_min_length` stays within the face tolerance: on a 12 m radius a 2 cm sag
allows 1.4 m, and pilasters break it further, so tight curves stay missed. This
pass looks for the circles themselves.

1. Every vertical return no face explains votes, along its normal (both ways), for
   the centres it could belong to at radii `arc_min_radius`..`arc_max_radius`.
   Straight walls vote along parallel lines and never concentrate; a curved wall's
   returns all vote for its centre. A peak (3 x 3 cells) of at least `arc_min_votes`
   returns, thinned to one per `arc_thin` cell, is a candidate centre, refined as the
   point nearest to all its returns' normal lines (least squares, trimmed).
2. The returns whose normal is radial to that centre (within `arc_radial_deg`) are
   unrolled: radius becomes the across axis, arc length (at the median radius) the
   along axis. A curved wall is a straight line there, so the same `find_faces`
   measures it with every test a flat wall passes (runs, height, rms, cover,
   lintel gaps). The ceiling map and scanner positions are read through the same
   mapping.
3. Each accepted face is mapped back as a chain of chords sagging at most
   `arc_chord_sag`, cut at the same angles for every face of one centre, so the two
   faces of a curved wall share their chords' directions and pair in stage 2. Chords
   are trimmed against faces already kept (s1_local._trim), as local chords are.

4. Round 16b: an arc that stops short of the ceiling is dropped (`arc_require_full_height`):
   a round case or a dome's drum, not a wall. A two-face rule (`arc_require_pair`) is
   kept as an option, off: one face of most large curved walls is all the scan holds.

Rejections from the unrolled search are kept, tagged `arc`.
"""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np

from ..config import Config
from ..model import Face


class _UnrolledCeilings:
    """A ceiling map read at unrolled (radius, arc length) positions."""

    def __init__(self, ceilings, centre: np.ndarray, r0: float, theta0: float):
        self.ceilings, self.centre, self.r0, self.theta0 = ceilings, centre, r0, theta0

    def at(self, xy: np.ndarray, above: np.ndarray | None = None) -> np.ndarray:
        return self.ceilings.at(_to_world(xy, self.centre, self.r0, self.theta0), above=above)


def _to_world(xy: np.ndarray, centre: np.ndarray, r0: float, theta0: float) -> np.ndarray:
    th = theta0 + xy[:, 1] / r0
    return centre + xy[:, :1] * np.c_[np.cos(th), np.sin(th)]


def _unit(n: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    norm = np.hypot(n[:, 0], n[:, 1])
    ok = norm > 0.5
    return n[ok] / norm[ok, None], ok


def _thin(xy: np.ndarray, cell: float) -> np.ndarray:
    """Index of one point per `cell` grid square."""
    key = np.floor(xy / cell).astype(np.int64)
    _, first = np.unique(key, axis=0, return_index=True)
    return np.sort(first)


def _votes(xy: np.ndarray, n: np.ndarray, cfg: Config, lo: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Accumulator of centre votes on the `arc_vote_cell` grid starting at `lo`."""
    cell = cfg.arc_vote_cell
    radii = np.arange(cfg.arc_min_radius, cfg.arc_max_radius, cell / 2)
    acc = np.zeros(shape[0] * shape[1], np.int64)
    for i in range(0, len(xy), 4000):
        p, d = xy[i : i + 4000], n[i : i + 4000]
        for sign in (1.0, -1.0):
            c = p[:, None, :] + sign * radii[None, :, None] * d[:, None, :]
            ij = np.floor((c - lo) / cell).astype(np.int64)
            ok = (ij[..., 0] >= 0) & (ij[..., 0] < shape[0]) & (ij[..., 1] >= 0) & (ij[..., 1] < shape[1])
            # one vote per point per cell (a line crosses a cell at a few radii)
            key = (np.arange(len(p))[:, None] * (shape[0] * shape[1]) + ij[..., 0] * shape[1] + ij[..., 1])[ok]
            cells = np.unique(key) % (shape[0] * shape[1])
            acc += np.bincount(cells, minlength=len(acc))
    return acc.reshape(shape)


def _centre(xy: np.ndarray, n: np.ndarray, guess: np.ndarray, cfg: Config) -> tuple[np.ndarray | None, np.ndarray]:
    """The point nearest to the normal lines of the returns that point at `guess`
    (least squares, re-taken with a tighter angle three times), and those returns.
    None when their normals span less than `arc_min_span_deg`: near-parallel lines
    are a straight wall, and their crossing point is noise."""
    c = guess.astype(float)
    t = np.c_[-n[:, 1], n[:, 0]]  # along each return's face: its normal line's distance to c is t . (c - p)
    mask = np.zeros(len(xy), bool)
    for deg in (3 * cfg.arc_line_deg, 2 * cfg.arc_line_deg, cfg.arc_line_deg):
        rho = np.hypot(*(xy - c).T)
        miss = np.abs(np.einsum("ij,ij->i", t, c - xy))
        mask = (miss <= rho * math.sin(math.radians(deg))) & (rho >= cfg.arc_min_radius) & (rho <= cfg.arc_max_radius)
        if mask.sum() < 3:
            return None, mask
        # spread of the normals' directions (axial, so mod 180), about their mean
        ang = np.arctan2(n[mask, 1], n[mask, 0])
        mean = 0.5 * np.arctan2(np.sin(2 * ang).mean(), np.cos(2 * ang).mean())
        dev = (ang - mean + np.pi / 2) % np.pi - np.pi / 2
        if np.degrees(np.percentile(dev, 95) - np.percentile(dev, 5)) < cfg.arc_min_span_deg:
            return None, mask
        tt, pp = t[mask], xy[mask]
        c = np.linalg.solve(tt.T @ tt, (tt * np.einsum("ij,ij->i", tt, pp)[:, None]).sum(0))
    return c, mask


def find_centres(xy: np.ndarray, normals: np.ndarray, cfg: Config) -> list[np.ndarray]:
    """Centres of the circles the returns (plan `xy`, horizontal `normals`) lie on."""
    n, ok = _unit(normals[:, :2])
    xy = xy[ok]
    if len(xy) < cfg.arc_min_votes:
        return []
    keep = _thin(xy, cfg.arc_thin)
    xy, n = xy[keep], n[keep]
    cell = cfg.arc_vote_cell
    lo = xy.min(0) - cfg.arc_max_radius
    shape = tuple(int(x) for x in np.ceil((xy.max(0) + cfg.arc_max_radius - lo) / cell).astype(int) + 1)
    acc = _votes(xy, n, cfg, lo, shape)
    left = np.ones(len(xy), bool)
    out: list[np.ndarray] = []
    for _ in range(4 * cfg.arc_max_centres):
        k = int(np.argmax(acc))
        if acc.flat[k] < cfg.arc_min_votes or len(out) >= cfg.arc_max_centres:
            break
        i0, j0 = divmod(k, shape[1])
        c, mask = _centre(xy[left], n[left], lo + (np.array([i0, j0]) + 0.5) * cell, cfg)
        idx = np.flatnonzero(left)[mask]
        if c is not None and len(idx) >= cfg.arc_min_votes:
            out.append(c)
            # every return pointing at it within the first refinement's angle belongs to
            # this circle (noisy normals would otherwise vote a second centre beside it)
            rest = np.flatnonzero(left)
            d = xy[rest] - c
            rho = np.hypot(d[:, 0], d[:, 1])
            miss = np.abs(n[rest, 0] * d[:, 1] - n[rest, 1] * d[:, 0])
            own = rest[miss <= rho * math.sin(math.radians(3 * cfg.arc_line_deg))]
            acc -= _votes(xy[own], n[own], cfg, lo, shape)
            left[own] = False
        acc[i0, j0] = 0  # never the same peak twice
    return out


def _chords(f: Face, centre: np.ndarray, r_ref: float, theta0: float, step: float) -> list[Face]:
    """An unrolled face as world chords on the angle grid theta0 + j * step. Each piece,
    the face's partial end pieces included, lies on its grid cell's full chord, so every
    face of one centre has the same chord directions and the two faces of a wall pair."""
    th0, th1 = theta0 + f.r0 / r_ref, theta0 + f.r1 / r_ref
    j0, j1 = math.floor((th0 - theta0) / step), math.ceil((th1 - theta0) / step)

    def at(th: float) -> np.ndarray:
        return centre + f.offset_at((th - theta0) * r_ref) * np.array([math.cos(th), math.sin(th)])

    out = []
    for j in range(j0, j1):
        ga, gb = theta0 + j * step, theta0 + (j + 1) * step
        a, b = max(ga, th0), min(gb, th1)
        if b - a < 1e-9:
            continue
        ca, cb = at(ga), at(gb)
        t = cb - ca
        mid = (ga + gb) / 2
        u_out = np.array([t[1], -t[0]]) / max(float(np.hypot(*t)), 1e-12)
        if u_out @ np.array([math.cos(mid), math.sin(mid)]) < 0:
            u_out = -u_out
        d = math.degrees(math.atan2(u_out[1], u_out[0])) % 180.0
        u = np.array([math.cos(math.radians(d)), math.sin(math.radians(d))])
        v = np.array([-u[1], u[0]])
        same = 1 if u @ u_out > 0 else -1  # the frame's +u is outward (1) or inward (-1)
        offset = float(ca @ u)
        ra, rb = (a - theta0) * r_ref, (b - theta0) * r_ref
        q0, q1 = float(at(a) @ v), float(at(b) @ v)
        length = abs(q1 - q0)
        if length < 1e-6:
            continue

        def to_world(rr: float, ra=ra, rb=rb, q0=q0, q1=q1) -> float:
            return q0 + (rr - ra) / (rb - ra) * (q1 - q0)

        def inside(gaps, ra=ra, rb=rb, to_world=to_world):
            return [tuple(sorted((to_world(g0), to_world(g1)))) for g0, g1 in gaps if ra <= g0 and g1 <= rb]

        out.append(
            replace(
                f,
                direction=d,
                offset=offset,
                k=0.0,
                c=offset,
                r0=min(q0, q1),
                r1=max(q0, q1),
                length=length,
                points=int(round(f.points * length / max(f.length, 1e-9))),
                facing=f.facing * same,
                openings=[],
                bridged=inside(f.bridged),
                pier_bridged=inside(f.pier_bridged),
            )
        )
    return out


def _pair(f: Face, g: Face, cfg: Config) -> bool:
    """Two unrolled faces of one centre one wall thickness apart (stage 2's range) over
    `pair_min_overlap` of the shorter: the two sides of a curved wall."""
    lo, hi = max(f.r0, g.r0), min(f.r1, g.r1)
    if hi - lo < cfg.pair_min_overlap * min(f.r1 - f.r0, g.r1 - g.r0):
        return False
    mid = (lo + hi) / 2
    return cfg.pair_min_thickness <= abs(f.offset_at(mid) - g.offset_at(mid)) <= cfg.pair_max_thickness


def arc_faces(
    band: np.ndarray,
    normals: np.ndarray,
    faces: list[Face],
    cfg: Config,
    floor_z: float | None,
    ceilings,
    stations=None,
    scan=None,
    rejected: list[dict] | None = None,
) -> tuple[list[Face], dict]:
    from .s1_faces import find_faces  # local import: s1_faces calls this module
    from .s1_local import _explained, _trim

    stats = {"centres": 0, "faces": 0, "chords": 0, "length_m": 0.0, "circles": []}
    vertical = np.abs(normals[:, 2]) < 0.25
    idx = np.flatnonzero(vertical)
    if len(idx) == 0:
        return [], stats
    idx = idx[~_explained(band[idx, :2], faces, cfg.local_explained)]
    if len(idx) < cfg.face_min_points:
        return [], stats
    centres = find_centres(band[idx, :2], normals[idx], cfg)
    stats["centres"] = len(centres)
    found: list[Face] = []
    cos_tol = math.cos(math.radians(cfg.arc_radial_deg))
    for c in centres:
        d = band[idx, :2] - c
        rho = np.hypot(d[:, 0], d[:, 1])
        n, ok = _unit(normals[idx][:, :2])
        radial = np.zeros(len(idx), bool)
        e = d[ok] / np.maximum(rho[ok, None], 1e-9)
        radial[ok] = np.abs(np.einsum("ij,ij->i", n, e)) >= cos_tol
        sel = radial & (rho >= cfg.arc_min_radius) & (rho <= cfg.arc_max_radius)
        if sel.sum() < cfg.face_min_points:
            continue
        pick = idx[sel]
        th = np.arctan2(d[sel, 1], d[sel, 0])
        # unroll from the largest angular gap, so no wall is cut by the seam
        order = np.sort(th)
        gaps = np.diff(np.r_[order, order[0] + 2 * np.pi])
        g = int(np.argmax(gaps))
        theta0 = float(order[(g + 1) % len(order)])
        r_ref = float(np.median(rho[sel]))
        along = ((th - theta0) % (2 * np.pi)) * r_ref
        e_r = np.c_[np.cos(th), np.sin(th)]
        e_t = np.c_[-np.sin(th), np.cos(th)]
        nn = normals[pick]
        unrolled = np.c_[rho[sel], along, band[pick, 2]]
        un_normals = np.c_[np.einsum("ij,ij->i", nn[:, :2], e_r), np.einsum("ij,ij->i", nn[:, :2], e_t), nn[:, 2]]
        st = None
        if stations is not None:
            sd = stations[:, :2] - c
            st = np.c_[
                np.hypot(sd[:, 0], sd[:, 1]),
                ((np.arctan2(sd[:, 1], sd[:, 0]) - theta0) % (2 * np.pi)) * r_ref,
                stations[:, 2],
            ]
        rej: list[dict] = []
        got = find_faces(
            unrolled,
            un_normals,
            0.0,
            cfg,
            floor_z=floor_z,
            ceilings=None if ceilings is None else _UnrolledCeilings(ceilings, c, r_ref, theta0),
            rejected=rej,
            stations=st,
            scan=None if scan is None else scan[pick],
        )
        if rejected is not None:
            rejected += [{**x, "pass": "arc", "centre": [round(float(c[0]), 2), round(float(c[1]), 2)]} for x in rej]
        # an arc must be long enough for its curve to be measured: over sqrt(8 R trim) a
        # circle stays within the face tolerance of a straight line, so a shorter piece is
        # as much a straight wall (the chord pass's) as a curve; twice that sags 4x the tolerance
        got = [f for f in got if f.length >= 2 * math.sqrt(8 * max(f.offset, 1e-6) * cfg.face_trim)]
        if cfg.arc_require_full_height:
            got = [f for f in got if not f.partial_height]
        if cfg.arc_require_pair:
            got = [f for f in got if any(_pair(f, g, cfg) for g in got if g is not f)]
        if not got:
            continue
        # one angle step for every face of this centre: the smallest radius sags most
        rho_min = min(min(f.offset_at(f.r0), f.offset_at(f.r1)) for f in got)
        step = 2 * math.acos(max(1.0 - cfg.arc_chord_sag / max(rho_min, 1e-6), -1.0))
        stats["circles"].append(
            {
                "centre": [round(float(c[0]), 2), round(float(c[1]), 2)],
                "faces": sorted([round(f.offset, 2), round(f.length, 1)] for f in got),
                "arc_m": round(sum(f.length for f in got), 1),
            }
        )
        stats["faces"] += len(got)
        for f in got:
            found += _chords(f, c, r_ref, theta0, step)
    kept: list[Face] = []
    for f in sorted(found, key=lambda x: -x.points):
        piece = _trim(f, list(faces) + kept, cfg)
        if piece is not None:
            kept.append(piece)
    stats["chords"] = len(kept)
    stats["length_m"] = round(sum(f.length for f in kept), 2)
    return kept, stats
