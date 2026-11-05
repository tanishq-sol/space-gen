"""Stage 1 — levels and wall faces.

Two independent measurements from one cloud (design §4.2):

*Levels* are horizontal planes, validated by a plane fit and a connected-footprint
test, then interpreted by the slab-pair rule. *Faces* are 1-D peaks in a projection
of **vertical points only**, with the point's own normal required to agree with the
projection direction.

That second condition is the whole difference from the pipeline this replaces: a
"wall" assembled from a desk plus a chair plus a real wall projects into a peak,
but the normals of the desk and chair do not point where a wall's normal points.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage

from ..config import Config
from ..geometry import cell_overlap
from ..model import Cloud, Face, LevelSet, Plane, SlabPair

# ------------------------------------------------------------------------- levels


def _pick_peaks(hist: np.ndarray, edges: np.ndarray, min_sep: float, top: int) -> list[int]:
    idx = [i for i in range(1, len(hist) - 1) if hist[i] >= hist[i - 1] and hist[i] >= hist[i + 1] and hist[i] > 0]
    idx.sort(key=lambda i: -hist[i])
    picked: list[int] = []
    for i in idx:
        centre = (edges[i] + edges[i + 1]) / 2
        if all(abs(centre - (edges[j] + edges[j + 1]) / 2) > min_sep for j in picked):
            picked.append(i)
        if len(picked) >= top:
            break
    return sorted(picked)


def _validate_plane(points: np.ndarray, z0: float, origin: np.ndarray, cfg: Config) -> Plane | None:
    sel = np.abs(points[:, 2] - z0) < cfg.level_tol
    # A fit needs points, not a density: the area test below decides what is a level.
    if sel.sum() < cfg.level_fit_min_points:
        return None
    q = points[sel]

    # Centred on the points, so the reported height is the plane *where it is*,
    # not the plane extrapolated to the world origin (a 1° slope moves the intercept
    # 17 mm per metre of distance).
    centre = q[:, :2].mean(0)
    design = np.c_[q[:, 0] - centre[0], q[:, 1] - centre[1], np.ones(len(q))]
    coef, *_ = np.linalg.lstsq(design, q[:, 2], rcond=None)
    residual = q[:, 2] - design @ coef
    rms = float(residual.std())
    if rms > cfg.level_max_rms:
        return None
    slope = float(np.degrees(np.arctan(np.hypot(coef[0], coef[1]))))
    if slope > cfg.level_max_slope_deg:
        return None

    cells = np.floor((q[:, :2] - origin) / cfg.level_cell).astype(np.int64)
    ci, cj = cells[:, 0] - cells[:, 0].min(), cells[:, 1] - cells[:, 1].min()
    mask = np.zeros((cj.max() + 1, ci.max() + 1), bool)
    mask[cj, ci] = True
    labels, _ = ndimage.label(mask, structure=np.ones((3, 3), int))
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    largest = int(sizes.argmax())
    ys, xs = np.where(labels == largest)
    area = len(xs) * cfg.level_cell**2
    bbox = (xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1) * cfg.level_cell**2

    # The area test uses the largest component; the footprint keeps every component
    # that is a surface in its own right, so one ceiling over two rooms covers both.
    min_cells = cfg.level_component_min_area / cfg.level_cell**2
    kept = np.flatnonzero(sizes >= min_cells)
    fy, fx = np.where(np.isin(labels, kept))

    return Plane(
        z=float(z0),
        z_fit=float(coef[2]),
        rms_m=rms,
        slope_deg=slope,
        area_m2=area,
        fill=area / bbox if bbox > 0 else 0.0,
        n_points=int(sel.sum()),
        cells=np.c_[fx + cells[:, 0].min(), fy + cells[:, 1].min()].astype(np.int32),
    )


def _slab_pairs(planes: list[Plane], cfg: Config) -> list[SlabPair]:
    """Two planes that are the top and bottom of one slab.

    Height alone is not enough: the sample scan has ceilings at +2.39 m and
    +2.57 m, 180 mm apart, and they are in different rooms. Pairing them would
    invent a slab between two rooms and hand the storey below a ceiling it never
    had. A slab's two faces share a footprint; two ceilings do not.
    """
    pairs: list[SlabPair] = []
    ordered = sorted(planes, key=lambda p: p.z_fit)
    for i, lower in enumerate(ordered):
        for upper in ordered[i + 1 :]:
            thickness = upper.z_fit - lower.z_fit
            if thickness < cfg.slab_min_thickness:
                continue
            if thickness > cfg.slab_max_thickness:
                break
            overlap = cell_overlap(lower.cells, upper.cells)
            if overlap >= cfg.slab_min_overlap:
                pairs.append(SlabPair(lower=lower, upper=upper, overlap=overlap, thickness=thickness))
    return pairs


def find_levels(cloud: Cloud, cfg: Config = Config()) -> LevelSet:
    if cloud.normals is None:
        from ..cloud import estimate_normals

        estimate_normals(cloud)
    # Only surfaces that face up or down. Without this, every z-band through the
    # walls passes as a "plane": the sample produced one every ~0.24 m from floor
    # to ceiling, and one of them became every room's ceiling.
    points = cloud.points[np.abs(cloud.normals[:, 2]) >= cfg.level_min_normal_z]
    if len(points) == 0:
        raise ValueError("no up- or down-facing surfaces in the cloud — is this a building interior?")
    z = points[:, 2]
    # padded so a level at the cloud's very top or bottom is not in an edge bin,
    # which `_pick_peaks` can never select (a cropped cloud starts at its floor)
    pad = 3 * cfg.level_z_bin
    edges = np.arange(z.min() - pad, z.max() + pad, cfg.level_z_bin)
    hist, _ = np.histogram(z, bins=edges)
    smooth = np.convolve(hist, np.ones(3) / 3.0, mode="same")
    origin = points[:, :2].min(0)

    planes: list[Plane] = []
    # peaks closer than the thinnest slab could not both be found, so a 100 mm
    # slab's two faces must be allowed to be separate candidates
    min_sep = cfg.slab_min_thickness - cfg.level_z_bin
    for i in _pick_peaks(smooth, edges, min_sep=min_sep, top=cfg.level_max_candidates):
        plane = _validate_plane(points, (edges[i] + edges[i + 1]) / 2, origin, cfg)
        if plane is not None:
            planes.append(plane)

    large = [p for p in planes if p.area_m2 >= cfg.level_min_area]
    if not large:
        raise ValueError(f"no horizontal plane reached {cfg.level_min_area} m² — is this a building interior?")

    # Slab pairs are found and reported, but do not decide the floor: on a
    # single-storey scan none exist, and letting a platform 0.1-0.5 m above the floor
    # make the floor an "underside" is a worse failure than the one pairs prevent.
    # They become storey evidence when a multi-storey scan exists (§9 step 1).
    pairs = _slab_pairs(large, cfg)

    # The floor is the lowest surface that is a substantial share of the largest
    # one. Lowest alone would take grade seen through glazing; largest alone would
    # take a ceiling. A desk run never reaches half the floor's area.
    pool = large
    known = cloud.station_rows() if cloud.stations_z_known else None
    if known is not None:
        # The scanner stands on the floor: a plane above the instrument is a
        # ceiling, whatever its area. Filter first, so a big ceiling cannot set
        # the share the real floor is measured against. With several stations the
        # lowest one bounds the floor (single storey, design §1.1).
        lowest = float(np.nanmin(known[0][:, 2]))
        below = [p for p in large if p.z_fit < lowest - cfg.floor_below_station]
        if below:
            pool = below
    biggest = max(p.area_m2 for p in pool)
    floor = min(
        (p for p in pool if p.area_m2 >= cfg.floor_min_share * biggest),
        key=lambda p: p.z_fit,
    )
    if cfg.floor_hint is not None:
        # a storey run: its floor was chosen by `find_storeys`, from the whole cloud
        floor = min(large, key=lambda p: abs(p.z_fit - cfg.floor_hint))
    ceilings = [p for p in large if p.z_fit > floor.z_fit + cfg.room_min_clear]

    return LevelSet(
        planes=planes,
        pairs=pairs,
        floor=floor,
        floor_z=floor.z_fit,
        ceilings=ceilings,
        origin=origin,
        cell=cfg.level_cell,
    )


def find_storeys(cloud: Cloud, levels: LevelSet, cfg: Config = Config()) -> list[float]:
    """Floor heights of every storey the scan shows, bottom to top, the main
    storey's floor (`levels.floor_z`) among them.

    Candidates are planes of `storey_min_area`; planes within `storey_slab_max` of
    each other are one slab and its upper surface is the floor (the lower is the
    ceiling of the storey beneath); a floor less than `storey_min_height` above the
    one below is a platform, not a storey. A candidate is kept only if walls stand
    on it: vertical returns 0.9-1.7 m above it, at least `storey_min_wall_share` of
    the main storey's — otherwise it is a ceiling seen from below (Grainger Museum:
    planes at 2.9-3.2 m, nothing scanned above them).
    """
    main = float(levels.floor_z)
    cands = sorted(p.z_fit for p in levels.planes if p.area_m2 >= cfg.storey_min_area)
    floors: list[float] = []
    for z in cands:
        if floors and z - floors[-1] < cfg.storey_slab_max:
            if abs(floors[-1] - main) > 1e-6:
                floors[-1] = z  # the slab's upper surface is the floor
            continue
        if floors and z - floors[-1] < cfg.storey_min_height:
            continue
        floors.append(z)
    # the main storey's floor is always one of them, exactly
    floors = sorted({f for f in floors if abs(f - main) >= cfg.storey_slab_max} | {main})
    if len(floors) == 1 or cloud.normals is None:
        return [main]
    vertical = np.abs(cloud.normals[:, 2]) < 0.25
    z = cloud.points[:, 2]

    def walls_on(f: float) -> int:
        return int((vertical & (z > f + 0.9) & (z < f + 1.7)).sum())

    base = max(walls_on(main), 1)
    return [f for f in floors if abs(f - main) < 1e-6 or walls_on(f) >= cfg.storey_min_wall_share * base]


# --------------------------------------------------------------------- directions


def normal_directions(normals: np.ndarray, cfg: Config = Config()) -> list[float]:
    """Wall directions from the orientation of vertical surfaces: peaks of the
    histogram of horizontal normal angles (mod 180°), 0.5° bins, smoothed.

    A peak is a direction when it is a local maximum over ±`direction_min_separation`,
    stands `direction_min_contrast` x above the median bin (the background of
    clutter and curved walls) and holds `direction_min_share` of the points within
    2°. The strongest peak is always kept. At most `direction_max`, strongest first.
    An orthogonal building gives two clean peaks (UoM: 22x background, nothing
    else); a radial one gives several (Grainger Museum: 1.3-3.5x).
    """
    if len(normals) == 0:
        return []
    ang = np.degrees(np.arctan2(normals[:, 1], normals[:, 0])) % 180.0
    nb = 360
    hist, _ = np.histogram(ang, bins=nb, range=(0.0, 180.0))
    k = np.exp(-0.5 * (np.arange(-4, 5) / 1.5) ** 2)
    smooth = np.convolve(np.r_[hist[-4:], hist, hist[:4]], k / k.sum(), mode="valid")
    background = max(float(np.median(smooth)), 1e-9)
    w = max(int(round(cfg.direction_min_separation / 0.5)), 1)
    peaks = [i for i in range(nb) if all(smooth[i] >= smooth[(i + j) % nb] for j in range(-w, w + 1))]
    peaks.sort(key=lambda i: -smooth[i])
    out: list[float] = []
    for i in peaks:
        c = i * 0.5 + 0.25
        d = np.minimum(np.abs(ang - c), 180.0 - np.abs(ang - c))
        strong = (
            smooth[i] / background >= cfg.direction_min_contrast and float(np.mean(d < 2.0)) >= cfg.direction_min_share
        )
        if out and not strong:
            continue
        if all(min(abs(c - x), 180 - abs(c - x)) > cfg.direction_min_separation for x in out):
            out.append(float(c))
        if len(out) >= cfg.direction_max:
            break
    return out


def dominant_directions(
    xy: np.ndarray, cfg: Config = Config(), max_points: int = 200_000, normals: np.ndarray | None = None
) -> list[float]:
    """The wall directions of the storey, each refined to 0.05° on the projection.

    With `normals` (of the same points) the candidates are the peaks of
    `normal_directions` — as many as the building has. Without, or when that finds
    fewer than two, the two directions carrying the most wall-length, 25° apart
    (the original rule) fill in.
    """
    if len(xy) > max_points:
        rng = np.random.default_rng(0)
        xy = xy[rng.choice(len(xy), max_points, replace=False)]
    from_normals = normal_directions(normals, cfg) if normals is not None else []

    def score_at(deg: float) -> float:
        t = np.deg2rad(deg)
        s = xy[:, 0] * np.cos(t) + xy[:, 1] * np.sin(t)
        hist, _ = np.histogram(s, bins=np.arange(s.min(), s.max() + 0.02, 0.02))
        return float(np.sort(hist)[-8:].mean())

    picked: list[float] = list(from_normals)
    if len(picked) < 2:
        coarse = [(score_at(deg), deg) for deg in np.arange(0, 180, cfg.direction_step)]
        for _, deg in sorted(coarse, reverse=True):
            if all(min(abs(deg - d), 180 - abs(deg - d)) > cfg.direction_pair_separation for d in picked):
                picked.append(float(deg))
            if len(picked) >= 2:
                break

    refined: list[float] = []
    for d in picked:
        best, best_score = d, -1.0
        for dd in np.arange(d - 1.0, d + 1.0, 0.05):
            sc = score_at(float(dd))
            if sc > best_score:
                best, best_score = float(dd), sc
        refined.append(round(best % 180.0, 2))
    return refined


# -------------------------------------------------------------------------- faces


class CeilingMap:
    """The ceiling over any point in plan: the nearest surface above the floor there.

    Built from every validated plane at least `room_min_clear` above the floor, each
    footprint closed (light-panel holes) and grown by `ceiling_reach` so a wall's
    line, which the ceiling meets but does not overhang, still finds it. Where no
    plane lies overhead the fallback is the highest ceiling, then floor +
    `fallback_ceiling_height`, and the map says which (`source`).
    """

    def __init__(self, levels: LevelSet, cfg: Config):
        self.floor_z = levels.floor_z
        self.cell = levels.cell
        self.origin = levels.origin
        # a plane whose every footprint piece is under level_component_min_area has
        # no cells: it is clutter overhead, not a ceiling
        planes = sorted(
            (p for p in levels.planes if p.z_fit >= levels.floor_z + cfg.room_min_clear and len(p.cells)),
            key=lambda p: p.z_fit,
        )
        self.levels_z = [p.z_fit for p in planes]
        if levels.ceilings:
            self.fallback = max(c.z_fit for c in levels.ceilings)
            self.source = "highest ceiling"
        else:
            self.fallback = levels.floor_z + cfg.fallback_ceiling_height
            self.source = f"floor + {cfg.fallback_ceiling_height} m (no ceiling found)"
        grow = max(int(round(cfg.ceiling_reach / self.cell)), 0)
        self.grids: list[tuple[np.ndarray, np.ndarray]] = []
        for p in planes:
            c = p.cells
            lo = c.min(0) - grow - 1
            g = np.zeros(tuple(c.max(0) - lo + grow + 2), bool)
            g[c[:, 0] - lo[0], c[:, 1] - lo[1]] = True
            g = ndimage.binary_closing(g, np.ones((3, 3))) | g
            if grow:
                g = ndimage.binary_dilation(g, np.ones((2 * grow + 1, 2 * grow + 1)))
            self.grids.append((lo, g))

    def at(self, xy: np.ndarray, above: np.ndarray | None = None) -> np.ndarray:
        """Lowest ceiling over each xy. With `above`, only surfaces at or over
        that height count: a wall seen up to 3.0 m does not stop at a 2.2 m pod
        roof beside it, so that roof is not its ceiling."""
        ij = np.floor((xy - self.origin) / self.cell).astype(np.int64)
        floor_ok = np.full(len(xy), -np.inf) if above is None else above
        out = np.full(len(xy), np.nan)
        for z, (lo, g) in zip(self.levels_z, self.grids):
            k = ij - lo
            ok = (k[:, 0] >= 0) & (k[:, 1] >= 0) & (k[:, 0] < g.shape[0]) & (k[:, 1] < g.shape[1])
            hit = np.zeros(len(xy), bool)
            hit[ok] = g[k[ok, 0], k[ok, 1]]
            out = np.where(np.isnan(out) & hit & (z >= floor_ok), z, out)
        return np.where(np.isnan(out), np.maximum(self.fallback, floor_ok), out)

    @property
    def highest(self) -> float:
        return max(self.levels_z + [self.fallback])


@dataclass(slots=True)
class Run:
    r0: float
    r1: float
    bridged: list[tuple[float, float]]
    top_gap: float
    pier_bridged: list[tuple[float, float]] = field(default_factory=list)
    # for a row of windows: the runs found without piers in its stretch, measured
    # instead if the row fails (review R14-1)
    fallback: list["Run"] = field(default_factory=list)


def _bands(floor_z: float, ceiling: np.ndarray, cfg: Config) -> tuple[np.ndarray, ...]:
    """Per-column (upper_lo, upper_hi, head_hi): the furniture-free band, capped
    below the local ceiling, and the lintel zone above it."""
    upper_lo = np.full(len(ceiling), floor_z + cfg.run_upper[0])
    # Under a low ceiling the band gives way to the lintel zone, never the other
    # way: the zone keeps run_lintel_min_cells cells (0.30 m) below the ceiling
    # margin, so a 2.4 m room still shows a door head (band 1.2-2.0, head 2.0-2.3).
    head_room = cfg.band_ceiling_offset + cfg.run_lintel_min_cells * cfg.run_cell_z
    upper_hi = np.minimum(floor_z + cfg.run_upper[1], ceiling - max(cfg.run_ceiling_margin, head_room))
    upper_hi = np.maximum(upper_hi, upper_lo + cfg.run_min_band)
    head_hi = ceiling - cfg.band_ceiling_offset
    return upper_lo, upper_hi, head_hi


def column_classes(
    col: np.ndarray,
    z: np.ndarray,
    ncol: int,
    floor_z: float,
    ceiling: np.ndarray,
    cfg: Config,
    col_any: np.ndarray | None = None,
    z_any: np.ndarray | None = None,
) -> dict[str, np.ndarray]:
    """Occupancy of each 0.20 m column in three z-zones, and its class.

    `ceiling` is per column. Cells are `run_cell_z` tall and present with
    `run_cell_min` points (§4.5's grid). Classes, in priority order:
    wall (furniture-free band occupied), lintel (only the zone above it), glass
    (sparse but at both low and band heights — the signature of glazing, which
    returns too little to be wall), low (furniture: low zone only), empty.
    """
    upper_lo, upper_hi, head_hi = _bands(floor_z, ceiling, cfg)
    zc = floor_z + np.arange(0.0, float(ceiling.max() - floor_z) + cfg.run_cell_z, cfg.run_cell_z)
    hist = np.zeros((ncol, len(zc)), np.int32)
    k = np.clip(((z - floor_z) / cfg.run_cell_z).astype(int), 0, len(zc) - 1)
    np.add.at(hist, (col, k), 1)
    present = hist >= cfg.run_cell_min
    centre = zc[None, :] + cfg.run_cell_z / 2

    def occ(lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
        m = (centre >= lo[:, None]) & (centre < hi[:, None])
        n = m.sum(1)
        return np.where(n > 0, (present & m).sum(1) / np.maximum(n, 1), 0.0)

    low = occ(np.full(ncol, floor_z + cfg.band_floor_offset), upper_lo)
    upper = occ(upper_lo, upper_hi)
    head = occ(upper_hi, head_hi)
    wall = upper >= cfg.run_min_upper
    # under a low ceiling the head zone is one or two cells, and one pipe at the
    # ceiling junction would read as a lintel: no evidence, no lintel
    head_cells = np.floor((head_hi - upper_hi) / cfg.run_cell_z + 1e-9)
    lintel = ~wall & (head >= cfg.run_lintel_occ) & (head_cells >= cfg.run_lintel_min_cells)
    glass = ~wall & ~lintel & (upper >= cfg.run_glass_occ) & (low >= cfg.run_glass_occ)
    lowonly = ~wall & ~lintel & ~glass & (low >= cfg.run_low_occ)
    # a pier (round 14): the band occupied by returns of any normal (`col_any`,
    # `z_any`: the line's points before the normal filter) under a lintel of aligned
    # returns — the narrow wall between windows, whose returns face its reveals
    pier = np.zeros(ncol, bool)
    if cfg.run_piers and col_any is not None and len(col_any):
        hist_any = np.zeros((ncol, len(zc)), np.int32)
        k_any = np.clip(((z_any - floor_z) / cfg.run_cell_z).astype(int), 0, len(zc) - 1)
        np.add.at(hist_any, (col_any, k_any), 1)
        m = (centre >= upper_lo[:, None]) & (centre < upper_hi[:, None])
        n = m.sum(1)
        upper_any = np.where(n > 0, ((hist_any >= cfg.run_cell_min) & m).sum(1) / np.maximum(n, 1), 0.0)
        pier = lintel & (upper_any >= cfg.run_min_upper)
    return {
        "upper": upper,
        "head": head,
        "low": low,
        "wall": wall,
        "lintel": lintel & ~pier,
        "glass": glass,
        "low_only": lowonly,
        "pier": pier,
    }


def wall_runs(
    r: np.ndarray,
    z: np.ndarray,
    floor_z: float,
    ceiling: float | np.ndarray,
    cfg: Config = Config(),
    lo: float | None = None,
    r_any: np.ndarray | None = None,
    z_any: np.ndarray | None = None,
    _rows: bool = False,
) -> tuple[list[Run], dict[str, np.ndarray]]:
    """The stretches of one fitted line where a wall actually stands.

    A column is wall when its furniture-free band (1.2 m above the floor up to
    2.2 m, or 0.3 m under the local ceiling if that is lower) is occupied: furniture
    does not reach it and cannot hide it. Breaks of `run_gap_free` merge; breaks up
    to `run_gap_lintel` merge only under a lintel — a door or an opening, recorded
    in `bridged` — rather than ending the wall. Run ends are the extreme points of
    their end columns, not the column edges, so a corner is located to the point
    spacing rather than to ±0.20 m.

    `ceiling` is a scalar or one value per column (from `lo` in `run_col` steps).
    `r_any`/`z_any`, the line's points before the normal filter, find the piers
    between windows (round 14), which anchor a run like wall columns.
    """
    if len(r) == 0:
        return [], {}
    if r_any is not None and cfg.run_piers and not _rows:
        # runs with piers, kept only where they make a row of windows (round 14)
        with_p, cls_p = wall_runs(r, z, floor_z, ceiling, cfg, lo, r_any, z_any, _rows=True)
        if not cls_p.get("pier", np.zeros(0, bool)).any():
            return with_p, cls_p
        without, _ = wall_runs(r, z, floor_z, ceiling, cfg, lo)

        def covered(y: Run) -> float:
            return sum(max(0.0, min(x.r1, y.r1) - max(x.r0, y.r0)) for x in without) / max(y.r1 - y.r0, 1e-9)

        rows = [
            x
            for x in with_p
            if x.pier_bridged and len(x.bridged) >= cfg.run_pier_min_bridges and covered(x) < cfg.run_pier_needed
        ]
        if not rows:
            return without, cls_p
        # the runs without piers, clipped to outside the rows; inside a row they stay
        # as its fallback (review R14-1)
        rest: list[Run] = []
        for x in without:
            pieces = [(x.r0, x.r1)]
            for y in rows:
                pieces = [q for a, b in pieces for q in ((a, min(b, y.r0)), (max(a, y.r1), b)) if q[1] > q[0]]
            for a, b in pieces:
                if b - a >= cfg.face_min_length - cfg.run_col / 2:
                    rest.append(Run(a, b, [g for g in x.bridged if a <= g[0] and g[1] <= b], x.top_gap))
        for y in rows:
            y.fallback = [
                Run(
                    max(x.r0, y.r0), min(x.r1, y.r1), [g for g in x.bridged if y.r0 <= g[0] and g[1] <= y.r1], x.top_gap
                )
                for x in without
                if min(x.r1, y.r1) - max(x.r0, y.r0) > 0
            ]
        return sorted(rows + rest, key=lambda x: x.r0), cls_p
    lo = float(r.min()) if lo is None else lo
    ceiling = np.asarray(ceiling, float)
    if ceiling.ndim:
        ncol = len(ceiling)
    else:
        ncol = max(int(np.ceil((float(r.max()) - lo) / cfg.run_col - 1e-9)), 1)
    col = np.clip(((r - lo) / cfg.run_col).astype(int), 0, ncol - 1)
    ceil = np.broadcast_to(ceiling, (ncol,)).copy()
    col_any = None
    if r_any is not None and _rows:
        keep_any = (r_any >= lo) & (r_any < lo + ncol * cfg.run_col)
        col_any = np.clip(((r_any[keep_any] - lo) / cfg.run_col).astype(int), 0, ncol - 1)
        z_any = z_any[keep_any]
    cls = column_classes(col, z, ncol, floor_z, ceil, cfg, col_any, z_any)
    wall, lintel = cls["wall"] | cls["pier"], cls["lintel"]

    idx = np.flatnonzero(wall)
    if not len(idx):
        return [], cls
    groups: list[list[int]] = [[int(idx[0]), int(idx[0])]]
    bridges: list[list[tuple[int, int]]] = [[]]
    pier_bridges: list[list[tuple[int, int]]] = [[]]
    aligned_wall = cls["wall"]
    eps = 1e-9
    for i in idx[1:]:
        a, b = groups[-1][1] + 1, int(i)
        width = (b - a) * cfg.run_col
        if width <= cfg.run_gap_free + eps:
            groups[-1][1] = b
        elif width <= cfg.run_gap_lintel + eps and lintel[a:b].mean() >= cfg.run_lintel_share:
            groups[-1][1] = b
            bridges[-1].append((a, b))
            if not (aligned_wall[a - 1] and aligned_wall[b]):
                pier_bridges[-1].append((a, b))
        else:
            groups.append([b, b])
            bridges.append([])
            pier_bridges.append([])

    # the band points of wall columns locate each run's ends and its top
    band = z >= floor_z + cfg.run_upper[0]
    out: list[Run] = []
    for (a, b), br, pbr in zip(groups, bridges, pier_bridges):
        first = band & (col == a) & (r >= lo + a * cfg.run_col)
        last = band & (col == b)
        r0 = float(r[first].min()) if first.any() else lo + a * cfg.run_col
        r1 = float(r[last].max()) if last.any() else lo + (b + 1) * cfg.run_col
        # the minimum is a column count; snapping ends to points may shave up to
        # half a column off a run that has the columns
        if r1 - r0 < cfg.face_min_length - cfg.run_col / 2:
            continue
        tops = [
            float(ceil[c] - np.percentile(z[col == c], 98)) for c in range(a, b + 1) if wall[c] and (col == c).any()
        ]
        out.append(
            Run(
                r0=r0,
                r1=r1,
                bridged=[(lo + x * cfg.run_col, lo + y * cfg.run_col) for x, y in br],
                top_gap=float(np.median(tops)) if tops else 0.0,
                pier_bridged=[(lo + x * cfg.run_col, lo + y * cfg.run_col) for x, y in pbr],
            )
        )
    return out, cls


def _peaks(hist: np.ndarray, threshold: float) -> list[tuple[int, int, int]]:
    """Contiguous bins above threshold, as (first, last, strongest)."""
    idx = np.where(hist >= threshold)[0]
    if not len(idx):
        return []
    out, start, prev = [], idx[0], idx[0]
    for i in list(idx[1:]) + [None]:
        if i is None or i - prev > 1:
            seg = hist[start : prev + 1]
            out.append((int(start), int(prev), int(start + np.argmax(seg))))
            if i is None:
                break
            start = i
        prev = i
    return out


def _split(hist: np.ndarray, a: int, b: int, min_sep: int, dip: float) -> list[int]:
    """The distinct maxima inside one above-threshold stretch [a, b].

    Two parallel surfaces 10-20 cm apart (a wall and its neighbour, a partition
    beside a façade) make one contiguous stretch; its single strongest bin would
    hide the weaker one. A maximum counts when it is `min_sep` bins from a
    stronger one and the valley between them falls below `dip` x the weaker.
    """
    seg = hist[a : b + 1].astype(float)
    order = np.argsort(-seg, kind="stable")
    kept: list[int] = []
    for i in order:
        if i > 0 and seg[i] < seg[i - 1] or i < len(seg) - 1 and seg[i] < seg[i + 1]:
            continue  # not a local maximum
        ok = True
        for j in kept:
            lo, hi = min(i, j), max(i, j)
            if hi - lo < min_sep or seg[lo : hi + 1].min() >= dip * min(seg[i], seg[j]):
                ok = False
                break
        if ok:
            kept.append(int(i))
    return sorted(a + i for i in kept)


def _seeds(s: np.ndarray, r: np.ndarray, edges: np.ndarray, cfg: Config) -> tuple[list[float], list[tuple]]:
    """Candidate face offsets in one direction: the distinct peaks of the whole
    projection, then of each `face_tile`-long tile along the direction (half
    overlapping), each against its own threshold — so a short wall is not judged
    against the strongest wall 50 m away. A tile's threshold never falls below
    `face_tile_global_frac` of the whole projection's, so a clutter-only tile
    cannot seed its noise. A stretch wider than `face_max_peak_width` is one
    smeared surface (a cross wall's points, a curved wall), never a seed. A seed
    within `face_seed_merge` of an earlier one is that line. Also returns the
    wide stretches of the whole projection, as rejects."""
    min_sep = max(int(round(cfg.face_split_sep / cfg.face_bin)), 1)
    max_bins = int(round(cfg.face_max_peak_width / cfg.face_bin))
    nbins, rng = len(edges) - 1, (float(edges[0]), float(edges[-1]))
    seeds: list[float] = []
    wide: list[tuple] = []
    floor = [cfg.face_thr_min]

    def add(sub: np.ndarray, whole: bool) -> None:
        hist, _ = np.histogram(sub, bins=nbins, range=rng)
        if not hist.any():
            return
        threshold = max(floor[0], cfg.face_thr_frac * hist.max())
        if whole:
            floor[0] = max(cfg.face_thr_min, cfg.face_tile_global_frac * threshold)
        for a, b, peak in _peaks(hist, threshold):
            if b - a + 1 > max_bins:
                if whole:
                    wide.append(((edges[peak] + edges[peak + 1]) / 2, (b - a + 1) * cfg.face_bin))
                continue
            for k in _split(hist, a, b, min_sep, cfg.face_split_dip):
                c = float((edges[k] + edges[k + 1]) / 2)
                if all(abs(c - x) > cfg.face_seed_merge for x in seeds):
                    seeds.append(c)

    add(s, True)
    if cfg.face_tile > 0 and len(r) >= cfg.face_min_points:
        order = np.argsort(r, kind="stable")
        r_sorted = r[order]
        # the span from percentiles: one stray return must not add empty tiles
        lo, hi = (float(x) for x in np.percentile(r_sorted, [0.1, 99.9]))
        if hi - lo > cfg.face_tile:
            for t0 in np.arange(lo, hi, cfg.face_tile / 2):
                i0, i1 = np.searchsorted(r_sorted, [t0, t0 + cfg.face_tile])
                if i1 - i0 >= cfg.face_min_points:
                    add(s[order[i0:i1]], False)
    return seeds, wide


def find_faces(
    band: np.ndarray,
    normals: np.ndarray,
    direction: float,
    cfg: Config = Config(),
    floor_z: float | None = None,
    ceilings: CeilingMap | None = None,
    station: np.ndarray | None = None,
    rejected: list[dict] | None = None,
    stations: np.ndarray | None = None,
    scan: np.ndarray | None = None,
) -> list[Face]:
    """Wall faces in one direction: peak, fit, split into runs, measure, accept.

    Facing comes from the scanner that saw the line: `stations` (S, 3) with `scan`,
    each band point's row in it (-1: no scanner), takes the station that saw most
    of the line's points; a single `station` stands for all of them.

    Without `floor_z`/`ceilings` the line is not split (unit-test mode). Every line
    that yields no accepted face is appended to `rejected` with a reason, so what is
    missing is a number in the report rather than a silence.
    """
    t = np.deg2rad(direction)
    u = np.array([np.cos(t), np.sin(t)])
    v = np.array([-u[1], u[0]])
    s = band @ np.r_[u, 0.0]
    r = band @ np.r_[v, 0.0]
    z = band[:, 2]
    normal_dot = np.abs(normals[:, :2] @ u)
    rejected = [] if rejected is None else rejected

    def reject(offset: float, r0: float, r1: float, reason: str, **extra) -> None:
        rejected.append(
            {
                "dir": round(float(direction), 3),
                "offset": round(float(offset), 4),
                "r0": round(float(r0), 3),
                "r1": round(float(r1), 3),
                "length": round(float(r1 - r0), 3),
                "reason": reason,
                **extra,
            }
        )

    edges = np.arange(s.min(), s.max() + cfg.face_bin, cfg.face_bin)
    seeds, wide = _seeds(s, r, edges, cfg)
    for centre, width in wide:
        reject(centre, float(r.min()), float(r.max()), "wide-peak", width=round(width, 3))
    order = np.argsort(s, kind="stable")
    s_sorted = s[order]

    faces: list[Face] = []
    for centre in sorted(seeds):
        sel = order[
            np.searchsorted(s_sorted, centre - cfg.face_window) : np.searchsorted(s_sorted, centre + cfg.face_window)
        ]
        if len(sel) < cfg.face_min_points:
            if len(sel):
                reject(centre, float(r[sel].min()), float(r[sel].max()), "sparse")
            continue
        s_sel, r_sel, z_sel, nd_sel = s[sel], r[sel], z[sel], normal_dot[sel]
        slope, intercept = np.polyfit(r_sel, s_sel, 1)
        keep = np.abs(s_sel - (slope * r_sel + intercept)) < cfg.face_trim
        if keep.sum() < cfg.face_min_points:
            reject(centre, float(r_sel.min()), float(r_sel.max()), "sparse")
            continue
        s_sel, r_sel, z_sel, nd_sel = s_sel[keep], r_sel[keep], z_sel[keep], nd_sel[keep]
        line_r0, line_r1 = float(r_sel.min()), float(r_sel.max())

        # the side the scanner looked from: the room side of this face
        facing = 0
        observer = None
        if stations is not None and scan is not None:
            seen = scan[sel][keep]
            seen = seen[seen >= 0]
            if len(seen):
                observer = stations[int(np.bincount(seen).argmax())]
        elif station is not None:
            observer = station
        if observer is not None:
            facing = 1 if float(observer[:2] @ u) > centre else -1

        if floor_z is None or ceilings is None:
            runs = [Run(float(np.percentile(r_sel, 0.3)), float(np.percentile(r_sel, 99.7)), [], 0.0)]
            cls: dict[str, np.ndarray] = {}
        else:
            aligned = nd_sel >= cfg.face_min_normal_dot
            ncol = max(int(np.ceil((line_r1 - line_r0) / cfg.run_col - 1e-9)), 1)
            rc = line_r0 + (np.arange(ncol) + 0.5) * cfg.run_col
            if not aligned.any():
                reject(centre, line_r0, line_r1, "no-aligned-points", facing=facing)
                continue
            # where each column's own points stop (98th percentile, so one stray
            # return cannot lift it): its ceiling cannot be below that
            col_all = np.clip(((r_sel[aligned] - line_r0) / cfg.run_col).astype(int), 0, ncol - 1)
            za = z_sel[aligned]
            top = np.full(ncol, -np.inf)
            for c in np.unique(col_all):
                top[c] = np.percentile(za[col_all == c], 98)
            top = np.where(np.isfinite(top), top - cfg.ceiling_tolerance, -np.inf)
            # the ceiling of the room this face looks into, sampled just off the face
            side = facing if facing else 1
            xy = (centre + side * cfg.ceiling_probe) * u[None, :] + rc[:, None] * v[None, :]
            ceil = ceilings.at(xy, above=top)
            if not facing:
                xy2 = (centre - cfg.ceiling_probe) * u[None, :] + rc[:, None] * v[None, :]
                ceil = np.minimum(ceil, ceilings.at(xy2, above=top))
            runs, cls = wall_runs(
                r_sel[aligned], z_sel[aligned], floor_z, ceil, cfg, lo=line_r0, r_any=r_sel, z_any=z_sel
            )

        accepted_here = 0
        pending = list(runs)
        while pending:
            run = pending.pop(0)
            m = (r_sel >= run.r0) & (r_sel <= run.r1)
            if m.sum() < cfg.face_min_points:
                reject(centre, run.r0, run.r1, "sparse-run")
                pending[:0] = run.fallback  # a failed row of windows: the runs without piers
                continue
            face, failed = _measure_face(
                direction,
                s_sel[m],
                r_sel[m],
                z_sel[m],
                nd_sel[m],
                cfg,
                (run.r0, run.r1) if cls else None,
                run.bridged,
            )
            if face is None:
                reject(centre, run.r0, run.r1, "failed:" + ",".join(failed))
                pending[:0] = run.fallback
                continue
            face.facing = facing
            face.bridged = run.bridged
            face.pier_bridged = run.pier_bridged
            face.top_gap = run.top_gap
            face.partial_height = run.top_gap >= cfg.run_partial_gap
            faces.append(face)
            accepted_here += 1

        if not accepted_here and cls:
            # a pier is a lintel column for the reason (the room stage reads "head-only", R14-3)
            lintel_all = cls["lintel"] | cls["pier"] if "pier" in cls else cls["lintel"]
            col_m = {
                k: round(float((lintel_all if k == "lintel" else cls[k]).sum()) * cfg.run_col, 2)
                for k in ("wall", "lintel", "glass", "low_only")
            }
            total = line_r1 - line_r0
            if col_m["glass"] >= cfg.run_reason_share * total:
                reason = "glass-signature"
            elif col_m["low_only"] >= cfg.run_reason_share * total:
                reason = "low-only"
            elif col_m["wall"] > 0:
                reason = "short-runs"
            elif col_m["lintel"] >= cfg.run_reason_share * total:
                reason = "head-only"
            else:
                reason = "empty-band"
            reject(centre, line_r0, line_r1, reason, columns_m=col_m, facing=facing)
    return faces


def _measure_face(
    direction: float,
    s_sel: np.ndarray,
    r_sel: np.ndarray,
    z_sel: np.ndarray,
    nd_sel: np.ndarray,
    cfg: Config,
    run: tuple[float, float] | None = None,
    bridged: list[tuple[float, float]] | None = None,
) -> tuple[Face | None, list[str]]:
    slope, intercept = np.polyfit(r_sel, s_sel, 1)
    rms = float((s_sel - (slope * r_sel + intercept)).std())
    ndot = float(np.median(nd_sel))
    if run is None:
        r0, r1 = float(np.percentile(r_sel, 0.3)), float(np.percentile(r_sel, 99.7))
    else:
        # the run's ends are already its extreme band points
        r0, r1 = run
    length = r1 - r0
    zspread = float(np.percentile(z_sel, 95) - np.percentile(z_sel, 5))

    bins = max(int(round(length / cfg.face_cover_bin)), 1)
    idx = np.clip(((r_sel - r0) / max(length, 1e-9) * bins).astype(int), 0, bins - 1)
    counts = np.bincount(idx, minlength=bins).astype(float)
    # a lintel-bridged opening is part of the wall, not a hole in its evidence:
    # its bins count as covered and do not drag the median down
    centres = r0 + (np.arange(bins) + 0.5) * length / bins
    in_bridge = np.zeros(bins, bool)
    for a, b in bridged or []:
        in_bridge |= (centres >= a) & (centres <= b)
    solid = counts[~in_bridge]
    median_count = float(np.median(solid)) if len(solid) else 0.0
    covered = (counts >= max(1.0, cfg.face_cover_frac * median_count)) | in_bridge
    cover = float(covered.mean()) if median_count > 0 else 0.0
    # points per metre of run per metre of observed height (not per face area)
    density = len(s_sel) / max(length * max(zspread, 0.1), 1e-6)

    tests = {
        "length": length >= cfg.face_min_length - (cfg.run_col / 2 if run is not None else 0.0),
        "zspread": zspread >= cfg.face_min_zspread,
        "rms": rms <= cfg.face_max_rms,
        "cover": cover >= cfg.face_min_cover,
        "density": density >= cfg.face_min_density,
        "normal": ndot >= cfg.face_min_normal_dot,
    }
    failed = [k for k, ok in tests.items() if not ok]
    if failed:
        return None, failed

    return (
        Face(
            direction=float(direction),
            offset=round(float(slope * (r0 + r1) / 2 + intercept), 4),
            k=float(slope),
            c=float(intercept),
            r0=float(r0),
            r1=float(r1),
            length=float(length),
            rms_m=rms,
            zspread=zspread,
            zmin=float(np.percentile(z_sel, 2)),
            zmax=float(np.percentile(z_sel, 98)),
            cover=cover,
            density=density,
            normal_dot=ndot,
            points=int(len(s_sel)),
        ),
        [],
    )


def dedupe(faces: list[Face], tol: float = 0.03, min_overlap: float = 0.4) -> list[Face]:
    """Drop a face that is the same surface as a stronger one (found in a
    neighbouring peak). The stronger face keeps its own statistics: a merged face
    must not look better than either parent. Extents join only where they overlap,
    which the 40% overlap test already guarantees."""
    kept: list[Face] = []
    for f in sorted(faces, key=lambda x: -x.points):
        duplicate = None
        for g in kept:
            ov0, ov1 = max(f.r0, g.r0), min(f.r1, g.r1)
            if ov1 - ov0 < min_overlap * min(f.length, g.length):
                continue
            rs = np.linspace(ov0, ov1, 9)
            if np.abs((f.k * rs + f.c) - (g.k * rs + g.c)).max() < tol:
                duplicate = g
                break
        if duplicate is None:
            kept.append(f)
        else:
            duplicate.r0 = min(duplicate.r0, f.r0)
            duplicate.r1 = max(duplicate.r1, f.r1)
            duplicate.length = duplicate.r1 - duplicate.r0
            duplicate.offset = float(duplicate.k * (duplicate.r0 + duplicate.r1) / 2 + duplicate.c)
    return kept


# --------------------------------------------------------------------------- run


def storey_band(
    cloud: Cloud, levels: LevelSet, cfg: Config = Config(), top: float | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """Points between floor and ceiling that belong to a vertical surface."""
    p, n = cloud.points, cloud.normals
    assert n is not None
    if top is None:
        top = max((c.z_fit for c in levels.ceilings), default=levels.floor_z + cfg.fallback_ceiling_height)
    band = storey_band_mask(cloud, levels, cfg, top)
    return p[band], n[band]


def storey_band_mask(cloud: Cloud, levels: LevelSet, cfg: Config = Config(), top: float | None = None) -> np.ndarray:
    p, n = cloud.points, cloud.normals
    assert n is not None
    if top is None:
        top = max((c.z_fit for c in levels.ceilings), default=levels.floor_z + cfg.fallback_ceiling_height)
    vertical = np.abs(n[:, 2]) < 0.25
    inside = (p[:, 2] > levels.floor_z + cfg.band_floor_offset) & (p[:, 2] < top - cfg.band_ceiling_offset)
    return inside & vertical


def run(model, cfg: Config = Config()) -> None:
    cloud = model.cloud
    assert cloud is not None, "stage 1 needs a cloud"
    model.levels = find_levels(cloud, cfg)
    ceilings = CeilingMap(model.levels, cfg)
    model.meta["ceiling_fallback"] = ceilings.source

    band, band_normals = storey_band(cloud, model.levels, cfg, top=ceilings.highest)
    known = cloud.station_rows()
    stations = band_scan = None
    if known is not None:
        stations = known[0]
        band_scan = known[1][storey_band_mask(cloud, model.levels, cfg, top=ceilings.highest)]
    lo, hi = cfg.direction_band
    floor_z = model.levels.floor_z
    mid = (
        (cloud.points[:, 2] > floor_z + lo) & (cloud.points[:, 2] < floor_z + hi) & (np.abs(cloud.normals[:, 2]) < 0.25)  # type: ignore[index]
    )
    model.direction = dominant_directions(cloud.points[mid, :2], cfg, normals=cloud.normals[mid])  # type: ignore[index]

    recall = {}
    for direction in model.direction:
        rejected: list[dict] = []
        found = find_faces(
            band,
            band_normals,
            direction,
            cfg,
            floor_z=floor_z,
            ceilings=ceilings,
            rejected=rejected,
            stations=stations,
            scan=band_scan,
        )
        kept = dedupe(found, tol=cfg.face_dedupe_tol)
        model.faces.extend(kept)
        model.rejected_faces.extend(rejected)
        accepted_m = sum(f.length for f in kept)
        glass_m = sum(x["length"] for x in rejected if x["reason"] == "glass-signature")
        recall[f"{direction:.2f}"] = {
            "accepted_run_m": round(accepted_m, 2),
            "rejected_line_m": round(sum(x["length"] for x in rejected), 2),
            "glass_signature_m": round(glass_m, 2),
        }
    model.meta["recall_by_direction"] = recall
    model.meta["band_points"] = len(band)
    if cfg.local_faces:
        from .s1_local import local_faces

        extra, stats = local_faces(
            band,
            band_normals,
            model.faces,
            model.direction,
            cfg,
            floor_z,
            ceilings,
            stations=stations,
            scan=band_scan,
            rejected=model.rejected_faces,
        )
        model.faces.extend(extra)
        model.meta["local_faces"] = stats
    if cfg.arc_faces:
        from .s1_arcs import arc_faces

        extra, stats = arc_faces(
            band,
            band_normals,
            model.faces,
            cfg,
            floor_z,
            ceilings,
            stations=stations,
            scan=band_scan,
            rejected=model.rejected_faces,
        )
        model.faces.extend(extra)
        model.meta["arc_faces"] = stats
