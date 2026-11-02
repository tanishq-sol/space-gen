"""Stage 3b — rooms from free space: the floor the scan saw, split at doorways.

Rooms traced from wall faces (stage 3) need every wall around a room found and
every corner joined; one missed wall or one open doorway loses the room. The
floor itself is evidence that does not depend on that: a room is a connected
piece of seen floor, and two rooms meet only through a doorway.

1. Seen floor: cells (`room_fs_cell`) with returns on the floor plane (±`side_floor_tol`),
   closed over one cell (scanner ring gaps); holes smaller than `room_fs_hole_max`
   are filled (furniture hides the floor beneath it; a larger hole is space the
   scan never reached and stays out).
2. Free space: seen floor minus every wall footprint (grown one cell).
3. Seeds: free space eroded by half `room_fs_door` — a doorway narrower than
   that disappears, so the rooms either side become separate seeds; a seed
   smaller than `room_fs_seed_min` is a niche, not a room.
4. Each seed regrows through free space (geodesic dilation) to claim its floor.
5. A region becomes a room when it is at least `room_min_area` and less than
   `room_fs_overlap_max` of it already lies in a wall-traced room. Its outline
   is the cell boundary, simplified; it is marked `derivation = "free-space"`
   and carries a `closure_gaps` entry of kind `free-space`, so writers present it
   as an inferred outline, never as a measured one.

Leak risk: where a wall was never found, two rooms share one region. The region
is then too large or spans two wall-traced rooms; `room_max_area` and the
overlap test reject the worst cases, and every free-space room says what it is.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage
from shapely import contains_xy
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from ..config import Config
from ..model import Model, Room
from .s3_rooms import footprint, sunken_floors


def _floor_returns(points: np.ndarray, levels, sunk: list, cfg: Config) -> tuple[np.ndarray, np.ndarray]:
    """Plan positions of floor returns, and which lie on a sunken floor. Each
    return within `side_floor_tol` of a floor level goes to the nearest level (a
    plane 0.08 m down shares part of the storey floor's band); a sunken floor's
    returns count only inside that plane's own validated footprint (round 19).
    Without sunken floors this is |z - floor_z| < side_floor_tol, as before."""
    tol = cfg.side_floor_tol
    zs = np.array([levels.floor_z] + [p.z_fit for p in sunk])
    z = points[:, 2]
    cand = np.flatnonzero((z > zs.min() - tol) & (z < zs.max() + tol))
    d = np.abs(z[cand, None] - zs[None, :])
    lvl = d.argmin(axis=1)
    ok = d[np.arange(len(cand)), lvl] < tol
    cand, lvl = cand[ok], lvl[ok]
    keep = lvl == 0
    for k, p in enumerate(sunk, start=1):
        on = np.flatnonzero(lvl == k)
        ij = np.floor((points[cand[on], :2] - levels.origin) / levels.cell).astype(np.int64)
        key = ij[:, 0] * 1_000_003 + ij[:, 1]  # as geometry.cell_overlap
        own = p.cells[:, 0].astype(np.int64) * 1_000_003 + p.cells[:, 1]
        keep[on[np.isin(key, own)]] = True
    return points[cand[keep], :2], lvl[keep] > 0


def _grid(points: np.ndarray, levels, sunk: list, cfg: Config):
    """Seen-floor cells: floor returns (`_floor_returns`), >= `room_fs_min_returns`
    per cell, isolated specks (< 1 m2 components) dropped, cropped to what is
    left. One stray return 2 km away must not make the grid 2 km wide (review
    R4-1); a grid still above `room_fs_max_cells` is refused, not allocated.
    With sunken floors, also each seen cell's level: `upper` (the storey floor)
    or `lower`, on the level most of its returns lie on. An island of either
    smaller than a niche (`room_fs_seed_min`) takes its surroundings' level: a
    plinth, a base, a drain or noise, not a change of floor (round 19)."""
    cell = cfg.room_fs_cell
    band, low = _floor_returns(points, levels, sunk, cfg)
    if len(band) == 0:
        return None
    ij = np.floor(band / cell).astype(np.int64)
    keys, inv, counts = np.unique(ij, axis=0, return_inverse=True, return_counts=True)
    n_upper = np.bincount(inv.ravel(), weights=~low, minlength=len(keys))
    good = counts >= cfg.room_fs_min_returns
    keys, n_upper, counts = keys[good], n_upper[good], counts[good]
    if len(keys) == 0:
        return None
    # specks: cluster the occupied cells coarsely (1 m blocks) and keep blocks
    # connected to enough floor
    blocks, inv, bcount = np.unique(keys // 10, axis=0, return_inverse=True, return_counts=True)
    big = bcount[inv.ravel()] >= 5
    keys, n_upper, counts = keys[big], n_upper[big], counts[big]
    if len(keys) == 0:
        return None
    origin = keys.min(axis=0) - 2
    keys = keys - origin
    shape = tuple(int(v) for v in keys.max(axis=0) + 3)
    if shape[0] * shape[1] > cfg.room_fs_max_cells:
        return None
    seen = np.zeros(shape, bool)
    seen[keys[:, 0], keys[:, 1]] = True
    if not low.any():
        return seen, origin, None, None
    upper = np.zeros(shape, bool)
    k = keys[2 * n_upper > counts]
    upper[k[:, 0], k[:, 1]] = True
    lower = seen & ~upper
    small = cfg.room_fs_seed_min / (cell * cell)

    def tiny(grid: np.ndarray, other: np.ndarray) -> np.ndarray:
        """Islands of `grid` under the niche size that touch `other`: a speck of
        floor seen on its own, nowhere near the other level, keeps its level."""
        lab, n = ndimage.label(grid, np.ones((3, 3)))
        touch = np.zeros(n + 1, bool)
        touch[lab[grid & ndimage.binary_dilation(other, np.ones((3, 3)))]] = True
        return ((np.bincount(lab.ravel(), minlength=n + 1) < small) & touch)[lab] & grid

    # both from the original labels (review R19-11)
    t_up, t_low = tiny(upper, lower), tiny(lower, upper)
    return seen, origin, (upper & ~t_up) | t_low, (lower & ~t_low) | t_up


def _polygon(mask: np.ndarray, origin: np.ndarray, cell: float) -> Polygon | None:
    """The cells of `mask` as one polygon (largest part), from row runs."""
    rects = []
    for i in np.flatnonzero(mask.any(axis=1)):
        row = mask[i].astype(np.int8)
        d = np.diff(np.r_[0, row, 0])
        for a, b in zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)):
            # both edges from integer cell indices, so neighbouring rows share exact
            # coordinates (x0 + cell drifts and left slivers between rows)
            rects.append(box((origin[0] + i) * cell, (origin[1] + a) * cell,
                             (origin[0] + i + 1) * cell, (origin[1] + b) * cell))
    if not rects:
        return None
    g = unary_union(rects)
    if g.geom_type == "MultiPolygon":
        g = max(g.geoms, key=lambda p: p.area)
    g = g.simplify(cell * 0.75, preserve_topology=True)
    if not g.is_valid:
        g = g.buffer(0)
        if g.geom_type == "MultiPolygon":
            g = max(g.geoms, key=lambda p: p.area)
    return g if g.geom_type == "Polygon" and not g.is_empty else None


def free_space_rooms(model: Model, traced: list[Room], cfg: Config = Config(),
                     debug: dict | None = None) -> tuple[list[Room], dict]:
    stats = {"regions": 0, "added": 0, "rejected_small": 0, "rejected_large": 0, "rejected_traced": 0,
             "door_cuts": 0, "small_seeds": 0, "small_seeds_dropped": 0}
    if model.cloud is None or model.levels is None:
        return [], stats
    cell = cfg.room_fs_cell
    candidates: list[dict] = []
    sunk = sunken_floors(model.levels, cfg, candidates)
    g = _grid(model.cloud.points, model.levels, sunk, cfg)
    if g is None:
        stats["skipped"] = "no floor grid (no floor returns, or larger than room_fs_max_cells)"
        return [], stats
    seen, origin, upper, lower = g
    if candidates:
        stats["sunken_candidates"] = candidates
    if sunk:
        stats["sunken_floors"] = [{"z": round(p.z_fit, 3), "area_m2": round(p.area_m2, 1)} for p in sunk]
    raw = seen
    # bridge one-cell gaps (scanner rings) only: a wider closing also erases the
    # strip a wall stands on whenever that wall was not found, merging two rooms
    seen = ndimage.binary_closing(seen, np.ones((3, 3)), border_value=0)
    holes = ndimage.binary_fill_holes(seen) & ~seen
    lab, n = ndimage.label(holes)
    if n:
        sizes = ndimage.sum(holes, lab, index=np.arange(1, n + 1)) * cell * cell
        small = np.r_[False, sizes <= cfg.room_fs_hole_max]
        seen |= small[lab]
    # a step down between the storey floor and a sunken floor parts rooms like a
    # wall (round 19: Grainger's sunken gallery and the room beside it, whose wall
    # between them was not found): lower cells next to upper ones, and the cells
    # the closing above filled in an unseen riser between them (review R19-9)
    step = np.zeros(seen.shape, bool)
    if upper is not None:
        step = lower & ndimage.binary_dilation(upper, np.ones((3, 3)))
        step |= (seen & ~raw & ndimage.binary_dilation(upper, np.ones((5, 5)))
                 & ndimage.binary_dilation(lower, np.ones((5, 5))))

    walls = np.zeros(seen.shape, bool)
    # doorways found between wall pieces (round 12): the free space is cut across
    # them so the rooms either side come apart; the walls themselves are untouched
    # here (extending them before the rooms are traced cost TUB1 two rooms)
    door_walls = []
    if cfg.room_fs_gap_doors and len(model.walls) > 1 and "gap_door_stats" not in model.meta:
        from dataclasses import replace as dc_replace

        from .s4_openings import bridge_door_gaps

        # shallow copies: bridging changes only these fields (faces stay shared, R12-3)
        probe = [dc_replace(w, unjoined=list(w.unjoined), joins=dict(w.joins), door_gaps=list(w.door_gaps),
                            window_gaps=list(w.window_gaps))
                 for w in model.walls]
        before = {w.id: len(w.door_gaps) for w in model.walls}
        # door cuts only: the window tests (and their point index) are not needed here
        bridge_door_gaps(Model(cloud=model.cloud, levels=model.levels, walls=probe),
                         dc_replace(cfg, open_gap_windows=False))
        door_walls = [w for w in probe if len(w.door_gaps) > before[w.id]]  # new cuts only (R12-4)
        stats["door_cuts"] = sum(len(w.door_gaps) - before[w.id] for w in door_walls)
    for w in [*model.walls, *door_walls]:
        # grown by half a cell: a wall thinner than a cell must still cover the
        # cell centres it crosses (review R4-3)
        f = footprint(w).buffer(cell * 0.5, join_style="mitre")
        if f.is_empty:
            continue
        x0, y0, x1, y1 = f.bounds
        i0 = max(int(np.floor(x0 / cell)) - origin[0] - 1, 0)
        i1 = min(int(np.floor(x1 / cell)) - origin[0] + 2, seen.shape[0])
        j0 = max(int(np.floor(y0 / cell)) - origin[1] - 1, 0)
        j1 = min(int(np.floor(y1 / cell)) - origin[1] + 2, seen.shape[1])
        if i1 > i0 and j1 > j0:
            X, Y = np.meshgrid((origin[0] + np.arange(i0, i1) + 0.5) * cell,
                               (origin[1] + np.arange(j0, j1) + 0.5) * cell, indexing="ij")
            walls[i0:i1, j0:j1] |= contains_xy(f, X, Y)
    free = seen & ~walls & ~step
    if step.any():
        stats["step_m"] = round(float(step.sum()) * cell, 1)

    # seeds: erode at widening radii (doorway first, then wider constrictions);
    # a region that splits into two or more substantial parts at a wider erosion is
    # several rooms joined through a constriction (a wide opening, a missed wall
    # with its jambs standing). Leaves of that split tree are the room seeds
    # (morphological room segmentation, after Bormann et al. 2016).
    radii = [cfg.room_fs_door / 2 + k * 0.25 for k in range(cfg.room_fs_levels)]
    # erosion by a disk of radius q cells == distance to the nearest non-free cell
    # above q: one distance transform serves every level
    dist = ndimage.distance_transform_edt(np.pad(free, 1))[1:-1, 1:-1]
    eroded = [dist > max(int(round(rad / cell)), 1) for rad in radii]
    # small seeds (closets, WCs: a 2 x 2 m room erodes to ~1 m2) are kept for now
    # and judged after regrowth by how much of their outline is wall (round 12)
    min_cells = min(cfg.room_fs_seed_min, cfg.room_fs_small_seed_min) / (cell * cell)
    big_cells = cfg.room_fs_seed_min / (cell * cell)
    seeds = np.zeros(free.shape, np.int32)
    n_seeds = 0

    def split(region: np.ndarray, level: int) -> None:
        """Seed `region` (a component at `level`): recurse while it splits."""
        nonlocal n_seeds
        kids: list[np.ndarray] = []
        if level + 1 < len(eroded):
            # work inside the region's bounding box: labelling the whole floor grid
            # at every step of the recursion is what made this slow
            sl = ndimage.find_objects(region.astype(np.int8))[0]
            lab, n = ndimage.label(eroded[level + 1][sl] & region[sl])
            for i in range(1, n + 1):
                sub = lab == i
                if sub.sum() >= big_cells:  # splits judged as before round 12
                    k = np.zeros(region.shape, bool)
                    k[sl] = sub
                    kids.append(k)
        if len(kids) >= 2:
            for k in kids:
                split(k, level + 1)
            return
        before = n_seeds
        if len(kids) == 1:
            split(kids[0], level + 1)
            if n_seeds > before + 1:
                return  # it split further in: those are the seeds
            seeds[seeds == n_seeds] = 0
            n_seeds = before
        # one room: seed it with the whole region at the level it stood alone,
        # so the regrown boundary sits at the constriction, not halfway between cores
        n_seeds += 1
        seeds[region] = n_seeds

    core = eroded[0]
    lab0, n0 = ndimage.label(core)
    counts0 = np.bincount(lab0.ravel(), minlength=n0 + 1)
    for i, sl in enumerate(ndimage.find_objects(lab0), start=1):
        if counts0[i] < min_cells:
            continue
        c = np.zeros(core.shape, bool)
        c[sl] = lab0[sl] == i
        if counts0[i] >= big_cells:
            split(c, 0)
        else:  # a small room's own core (closet, WC): judged after regrowth
            n_seeds += 1
            seeds[c] = n_seeds
    if n_seeds == 0:
        return [], stats
    r = max(int(round(radii[-1] / cell)), 1)

    def regrow(sd: np.ndarray) -> np.ndarray:
        """Each seed regrows through free space; where two meet, the higher label wins."""
        lb = sd.copy()
        for _ in range(4 * r + 50):
            todo = free & (lb == 0)
            if not todo.any():
                break
            grown = ndimage.grey_dilation(lb, footprint=ndimage.generate_binary_structure(2, 1))
            new = todo & (grown > 0)
            if not new.any():
                break
            lb[new] = grown[new]
        return lb

    label = regrow(seeds)
    # a small seed stands as a room only if walls bound most of its region (a closet
    # is walled in; a corner of a big room cut off by furniture is not): else its
    # seed is dropped and the neighbours regrow over it (round 12)
    sizes = np.bincount(seeds.ravel(), minlength=n_seeds + 1)
    small = [k for k in range(1, n_seeds + 1) if 0 < sizes[k] < big_cells]
    if small:
        # judged together on the first regrowth, then dropped at once (order-free).
        # The edge includes the doorway to the neighbour and any furniture holes, so
        # the share is conservative; door cuts count as wall.
        near_wall = ndimage.binary_dilation(walls | step, iterations=2)  # a step bounds too
        boxes = ndimage.find_objects(label)
        dropped = 0
        for k in small:
            if k > len(boxes) or boxes[k - 1] is None:
                continue
            sl = tuple(slice(max(b.start - 1, 0), b.stop + 1) for b in boxes[k - 1])
            m_ = label[sl] == k
            edge = m_ & ~ndimage.binary_erosion(m_, border_value=0)
            if edge.sum() == 0 or (edge & near_wall[sl]).sum() / edge.sum() < cfg.room_fs_small_wall_share:
                seeds[seeds == k] = 0
                dropped += 1
        stats["small_seeds"], stats["small_seeds_dropped"] = len(small), dropped
        if dropped:
            label = regrow(seeds)

    if debug is not None:
        debug.update(seen=seen, walls=walls, step=step, free=free, core=core, label=label, origin=origin)
    stats["unlabelled_free_m2"] = round(float((free & (label == 0)).sum()) * cell * cell, 2)
    # Floor hidden under furniture along the walls (shelves, desks, cabinets) was
    # never seen, so a room stops short of its walls. Grow each room on into
    # unseen, non-wall cells, at most `room_fs_reach` and never through a wall or
    # into another room (Fire Brigade: our rooms covered 51-69 % of the reference
    # rooms). The reach keeps a room from spilling out where an exterior wall was missed.
    # only towards a wall: hidden floor within `room_fs_reach` of a wall cell. Open
    # unscanned space with no wall near it stays out of the room.
    if walls.any():
        to_wall = ndimage.distance_transform_edt(~walls) * cell
        hidden = ~seen & ~walls & (to_wall <= cfg.room_fs_reach)
    else:
        hidden = np.zeros_like(seen)
    cross = ndimage.generate_binary_structure(2, 1)
    before = int((label > 0).sum())
    for _ in range(max(int(round(cfg.room_fs_reach / cell)), 0)):
        grown = ndimage.grey_dilation(label, footprint=cross)
        new = hidden & (label == 0) & (grown > 0)
        if not new.any():
            break
        label[new] = grown[new]
    stats["hidden_floor_added_m2"] = round((int((label > 0).sum()) - before) * cell * cell, 2)
    traced_polys = [Polygon(t.polygon).buffer(0) for t in traced if len(t.polygon) >= 3]
    traced_union = unary_union(traced_polys) if traced_polys else Polygon()
    rooms: list[Room] = []
    for k in np.unique(label[label > 0]):
        stats["regions"] += 1
        mask = label == k
        area = float(mask.sum()) * cell * cell
        if area < cfg.room_min_area:
            stats["rejected_small"] += 1
            continue
        if area > cfg.room_max_area:
            stats["rejected_large"] += 1
            continue
        poly = _polygon(mask, origin, cell)
        if poly is None:
            stats["rejected_invalid"] = stats.get("rejected_invalid", 0) + 1
            continue
        if poly.area < cfg.room_min_area:
            stats["rejected_small"] += 1
            continue
        if not traced_union.is_empty and poly.intersection(traced_union).area > cfg.room_fs_overlap_max * poly.area:
            stats["rejected_traced"] += 1
            continue
        if not traced_union.is_empty:
            poly = poly.difference(traced_union)
            if poly.geom_type == "MultiPolygon":
                poly = max(poly.geoms, key=lambda p: p.area)
            if poly.is_empty or poly.area < cfg.room_min_area:
                stats["rejected_small"] += 1
                continue
        if poly.interiors:
            # a core or a traced room inside the region: rooms carry no holes, so
            # the outline is the exterior and the area the true floor area; say so
            stats["with_holes"] = stats.get("with_holes", 0) + 1
        rooms.append(Room(
            id="", polygon=[(float(x), float(y)) for x, y in poly.exterior.coords],
            area_m2=float(poly.area), perimeter_m=float(poly.exterior.length),
            floor_z=float(model.levels.floor_z), ceiling_z=None,
            closure_gaps=[{"kind": "free-space", "gap_mm": None, "wall": None, "end": None}],
            support=0.0, derivation="free-space",
        ))
    stats["added"] = len(rooms)
    return rooms, stats
