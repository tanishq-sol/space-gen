"""Stage 4 — openings: voids in measured wall faces, classed by sill and head.

Design §4.5. Each measured face is read on a grid of `open_col` (along) by
`open_cell_z` (height) cells, from the floor to the wall's top; a cell is present
with >= `open_min_pts` returns within `open_trim` of the face's line. In each
column the void is the longest run of absent cells with a present cell above it
(a lintel or sill wall — without one the face was simply not scanned there) and
either a present cell below it (a window) or the floor (a door). Neighbouring
void columns that overlap in height join; a gap of one column (a mullion) does
not split them.

Stage 1's lintel-bridged gaps (`Face.bridged`) are openings already measured;
they are taken first and only classed here (wall below the band: a window).

Occlusion is the failure this stage must not mistake for an opening: a cabinet
standing in front of a wall leaves the face unscanned behind it. A void whose
cells mostly have returns 0.05-`open_occluder` m off the face, on either side,
is a shadow and is dropped (counted). A void on both faces of a paired wall is
recorded once, as `measured-both-faces`.

Classes (relative to the storey floor): door — sill <= `door_sill_max`, head
`door_head` range, width `door_width` range; window — sill >= `window_sill_min`;
everything else `unresolved` (design: the 0.15-0.45 m sill band is not guessed).
"""

from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from ..config import Config
from ..model import Face, Join, Model, Opening, Wall
from .s3_rooms import footprint


def _face_voids(f: Face, wall: Wall, pts: np.ndarray, floor_z: float, cfg: Config,
                stats: dict) -> list[Opening]:
    t = np.deg2rad(f.direction)
    u = np.array([np.cos(t), np.sin(t)])
    v = np.array([-u[1], u[0]])
    r = pts[:, :2] @ v
    d = pts[:, :2] @ u - (f.k * r + f.c)
    z = pts[:, 2]
    # the grid spans the whole face: a gap is classed on all of it, even where the
    # face is shared with a neighbouring wall piece (review R8-5); ceil, so a gap at
    # the face's end keeps its last column (R8-6)
    r0, r1 = f.r0, f.r1
    top = (wall.top_z if wall.top_z is not None else wall.z1) - 0.05
    ncol = max(int(np.ceil((r1 - r0) / cfg.open_col)), 1)
    nz = int((top - floor_z) / cfg.open_cell_z)
    if nz < 4:
        return []
    inside = (r >= r0) & (r < r0 + ncol * cfg.open_col) & (z >= floor_z) & (z < floor_z + nz * cfg.open_cell_z)
    ci = ((r - r0) / cfg.open_col).astype(int)
    zi = ((z - floor_z) / cfg.open_cell_z).astype(int)
    on = inside & (np.abs(d) < cfg.open_trim)
    front = inside & (np.abs(d) > 0.05) & (np.abs(d) < cfg.open_occluder)
    # which side of the face the wall's body is on: toward the wall axis, read in the
    # face's own frame (a face may run opposite to its wall)
    axis_pt = wall.axis_offset() * np.asarray(wall.unit)
    into = 1.0 if axis_pt @ u - (f.k * (f.r0 + f.r1) / 2 + f.c) >= 0 else -1.0
    present = np.zeros((ncol, nz), np.int32)
    np.add.at(present, (ci[on], zi[on]), 1)
    present = present >= cfg.open_min_pts
    occl = np.zeros((ncol, nz), np.int32)
    np.add.at(occl, (ci[front], zi[front]), 1)
    occl = occl >= cfg.open_min_pts
    floor_cells = int(round(cfg.door_sill_max / cfg.open_cell_z))
    out: list[Opening] = []
    used = np.zeros(ncol, bool)

    # Stage 1's lintel-bridged gaps are openings already measured: the face's
    # furniture-free band is empty there and a head stands above it (on the
    # benchmark 8/8 on TUB1, 20/26 on TUB2 sit on a reference door). The grid
    # only says which kind: wall below the band (a sill) makes it a window.
    band_lo = int(round(cfg.run_upper[0] / cfg.open_cell_z))
    sill_hi = int(round(cfg.open_sill_band / cfg.open_cell_z))
    for a, b in f.bridged:
        # each gap belongs to the one wall piece holding its centre (R8-5)
        if not (wall.r0_meas <= (a + b) / 2 < wall.r1_meas):
            continue
        c0, c1 = int(np.floor((a - r0) / cfg.open_col)), int(np.ceil((b - r0) / cfg.open_col))
        c0, c1 = max(c0, 0), min(c1, ncol)
        if c1 - c0 < 1:
            continue
        cols = present[c0:c1]
        # head: the first solid wall (two present cells) at or above the band's foot,
        # so a window head at 1.5 m is read as 1.5 m (R8-3); a lone return from a
        # frame is not a head
        heads = []
        for col in cols:
            solid = np.flatnonzero(col[band_lo:-1] & col[band_lo + 1:])
            if len(solid):
                heads.append(int(solid[0]) + band_lo)
        head = floor_z + (int(np.median(heads)) if heads else nz) * cfg.open_cell_z
        # sill: wall returns 0.2-0.9 m up in at least half the gap's columns make it a
        # window, the sill at their top. Measured (round 8 review): requiring a solid
        # wall from the floor, or 0.3 m of contiguous wall, typed 0 of Fire Brigade's 18
        # windows (radiators hide the wall under them) for 2 more UoM doors; this
        # looser reading types more openings right overall. A leaf or cabinet in a
        # doorway can still read as a sill (open item).
        low = cols[:, floor_cells + 1:sill_hi + 1]
        if low.size and low.any(axis=1).mean() >= 0.5:
            sills = [int(np.flatnonzero(col)[-1]) + floor_cells + 2 for col in low if col.any()]
            sill = floor_z + int(np.median(sills)) * cfg.open_cell_z
        else:
            sill = floor_z
        o = Opening(along0=max(a, r0), along1=min(b, r1), sill_z=sill, head_z=max(head, sill))
        o.source = "pier" if (a, b) in f.pier_bridged else "lintel"
        if o.source == "pier":
            # an opening only within the gap rules' widths, and on their evidence (R14-4)
            evidence = None
            if cfg.open_pier_openings and o.width <= cfg.open_pier_max_width:
                evidence = _span_evidence(wall, o.along0, o.along1, pts, floor_z, cfg) \
                    if cfg.open_pier_evidence else ("lintel", None)
            if evidence is None:
                stats["pier_spans_kept_as_wall"] = stats.get("pier_spans_kept_as_wall", 0) + 1
                used[c0:c1] = True
                continue
            if evidence[0] == "window":  # sill and head from the reading that gave the evidence (R14-5)
                o.sill_z, o.head_z = floor_z + evidence[1][0], floor_z + evidence[1][1]
            elif evidence[0] == "door":
                o.sill_z = floor_z
        elif cfg.open_floor_through_door and o.sill_z > floor_z + cfg.door_sill_max \
                and cfg.door_head[0] <= o.head_z - floor_z <= cfg.door_head[1] \
                and _floor_through(wall, o.along0, o.along1, pts, floor_z, cfg):
            # floor seen inside the wall's footprint: no wall stands under it, so what read
            # as a sill is a leaf or furniture in a doorway (round 9's door rule)
            read_sill, o.sill_z = o.sill_z, floor_z
            if _classify(o, floor_z, cfg) == "door":
                stats["floor_through_doors"] = stats.get("floor_through_doors", 0) + 1
            else:
                o.sill_z = read_sill  # only a door-shaped opening is re-read (R18-1)
        o.kind = _classify(o, floor_z, cfg)
        o.derivation = "measured" if o.kind != "unresolved" else "unresolved"
        parts = [o]
        if o.kind == "window" and cfg.open_mullion_split:
            cuts = _mullions(r, d, z, o, cfg)
            if cuts:
                edges = [o.along0, *cuts, o.along1]
                parts = []
                for e0, e1 in zip(edges[:-1], edges[1:]):
                    p_ = Opening(along0=e0, along1=e1, sill_z=o.sill_z, head_z=o.head_z)
                    p_.source, p_.kind, p_.derivation = o.source, _classify(p_, floor_z, cfg), o.derivation
                    parts.append(p_)
                stats["mullion_splits"] = stats.get("mullion_splits", 0) + len(cuts)
        out.extend(parts)
        used[c0:c1] = True
        stats["from_lintel"] = stats.get("from_lintel", 0) + 1

    if not cfg.open_void_search:
        return out
    # per column: the longest absent run with wall above it and wall or floor below
    runs: list[tuple[int, int] | None] = []
    for c in range(ncol):
        if used[c]:
            runs.append(None)
            continue
        best = None
        col = present[c]
        k = 0
        while k < nz:
            if col[k]:
                k += 1
                continue
            j = k
            while j < nz and not col[j]:
                j += 1
            above = j < nz  # a present cell closes the run from above
            below = k == 0 or col[k - 1] or k <= floor_cells
            if above and below and j - k >= cfg.open_min_cells and (best is None or j - k > best[1] - best[0]):
                best = (k, j)
            k = j
        runs.append(best)

    c = 0
    while c < ncol:
        if runs[c] is None:
            c += 1
            continue
        group = [c]
        k = c + 1
        while k < ncol:
            if runs[k] is not None and _overlap(runs[k], runs[group[-1]]) >= 0.5:
                group.append(k)
                k += 1
            elif k + 1 < ncol and runs[k] is None and runs[k + 1] is not None \
                    and _overlap(runs[k + 1], runs[group[-1]]) >= 0.5:
                group.append(k + 1)  # one-column mullion
                k += 2
            else:
                break
        c = group[-1] + 1
        width = (group[-1] - group[0] + 1) * cfg.open_col
        if width < cfg.open_min_width or width > cfg.open_max_width:
            stats["rejected_width"] += 1
            continue
        lo = int(np.median([runs[g][0] for g in group]))
        hi = int(np.median([runs[g][1] for g in group]))
        cells = occl[group[0]:group[-1] + 1, lo:hi]
        if cells.size and cells.mean() >= cfg.open_occluded_share:
            stats["rejected_occluded"] += 1
            if cfg.open_debug:
                a0, a1 = r0 + group[0] * cfg.open_col, r0 + (group[-1] + 1) * cfg.open_col
                z0, z1 = floor_z + lo * cfg.open_cell_z, floor_z + hi * cfg.open_cell_z
                sel = front & (r >= a0) & (r < a1) & (z >= z0) & (z < z1)
                behind = sel & (d * into > 0)
                mid = (f.k * (a0 + a1) / 2 + f.c) * u + (a0 + a1) / 2 * v
                stats.setdefault("_occluded", []).append({
                    "wall": wall.id, "x": float(mid[0]), "y": float(mid[1]), "width": round(a1 - a0, 2),
                    "sill": round(z0 - floor_z, 2), "head": round(z1 - floor_z, 2),
                    "into_wall_share": round(float(behind.sum()) / max(int(sel.sum()), 1), 2),
                    "depth_cm": round(100 * float(np.median(np.abs(d[sel]))), 1) if sel.any() else None})
            continue
        sill = floor_z if lo <= floor_cells else floor_z + lo * cfg.open_cell_z
        o = Opening(along0=r0 + group[0] * cfg.open_col, along1=r0 + (group[-1] + 1) * cfg.open_col,
                    sill_z=sill, head_z=floor_z + hi * cfg.open_cell_z)
        o.kind = _classify(o, floor_z, cfg)
        o.derivation = "measured" if o.kind != "unresolved" else "unresolved"
        out.append(o)
    return out


def _floor_through(w: Wall, a: float, b: float, pts: np.ndarray, floor_z: float, cfg: Config) -> bool:
    """Round 9's door rule: floor returns in >= `open_gap_floor` of the span's 0.1 m cells
    inside the wall's footprint (clear of its faces by `open_gap_face_clear`), and floor on
    both sides of it within 0.5 m: the floor runs through under the span."""
    if not len(pts) or b - a < cfg.open_min_width:
        return False
    half = max(w.thickness or 0.1, 0.1) / 2.0
    s_, r_, z = pts[:, :2] @ w.unit - w.axis_offset(), pts[:, :2] @ w.perp, pts[:, 2] - floor_z
    along = (r_ >= a) & (r_ < b)
    n = max(int(round((b - a) / 0.1)), 1)
    fl = along & (np.abs(z) < cfg.side_floor_tol)
    inner = fl & (np.abs(s_) < max(half - cfg.open_gap_face_clear, 0.03))
    ci = np.clip(((r_[inner] - a) / ((b - a) / n)).astype(int), 0, n - 1)
    return bool((np.bincount(ci, minlength=n) >= cfg.open_min_pts).mean() >= cfg.open_gap_floor
                and (fl & (s_ > half) & (s_ < half + 0.5)).sum() >= cfg.open_min_pts
                and (fl & (s_ < -half) & (s_ > -half - 0.5)).sum() >= cfg.open_min_pts)


def _span_evidence(w: Wall, a: float, b: float, pts: np.ndarray, floor_z: float,
                   cfg: Config) -> tuple[str, tuple[float, float] | None] | None:
    """A pier-anchored span's evidence (round 14), by the gap rules: "door" when floor
    returns lie in >= `open_gap_floor` of its 0.1 m cells inside the wall's footprint
    and on both sides of it (round 9), "window" when the wall or a radiator stands
    under a window-shaped opening at the face in >= `open_gap_window_share` of its
    columns (round 13), with the (sill, head) of that reading; else None: the span
    stays wall."""
    if not len(pts) or b - a < cfg.open_min_width:
        return None
    t = w.thickness or 0.1
    half = max(t, 0.1) / 2.0
    s_, r_, z = pts[:, :2] @ w.unit - w.axis_offset(), pts[:, :2] @ w.perp, pts[:, 2] - floor_z
    along = (r_ >= a) & (r_ < b)
    n = max(int(round((b - a) / 0.1)), 1)
    ci = np.clip(((r_ - a) / ((b - a) / n)).astype(int), 0, n - 1)
    if _floor_through(w, a, b, pts, floor_z, cfg):
        return "door", None
    for flip in _reveal_sides(w):
        k = along & ~_in_reveal(w, s_, cfg, flip) & (np.abs(s_) < half + cfg.open_trim + cfg.open_gap_sill_reach) \
            & (z >= cfg.open_gap_sill[0]) & (z < cfg.open_gap_sill[1])
        if (np.bincount(ci[k], minlength=n) >= cfg.open_min_pts).mean() < cfg.open_gap_window_share:
            continue
        ext = _window_extent(w, a, b, pts, floor_z, cfg, flip)
        if _window_shaped(ext, cfg):
            return "window", ext
    return None


def _mullions(r: np.ndarray, d: np.ndarray, z: np.ndarray, o: Opening, cfg: Config) -> list[float]:
    """Where a window span splits into windows (round 14): narrow clusters of returns
    (<= `open_mullion_max_width`, >= `open_mullion_pts` per 5 cm bin) within
    `open_mullion_depth` of the face in the glass band (sill + 0.2 m to head - 0.1 m),
    with `open_mullion_clear` of near-empty bins on each side (blinds and a closed
    sash fill a window's width and do not qualify). A cut is kept when the parts on
    both sides stay >= `open_min_width`. Returns the cut positions along the wall."""
    a, b = o.along0, o.along1
    if b - a < 2 * cfg.open_min_width + 0.05:
        return []
    k = (r >= a) & (r < b) & (np.abs(d) < cfg.open_mullion_depth) & (z > o.sill_z + 0.2) & (z < o.head_z - 0.1)
    step = 0.05
    n = int(np.ceil((b - a) / step))
    h = np.bincount(np.clip(((r[k] - a) / step).astype(int), 0, n - 1), minlength=n)
    hit = h >= cfg.open_mullion_pts
    clear = int(round(cfg.open_mullion_clear / step))
    cuts: list[float] = []
    i = 0
    while i < n:
        if not hit[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and hit[j + 1]:
            j += 1
        width = (j - i + 1) * step
        left, right = h[max(i - clear, 0):i], h[j + 1:j + 1 + clear]
        quiet = len(left) == clear and len(right) == clear and \
            (left < cfg.open_mullion_pts).mean() >= 0.75 and (right < cfg.open_mullion_pts).mean() >= 0.75
        c = a + (i + j + 1) / 2 * step
        prev = cuts[-1] if cuts else a
        if width <= cfg.open_mullion_max_width and quiet and c - prev >= cfg.open_min_width \
                and b - c >= cfg.open_min_width:
            cuts.append(c)
        i = j + 1
    return cuts


def bridge_door_gaps(model: Model, cfg: Config = Config()) -> dict:
    """Doorways between two pieces of one wall line (round 9).

    A door with no lintel above it (it reaches the ceiling) leaves no head for
    stage 1 to bridge, so the wall comes out in two collinear pieces. For every
    open wall end, the first wall its own axis meets within `open_gap[1]` must be
    collinear (+-3 deg); the gap is a doorway when it is `open_gap` wide and floor
    returns lie in >= `open_gap_floor` of its 0.1 m cells across the wall's
    footprint continued: under a wall the scanner never sees floor, through a
    doorway it does. The wall is then extended to the other piece and the span
    recorded in `door_gaps`; stage 4 turns it into an opening.
    """
    stats = {"gap_candidates": 0, "gap_doors": 0, "gap_windows": 0}
    if not cfg.open_gap_doors or model.cloud is None or model.levels is None or len(model.walls) < 2:
        return stats
    from shapely.geometry import LineString

    floor_z = float(model.levels.floor_z)
    floor_pts: list = []  # [points, cKDTree], built on the first candidate (R9-4)

    def floor_near(centre: np.ndarray, radius: float) -> np.ndarray:
        if not floor_pts:
            p = model.cloud.points
            fl = p[np.abs(p[:, 2] - floor_z) < cfg.side_floor_tol, :2]
            floor_pts.extend([fl, cKDTree(fl) if len(fl) else None])
        fl, tree = floor_pts
        if tree is None:
            return np.zeros((0, 2))
        return fl[np.asarray(tree.query_ball_point(centre, radius), dtype=np.int64)]

    wall_pts: list = []  # [points, cKDTree] above the floor, built on the first window test

    def wall_near(centre: np.ndarray, radius: float) -> np.ndarray:
        if not wall_pts:
            p = model.cloud.points
            k = (p[:, 2] > floor_z + cfg.open_gap_sill[0] - 0.05) & (p[:, 2] < floor_z + 4.0)
            wall_pts.extend([p[k], cKDTree(p[k, :2]) if k.any() else None])
        q, tree = wall_pts
        if tree is None:
            return np.zeros((0, 3))
        return q[np.asarray(tree.query_ball_point(centre, radius), dtype=np.int64)]

    def window_gap(w, lo_r, hi_r, gap, half, paired=False) -> bool:
        """Wall below the sill and above the head across the gap, glass between (round 13)."""
        # the head band stops short of the ceiling, whose returns lie in every column (R13-3)
        top = (w.top_z if w.top_z is not None else w.z1) - floor_z - WINDOW_CEILING_CLEAR
        if top < cfg.open_gap_head_min + 0.1:
            return False
        q = wall_near(w.axis_offset() * w.unit + (lo_r + hi_r) / 2 * w.perp, gap / 2 + half + 0.4)
        if not len(q):
            return False
        s_, r_, z = q[:, :2] @ w.unit - w.axis_offset(), q[:, :2] @ w.perp, q[:, 2] - floor_z
        n = max(int(round(gap / 0.1)), 1)
        ci = np.clip(((r_ - lo_r) / (gap / n)).astype(int), 0, n - 1)

        def share(z0, z1, reach=0.0, face=None):
            k = (np.abs(s_) < half + cfg.open_trim + reach) & (r_ >= lo_r) & (r_ < hi_r) & (z >= z0) & (z < z1)
            if face is not None:
                k &= face
            return float((np.bincount(ci[k], minlength=n) >= cfg.open_min_pts).mean())

        # both faces of the wall seen and returns all the way up the gap: a piece of
        # wall stage 1 missed, not a window (round 13: all 5 such gaps were false)
        glass_max = min(cfg.open_gap_glass_max, cfg.open_gap_paired_glass_max) if paired else cfg.open_gap_glass_max
        head_sh, glass_sh = share(cfg.open_gap_head_min, top), share(*cfg.open_gap_glass)
        last_shares[:] = [None, round(head_sh, 2), round(glass_sh, 2)]
        if head_sh < cfg.open_gap_window_share or glass_sh > glass_max:
            return False
        for flip in _reveal_sides(w):
            # below the sill: the wall, or what stands against it there (a radiator hides
            # the wall under most of Fire Brigade's windows), not reveal content; a
            # passage has neither
            sill_sh = share(*cfg.open_gap_sill, reach=cfg.open_gap_sill_reach, face=~_in_reveal(w, s_, cfg, flip))
            last_shares[0] = round(sill_sh, 2)
            if sill_sh < cfg.open_gap_window_share:
                continue
            # the measured opening must be window-shaped: a closed door leaf fills the
            # gap from the floor to its head, so its "sill" is its top (R13-2)
            ext = _window_extent(w, lo_r, hi_r, q, floor_z, cfg, flip)
            if _window_shaped(ext, cfg):
                last_shares.append(ext)
                return True
        return False

    last_shares: list = []
    trace: list = []

    def note(reason, w, end, a, **kw):
        if cfg.open_debug:
            trace.append({"wall": w.id, "end": end, "x": round(float(a[0]), 2), "y": round(float(a[1]), 2),
                          "reason": reason, **kw})

    prints = {w.id: footprint(w) for w in model.walls}
    done: set[frozenset] = set()
    c = model.cloud
    path = None
    if cfg.open_gap_walk and str(getattr(c, "file_station_kind", "")).startswith("trajectory") \
            and c.stations is not None and len(c.stations) > 1:
        path = c.stations[:, :2]
        step_ok = np.isfinite(path).all(1)
        step_ok = step_ok[:-1] & step_ok[1:] & (np.linalg.norm(path[1:] - path[:-1], axis=1) <= cfg.open_beam_walk_step)
    stats["gap_walk_doors"] = 0
    walk_centres: list[np.ndarray] = []  # one doorway, one door: a parallel twin wall is not bridged again
    for w in model.walls:
        u, v = w.unit, w.perp
        walk_r = None
        for end in ("r0", "r1"):
            if end not in w.unjoined:
                continue
            sgn = 1.0 if end == "r1" else -1.0
            r_end = w.r1 if end == "r1" else w.r0
            a = w.axis_offset() * u + r_end * v
            ray = LineString([a, a + sgn * cfg.open_gap[1] * v])
            hit = None
            for o in model.walls:
                if o is w:
                    continue
                x = ray.intersection(prints[o.id])
                if x.is_empty:
                    continue
                d = min(float(np.hypot(*(np.asarray(c) - a))) for g in getattr(x, "geoms", [x]) for c in g.coords)
                if hit is None or d < hit[0]:
                    hit = (d, o)
            if hit is None:
                note("nothing-ahead", w, end, a)
                continue
            gap, other = hit
            if abs((other.direction - w.direction + 90.0) % 180.0 - 90.0) >= 3.0:
                # a corner gap: too often not a door (round 9) — unless the scanner
                # itself walked through it (round 10)
                if path is None or not (cfg.open_gap[0] <= gap <= cfg.open_gap[1]):
                    note("corner", w, end, a, gap=round(gap, 2))
                    continue
                if walk_r is None:
                    s_st = path @ u - w.axis_offset()
                    sw = np.flatnonzero(step_ok & ((s_st[:-1] > 0) != (s_st[1:] > 0)))
                    tt = s_st[sw] / (s_st[sw] - s_st[sw + 1])
                    walk_r = (path[sw] + tt[:, None] * (path[sw + 1] - path[sw])) @ v
                lo_r, hi_r = sorted((r_end, r_end + sgn * gap))
                if not ((walk_r > lo_r) & (walk_r < hi_r)).any():
                    continue
                key = frozenset((w.id, other.id))
                centre = w.axis_offset() * u + (lo_r + hi_r) / 2 * v
                if key in done or any(np.hypot(*(centre - q)) < 0.6 for q in walk_centres):
                    continue
                done.add(key)
                walk_centres.append(centre)
                new_end = hi_r if end == "r1" else lo_r
                if end == "r1":
                    w.r1 = hi_r
                else:
                    w.r0 = lo_r
                w.unjoined = [e for e in w.unjoined if e != end]
                w.joins[end] = Join(other=other.id, face_offset=new_end, delta=new_end - r_end,
                                    new_end=new_end, trimmed=-gap, partner_covers=True)
                w.door_gaps.append((lo_r, hi_r))
                stats["gap_walk_doors"] += 1
                stats["gap_doors"] += 1
                continue
            lateral = abs(float(other.axis_offset() * other.unit @ u) - w.axis_offset())
            if lateral > max(w.thickness or 0.1, other.thickness or 0.1) / 2.0:
                note("offset", w, end, a, gap=round(gap, 2), lateral=round(lateral, 2))
                continue  # parallel but offset: a jog in the wall line, not one wall (R9-6)
            if not (cfg.open_gap[0] <= gap <= cfg.open_gap[1]):
                note("gap-range", w, end, a, gap=round(gap, 2))
                continue
            key = frozenset((w.id, other.id))
            if key in done:
                continue
            stats["gap_candidates"] += 1
            half = max(w.thickness or 0.1, 0.1) / 2.0
            n = max(int(round(gap / 0.1)), 1)
            lo_r, hi_r = sorted((r_end, r_end + sgn * gap))
            fl = floor_near(a + sgn * gap / 2 * v, gap / 2 + half + 0.6)
            s_ = fl @ u - w.axis_offset()
            r_ = fl @ v
            along = (r_ >= lo_r) & (r_ < hi_r)
            # inside the footprint, clear of its faces: a wall's base returns lie on
            # its faces, a doorway's threshold between them (R9-3)
            inner = along & (np.abs(s_) < max(half - cfg.open_gap_face_clear, 0.03))
            ci = np.clip(((r_[inner] - lo_r) / (gap / n)).astype(int), 0, n - 1)
            is_door = (np.bincount(ci, minlength=n) >= cfg.open_min_pts).mean() >= cfg.open_gap_floor
            # a passage has floor on both sides of the line (R9-3)
            is_door = is_door and ((along & (s_ > half) & (s_ < half + 0.5)).sum() >= cfg.open_min_pts
                                   and (along & (s_ < -half) & (s_ > -half - 0.5)).sum() >= cfg.open_min_pts)
            is_window = (not is_door and cfg.open_gap_windows
                         and (np.bincount(ci, minlength=n) >= cfg.open_min_pts).mean() < cfg.open_gap_floor
                         and window_gap(w, lo_r, hi_r, gap, half,
                                        paired="paired" in (w.pairing, other.pairing)))
            if cfg.open_debug:
                last_shares[:] = []
                if not is_door:
                    window_gap(w, lo_r, hi_r, gap, half, paired="paired" in (w.pairing, other.pairing))
                floor_share = float((np.bincount(ci, minlength=n) >= cfg.open_min_pts).mean())
                note("door" if is_door else ("window" if is_window else "evidence"), w, end, a, gap=round(gap, 2),
                     floor=round(floor_share, 2), sill_head_glass=list(last_shares))
            if not (is_door or is_window):
                continue
            done.add(key)
            if end == "r1":
                w.r1 = hi_r
            else:
                w.r0 = lo_r
            # both pieces now meet end to end: neither end is open (R9-2)
            w.unjoined = [e for e in w.unjoined if e != end]
            same = float(other.perp @ v) > 0
            facing = ({"r1": "r0", "r0": "r1"}[end]) if same else end
            other.unjoined = [e for e in other.unjoined if e != facing]
            new_end = hi_r if end == "r1" else lo_r
            w.joins[end] = Join(other=other.id, face_offset=new_end, delta=new_end - r_end,
                                new_end=new_end, trimmed=-gap, partner_covers=True)
            o_end = other.r0 if facing == "r0" else other.r1
            other.joins.setdefault(facing, Join(other=w.id, face_offset=o_end, delta=0.0, new_end=o_end))
            if is_door:
                w.door_gaps.append((lo_r, hi_r))
                stats["gap_doors"] += 1
            else:
                w.window_gaps.append((lo_r, hi_r))
                stats["gap_windows"] += 1
    if cfg.open_debug:
        stats["_gap_trace"] = trace
    return stats


WINDOW_CEILING_CLEAR = 0.15  # the head band ends this far below the wall's top (R13-3)


def _reveal_sides(w: Wall) -> tuple[bool, ...]:
    """Body-side readings to try: a one-sided wall's body side is inferred when the
    scan has no stations (Fire Brigade) and may be wrong, so both are tried; for a
    door leaf either reading fails (counted, it fills the gap to its top; not
    counted, it leaves no sill), so trying both admits no doors (R13-7)."""
    return (False,) if (w.pairing == "paired" or not w.body_side) else (False, True)


def _window_shaped(ext: tuple[float, float] | None, cfg: Config) -> bool:
    return ext is not None and ext[0] >= cfg.window_sill_min and ext[1] - ext[0] >= cfg.window_min_height


def _in_reveal(w: Wall, s_: np.ndarray, cfg: Config, flip: bool = False) -> np.ndarray:
    """Returns set back inside the wall's body, behind a face by more than
    `open_gap_reveal_clear` (s_ measured from the wall's axis along `w.unit`):
    between the two faces of a paired wall, or behind the measured face of a
    one-sided wall, toward its body. Glass, frames and blinds in a window's reveal
    lie there; the wall below the sill, a radiator and the lintel's face do not."""
    t = w.thickness or 0.1
    if w.pairing == "paired" or not w.body_side:
        return np.abs(s_) < t / 2.0 - cfg.open_gap_reveal_clear
    body = -w.body_side if flip else w.body_side
    face = -w.body_side * t / 2.0  # the measured face stays where it was measured
    return (s_ - face) * body > cfg.open_gap_reveal_clear


def _window_extent(w: Wall, a: float, b: float, pts: np.ndarray, floor_z: float,
                   cfg: Config, flip: bool = False) -> tuple[float, float] | None:
    """(sill, head) above the floor of a window gap a-b along `w`, per 0.1 m column,
    medians over the columns (review R13-1):
    sill — the top of the solid run of 0.1 m cells climbing from the lowest return in
           the sill band (wall or radiator, within `open_gap_sill_reach`); blinds above
           a cell of glass do not raise it
    head — the lowest return at or above `open_gap_head_min` within the wall's
           thickness, below the ceiling clearance; blinds below it do not lower it.
    Neither counts returns set back in the reveal (`_in_reveal`, R13-6)."""
    if not len(pts):
        return None
    top = (w.top_z if w.top_z is not None else w.z1) - floor_z - WINDOW_CEILING_CLEAR
    half = max(w.thickness or 0.1, 0.1) / 2.0 + cfg.open_trim
    s_, r_, z = pts[:, :2] @ w.unit - w.axis_offset(), pts[:, :2] @ w.perp, pts[:, 2] - floor_z
    along = (r_ >= a) & (r_ < b)
    ncol = max(int(np.ceil((b - a) / 0.1)), 1)
    col = np.clip(((r_ - a) / 0.1).astype(int), 0, ncol - 1)
    face = ~_in_reveal(w, s_, cfg, flip)  # reveal content does not make a sill or a head (R13-6)
    low = along & face & (np.abs(s_) < half + cfg.open_gap_sill_reach) & (z >= cfg.open_gap_sill[0]) & (z < top)
    high = along & face & (np.abs(s_) < half) & (z >= cfg.open_gap_head_min) & (z < top)
    nz = int(np.ceil(top / 0.1)) + 1
    sills, heads = [], []
    for c in range(ncol):
        zc = z[low & (col == c)]
        cells = np.zeros(nz, np.int32)
        np.add.at(cells, np.clip((zc / 0.1).astype(int), 0, nz - 1), 1)
        solid = cells >= cfg.open_min_pts
        k0 = int(np.ceil(cfg.open_gap_sill[0] / 0.1))
        start = next((k for k in range(k0, min(int(cfg.open_gap_sill[1] / 0.1) + 1, nz)) if solid[k]), None)
        if start is not None:
            k = start
            while k + 1 < nz and solid[k + 1]:
                k += 1
            sills.append((k + 1) * 0.1)
        zh = z[high & (col == c)]
        if len(zh):
            heads.append(float(zh.min()))
    if not sills or not heads:
        return None
    return float(np.median(sills)), float(np.median(heads))


def _gap_window(w: Wall, a: float, b: float, pts: np.ndarray, floor_z: float, cfg: Config) -> Opening:
    """A window between wall pieces (round 13), sill and head from `_window_extent`
    (the first body-side reading that is window-shaped, as when it was bridged)."""
    ext = None
    for flip in _reveal_sides(w):
        ext = _window_extent(w, a, b, pts, floor_z, cfg, flip)
        if _window_shaped(ext, cfg):
            break
    sill, head = ext if ext is not None else (cfg.open_gap_sill[1], cfg.open_gap_head_min)
    sill, head = floor_z + sill, floor_z + head
    o = Opening(along0=a, along1=b, sill_z=sill, head_z=max(head, sill + 0.1))
    o.source = "gap"
    o.kind = _classify(o, floor_z, cfg)
    o.derivation = "measured" if o.kind != "unresolved" else "unresolved"
    return o


def _gap_opening(w: Wall, a: float, b: float, pts: np.ndarray, floor_z: float, cfg: Config) -> Opening:
    """A doorway between wall pieces: sill at the floor, head at the first solid
    cells (two 0.1 m cells with returns in half the gap's 0.2 m columns) at or
    above the lowest door head within the wall's thickness, else the wall's top."""
    top = w.top_z if w.top_z is not None else w.z1
    u, v = w.unit, w.perp
    half = max(w.thickness or 0.1, 0.1) / 2.0 + cfg.open_trim
    head = top
    ncol = max(int(np.ceil((b - a) / cfg.open_col)), 1)
    nz = int((top - floor_z) / cfg.open_cell_z)
    if nz > 1 and len(pts):
        s_, r_, z = pts[:, :2] @ u - w.axis_offset(), pts[:, :2] @ v, pts[:, 2]
        m = (np.abs(s_) < half) & (r_ >= a) & (r_ < b) & (z >= floor_z) & (z < floor_z + nz * cfg.open_cell_z)
        if m.any():
            grid = np.zeros((ncol, nz), np.int32)
            ci = np.clip(((r_[m] - a) / cfg.open_col).astype(int), 0, ncol - 1)
            zi = ((z[m] - floor_z) / cfg.open_cell_z).astype(int)
            np.add.at(grid, (ci, zi), 1)
            row = (grid >= cfg.open_min_pts).mean(axis=0) >= 0.5
            lo = int(round(cfg.door_head[0] / cfg.open_cell_z))
            solid = np.flatnonzero(row[lo:-1] & row[lo + 1:])
            if len(solid):
                head = floor_z + (int(solid[0]) + lo) * cfg.open_cell_z
    o = Opening(along0=a, along1=b, sill_z=floor_z, head_z=head)
    o.source = "gap"
    # no head below the top: the doorway reaches the ceiling (TUB1); classed on
    # its floor sill and width, with the hole kept to the wall's top (R9-1)
    probe = Opening(along0=a, along1=b, sill_z=floor_z, head_z=min(head, floor_z + cfg.door_head[1]))
    o.kind = _classify(probe, floor_z, cfg)
    o.derivation = "measured" if o.kind != "unresolved" else "unresolved"
    return o


def beam_runs(model: Model, cfg: Config = Config()) -> dict[str, list[tuple[str, float, float, float, float]]]:
    """Openings seen through: (kind, a, b, z5, z95) per wall id (round 10).

    Needs a scanner position per point. A return beyond a wall, measured from a
    scanner on its near side, reached it through an opening: in plan the beam
    crosses the wall's axis there. Per 0.1 m cell along the wall the crossings are
    counted; cells with >= `open_beam_min` form runs (a one-cell hole is closed).
    A run whose beams all pass above `open_beam_window_z` is a window; one the
    scanner itself walked through (a trajectory), with beams down to the floor, a
    door. z5/z95 are heights above the floor where the beams cross the wall, from
    a nominal sensor height when station heights are not trusted (R10-1)."""
    out: dict[str, list[tuple[str, float, float, float, float]]] = {}
    c = model.cloud
    if not cfg.open_beam or c is None or model.levels is None or not model.walls:
        return out
    rows = c.station_rows()
    if rows is None:
        return out
    stations, idx = rows
    floor_z = float(model.levels.floor_z)
    zcap = floor_z + cfg.open_beam_zcap
    ok_st = np.isfinite(stations).all(1)
    # stations of this storey: a scanner on another storey sees few of its returns
    # (through a stairwell); one with under open_beam_station_share of the median
    # station's returns here is left out, for beams and for the walk (R10-3)
    counts = np.bincount(idx[idx >= 0], minlength=len(stations))
    on_storey = ok_st & (counts > 0)  # the walk: any station that measured here
    if counts.any():
        ok_st &= counts >= cfg.open_beam_station_share * np.median(counts[counts > 0])
    if c.stations_z_known:
        ok_st &= np.abs(stations[:, 2] - floor_z - 1.5) < 2.0
    keep = (idx >= 0) & (c.points[:, 2] > floor_z + 0.1) & (c.points[:, 2] < zcap)
    keep[keep] = ok_st[idx[keep]]
    if not keep.any():
        return out
    P = c.points[keep].astype(np.float32)
    sid = idx[keep]
    st2 = stations[:, :2]
    sh = (stations[:, 2] - floor_z) if c.stations_z_known else np.full(len(stations), cfg.open_beam_sensor_h)
    walked = str(getattr(c, "file_station_kind", "")).startswith("trajectory")
    cell = 0.1
    for w in model.walls:
        if w.r1 - w.r0 < 0.3:
            continue  # shorter than any run the cover rule would let through
        u, v, off = w.unit, w.perp, w.axis_offset()
        half = max(w.thickness or 0.1, 0.1) / 2.0
        top = min((w.top_z if w.top_z is not None else w.z1) - 0.1, zcap)
        sp_st = st2 @ u - off
        sp = sp_st[sid]
        pp = P[:, 0] * u[0] + P[:, 1] * u[1] - off
        cross = ((sp > 0) != (pp > 0)) & (P[:, 2] < top)
        cross &= (np.abs(sp) > max(half, cfg.open_beam_sdist)) & (np.abs(pp) > half + 0.1)
        if not cross.any():
            continue
        Pc, Sc, sc, pc = P[cross], st2[sid[cross]], sp[cross], pp[cross]
        # grazing beams: a small station error moves their crossing far (R10-2)
        seg = np.hypot(Pc[:, 0] - Sc[:, 0], Pc[:, 1] - Sc[:, 1])
        steep = np.abs(sc - pc) >= cfg.open_beam_incidence * seg
        Pc, Sc, sc, pc = Pc[steep], Sc[steep], sc[steep], pc[steep]
        t = sc / (sc - pc)
        r = (Sc + t[:, None] * (Pc[:, :2] - Sc)) @ v
        inw = (r >= w.r0) & (r < w.r1)
        if not inw.any():
            continue
        h0 = sh[sid[cross][steep][inw]]
        pz = Pc[inw, 2] - floor_z
        zc = h0 + t[inw] * (pz - h0)  # beam height at the wall (R10-1)
        r = r[inw]
        n = max(int(np.ceil((w.r1 - w.r0) / cell)), 1)
        ci = ((r - w.r0) / cell).astype(int).clip(0, n - 1)
        mark = np.bincount(ci, minlength=n) >= cfg.open_beam_min
        mk = mark.copy()
        mk[1:-1] |= mark[:-2] & mark[2:]
        walk_r = None
        k = 0
        while k < n:
            if not mk[k]:
                k += 1
                continue
            j = k
            while j < n and mk[j]:
                j += 1
            a, b = w.r0 + k * cell, min(w.r0 + j * cell, w.r1)  # clipped to the wall (R10-6)
            if b - a >= cfg.open_beam_max_cover * (w.r1 - w.r0):
                # seen through over (nearly) its whole length: not a wall with an
                # opening but a false wall across one (TUB1 W46/W48, TUB2 W50); beams
                # down to the floor mean nothing stands there at all
                sel = (ci >= k) & (ci < j)
                if float(np.percentile(pz[sel], 5)) < cfg.open_beam_door_z:
                    out.setdefault(w.id, []).append(("nowall", a, b, 0.0, 0.0))
                k = j
                continue
            sel = (ci >= k) & (ci < j)
            # kind from the far returns' heights (measured: a door's reach the floor,
            # a window's stay above ~1 m); the opening's sill/head from the beams'
            # heights at the wall (R10-1)
            fz5 = float(np.percentile(pz[sel], 5))
            z5, z95 = float(np.percentile(zc[sel], 5)), float(np.percentile(zc[sel], 95))
            kind = None
            if fz5 >= cfg.open_beam_window_z and \
                    cfg.open_beam_window_width[0] <= b - a <= cfg.open_beam_window_width[1]:
                kind = "window"
            elif walked and fz5 < cfg.open_beam_door_z \
                    and cfg.open_beam_door_width[0] <= b - a <= cfg.open_beam_door_width[1]:
                if walk_r is None:  # where the path crosses this wall's line (lazy, R10-8)
                    good = on_storey[:-1] & on_storey[1:] & (np.linalg.norm(st2[1:] - st2[:-1], axis=1)
                                                     <= cfg.open_beam_walk_step)
                    sw = np.flatnonzero(good & ((sp_st[:-1] > 0) != (sp_st[1:] > 0)))
                    tt = sp_st[sw] / (sp_st[sw] - sp_st[sw + 1])
                    walk_r = (st2[sw] + tt[:, None] * (st2[sw + 1] - st2[sw])) @ v
                if ((walk_r >= a - 0.2) & (walk_r < b + 0.2)).any():
                    kind = "door"
            if kind:
                out.setdefault(w.id, []).append((kind, a, b, z5, z95))
            k = j
    return out


def _beam_opening(w: Wall, kind: str, a: float, b: float, z5: float, z95: float,
                  pts: np.ndarray, floor_z: float, cfg: Config) -> Opening:
    """An opening seen through. A door is read as a doorway between pieces is
    (`_gap_opening`). A window's sill is the top of the solid wall (rows of 0.1 m
    cells with returns in half the 0.2 m columns, inside the wall's thickness)
    below its lowest beam, its head the foot of the solid wall above its highest;
    with no solid wall there, the beams' own heights."""
    if kind == "door":
        o = _gap_opening(w, a, b, pts, floor_z, cfg)
        o.source = "beam"
        return o
    top = w.top_z if w.top_z is not None else w.z1
    u, v = w.unit, w.perp
    half = max(w.thickness or 0.1, 0.1) / 2.0 + cfg.open_trim
    nz = max(int((top - floor_z) / cfg.open_cell_z), 1)
    ncol = max(int(np.ceil((b - a) / cfg.open_col)), 1)
    sill, head = floor_z + z5, floor_z + z95
    if len(pts):
        s_, r_, z = pts[:, :2] @ u - w.axis_offset(), pts[:, :2] @ v, pts[:, 2]
        m = (np.abs(s_) < half) & (r_ >= a) & (r_ < b) & (z >= floor_z) & (z < floor_z + nz * cfg.open_cell_z)
        if m.any():
            grid = np.zeros((ncol, nz), np.int32)
            np.add.at(grid, (np.clip(((r_[m] - a) / cfg.open_col).astype(int), 0, ncol - 1),
                             ((z[m] - floor_z) / cfg.open_cell_z).astype(int)), 1)
            row = (grid >= cfg.open_min_pts).mean(axis=0) >= 0.5
            lo, hi = int(z5 / cfg.open_cell_z), int(np.ceil(z95 / cfg.open_cell_z))
            below = np.flatnonzero(row[:max(lo, 0)])
            above = np.flatnonzero(row[min(hi, nz):]) + min(hi, nz)
            if len(below):
                sill = floor_z + (int(below[-1]) + 1) * cfg.open_cell_z
            if len(above):
                head = floor_z + int(above[0]) * cfg.open_cell_z
            else:
                head = max(head, top)
    o = Opening(along0=a, along1=b, sill_z=sill, head_z=max(head, sill + cfg.window_min_height))
    o.source = "beam"
    o.kind = "window" if sill - floor_z >= cfg.window_sill_min else _classify(o, floor_z, cfg)
    o.derivation = "measured" if o.kind != "unresolved" else "unresolved"
    return o


def _overlap(a: tuple[int, int], b: tuple[int, int]) -> float:
    inter = min(a[1], b[1]) - max(a[0], b[0])
    return inter / max(min(a[1] - a[0], b[1] - b[0]), 1)


def _classify(o: Opening, floor_z: float, cfg: Config) -> str:
    sill, head = o.sill_z - floor_z, o.head_z - floor_z
    if sill <= cfg.door_sill_max and cfg.door_head[0] <= head <= cfg.door_head[1] \
            and cfg.door_width[0] <= o.width <= cfg.door_width[1]:
        return "door"
    if sill >= cfg.window_sill_min and o.height >= cfg.window_min_height:
        return "window"
    return "unresolved"


def find_openings(model: Model, cfg: Config = Config()) -> dict:
    stats = {"faces": 0, "openings": 0, "doors": 0, "windows": 0, "unresolved": 0,
             "rejected_width": 0, "rejected_occluded": 0, "beam_runs": 0, "from_beam": 0, "beam_dropped": 0}
    if model.cloud is None or model.levels is None or not model.walls:
        return stats
    floor_z = float(model.levels.floor_z)
    top = max((w.top_z if w.top_z is not None else w.z1) for w in model.walls)
    p = model.cloud.points
    keep = (p[:, 2] > floor_z - 0.05) & (p[:, 2] < top + 0.1)
    pts = p[keep]
    if len(pts) == 0:
        return stats
    tree = cKDTree(pts[:, :2])
    beams = beam_runs(model, cfg)
    stats["beam_runs"] = sum(len(x) for x in beams.values())
    for w in model.walls:
        w.openings = []
        found: list[Opening] = []
        gap_doors: list[Opening] = []
        for a, b in w.door_gaps:
            mid = w.axis_offset() * w.unit + (a + b) / 2 * w.perp
            near = tree.query_ball_point(mid, (b - a) / 2 + 0.5)
            gap_doors.append(_gap_opening(w, a, b, pts[np.asarray(near, dtype=np.int64)], floor_z, cfg))
            stats["from_gap"] = stats.get("from_gap", 0) + 1
        for a, b in w.window_gaps:
            mid = w.axis_offset() * w.unit + (a + b) / 2 * w.perp
            near = tree.query_ball_point(mid, (b - a) / 2 + 0.5)
            gap_doors.append(_gap_window(w, a, b, pts[np.asarray(near, dtype=np.int64)], floor_z, cfg))
            stats["from_gap"] = stats.get("from_gap", 0) + 1
        for f in w.faces:
            a, b = f.r0, f.r1
            if not f.bridged and not cfg.open_void_search:
                continue
            t = np.deg2rad(f.direction)
            u, v = np.array([np.cos(t), np.sin(t)]), np.array([-np.sin(t), np.cos(t)])
            centre = (f.k * (a + b) / 2 + f.c) * u + (a + b) / 2 * v
            near = tree.query_ball_point(centre, (b - a) / 2 + cfg.open_occluder + 0.1)
            if not near:
                continue
            stats["faces"] += 1
            for o in _face_voids(f, w, pts[np.asarray(near)], floor_z, cfg, stats):
                # the same opening seen on the other face: one opening over the
                # union, the classed reading preferred (R8-8)
                twin = next((x for x in found if min(x.along1, o.along1) - max(x.along0, o.along0) > 0), None)
                if twin is None:
                    found.append(o)
                    continue
                twin.along0, twin.along1 = min(twin.along0, o.along0), max(twin.along1, o.along1)
                if twin.kind == "unresolved" and o.kind != "unresolved":
                    twin.kind, twin.sill_z, twin.head_z = o.kind, o.sill_z, o.head_z
                if twin.kind != "unresolved" and o.kind == twin.kind:
                    twin.derivation = "measured-both-faces"
        # clip once to the wall as joined, then class again on what is left (R8-7)
        kept = list(gap_doors)
        for o in found:
            if any(min(g.along1, o.along1) - max(g.along0, o.along0) >= 0.5 * min(g.width, o.width)
                   for g in gap_doors):
                continue  # the same doorway, already taken from the gap (R9-5)
            o.along0, o.along1 = max(o.along0, w.r0), min(o.along1, w.r1)
            if o.width < cfg.open_min_keep or o.height <= 0.3:
                continue
            o.kind = _classify(o, floor_z, cfg)
            o.derivation = "unresolved" if o.kind == "unresolved" else (
                o.derivation if o.derivation.startswith("measured") else "measured")
            kept.append(o)
        # openings seen through (round 10): taken where nothing else was found
        for kind, a, b, z5, z95 in beams.get(w.id, []):
            if kind == "nowall":
                continue
            # the same opening already read: kept, unless it was left unresolved
            # and the beams class it (R10-4)
            same = [x for x in kept if min(x.along1, b) - max(x.along0, a) >= 0.5 * min(x.width, b - a)]
            if any(x.kind != "unresolved" for x in same) or \
                    any(min(x.along1, b) - max(x.along0, a) > 0 for x in kept if x not in same):
                continue
            mid = w.axis_offset() * w.unit + (a + b) / 2 * w.perp
            near = tree.query_ball_point(mid, (b - a) / 2 + 0.5)
            o = _beam_opening(w, kind, max(a, w.r0), min(b, w.r1), z5, z95,
                              pts[np.asarray(near, dtype=np.int64)], floor_z, cfg)
            if o.width < cfg.open_min_keep or o.kind != kind:
                stats["beam_dropped"] += 1  # e.g. a walk-through that does not read as a door
                continue
            kept = [x for x in kept if x not in same]
            kept.append(o)
            stats["from_beam"] += 1
        w.openings = sorted(kept, key=lambda o: o.along0)
        for o in w.openings:
            stats["openings"] += 1
            stats[{"door": "doors", "window": "windows"}.get(o.kind, "unresolved")] += 1
    return stats


def drop_seen_through(model: Model, cfg: Config) -> int:
    """Walls the scanner saw through, floor to head, over most of their length
    (round 10): a wall drawn across a doorway or open space. Dropped when
    `open_beam_drop_walls`."""
    if not cfg.open_beam_drop_walls:
        return 0
    runs = beam_runs(model, cfg)
    gone = {wid for wid, rs in runs.items() if any(r[0] == "nowall" for r in rs)}
    model.walls = [w for w in model.walls if w.id not in gone]
    return len(gone)


def run(model: Model, cfg: Config = Config()) -> None:
    dropped = drop_seen_through(model, cfg)
    gaps = model.meta.get("gap_door_stats")
    if gaps is None:  # not already bridged before the rooms (open_gap_before_rooms)
        gaps = model.meta["gap_door_stats"] = bridge_door_gaps(model, cfg)
    if "_gap_trace" in gaps:
        model.meta["gap_trace"] = gaps.pop("_gap_trace")
    stats = find_openings(model, cfg)
    if "_occluded" in stats:
        model.meta["occluded_voids"] = stats.pop("_occluded")
    model.meta["opening_stats"] = {**stats, **gaps, "walls_seen_through": dropped}
