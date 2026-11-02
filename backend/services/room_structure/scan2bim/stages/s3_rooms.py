"""Stage 3 — rooms: close the wall network in plan, polygonise it, keep what closes.

Rooms are the *inner faces* of the walls, not their centrelines (design §4.4), so
a room's area is the floor area a reader measures with a tape rather than the
area between wall axes.

The hard part is not finding polygons, it is refusing bad ones. `polygonize` over
the arrangement of wall faces will happily return a simple, well-supported polygon
for the union of two rooms joined by an unmeasured gap — every criterion in §4.4
passes it. What separates a room from that union is *closure*: the ring is only
real where the wall network actually meets, and a chord we added to make it meet
is a claim, not a measurement. So every chord is graded by length, kept if it is
small enough, and recorded on the room whose boundary used it.

The other thing this stage must not do is hallucinate floor it cannot see. It
reports how much of the scanned floor ended up inside no room, because "14 rooms"
on a 130 m² floor is a very different statement from "14 rooms" on a 40 m² one.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from scipy import ndimage
from shapely import contains_xy
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union

from ..config import Config
from ..model import Model, Room, Wall


@dataclass(slots=True)
class Chord:
    """A segment added to close the network between a wall end and another face."""

    wall: str
    end: str
    line: LineString
    gap_m: float
    recorded: bool  # the gap is large enough that closing it is a claim
    kind: str = "short"  # short: within the closure band; occluded: no ray crossed it


# ----------------------------------------------------------------- gap evidence


class Rays:
    """Band-height returns as rays from the station, sorted by azimuth so the rays
    aimed at a chord are found by binary search (O(log N + wedge) per chord)."""

    def __init__(self, xy: np.ndarray, station: np.ndarray):
        d = xy - station[:2]
        ang = np.arctan2(d[:, 1], d[:, 0])
        order = np.argsort(ang, kind="stable")
        self.station = station[:2]
        self.ang = ang[order]
        self.dist = np.hypot(d[order, 0], d[order, 1])

    def wedge(self, a0: float, a1: float) -> slice | tuple[slice, slice]:
        lo, hi = (a0, a1) if a0 <= a1 else (a1, a0)
        if hi - lo <= np.pi:
            return slice(np.searchsorted(self.ang, lo), np.searchsorted(self.ang, hi))
        # the short way round crosses ±pi
        return (slice(np.searchsorted(self.ang, hi), len(self.ang)), slice(0, np.searchsorted(self.ang, lo)))


def gap_evidence(chord: LineString, rays, cfg: Config) -> tuple[int, int]:
    """Sum of `_gap_evidence_one` over every station's rays (one Rays or a list):
    a ray from any scanner that passes the gap proves it open. Only stations
    within `ray_reach` of the chord are asked: a mobile scan has thousands of
    stations, and the ones across the building see nothing of this gap."""
    if isinstance(rays, Rays):
        return _gap_evidence_one(chord, rays, cfg)
    through = blocked = 0
    mid = np.asarray(chord.interpolate(0.5, normalized=True).coords[0])
    for r in rays:
        if float(np.hypot(*(r.station - mid))) > cfg.ray_reach:
            continue
        t, b = _gap_evidence_one(chord, r, cfg)
        through, blocked = through + t, blocked + b
    return through, blocked


def _gap_evidence_one(chord: LineString, rays: Rays, cfg: Config) -> tuple[int, int]:
    """(through, blocked): rays aimed at the chord's interior (5-95%) that land at
    least `occluded_beyond` past it, and rays that stop that far short of it.

    Through-rays prove the gap is seen through. Blocked rays prove something nearer
    hid it. Neither means nothing was seen in that direction: no evidence at all.
    """
    a, b = np.asarray(chord.coords[0]), np.asarray(chord.coords[-1])
    p0, p1 = a + 0.05 * (b - a), a + 0.95 * (b - a)
    s = rays.station
    a0 = float(np.arctan2(*(p0 - s)[::-1]))
    a1 = float(np.arctan2(*(p1 - s)[::-1]))
    sel = rays.wedge(a0, a1)
    parts = sel if isinstance(sel, tuple) else (sel,)
    ang = np.concatenate([rays.ang[p] for p in parts])
    dist = np.concatenate([rays.dist[p] for p in parts])
    if len(ang) == 0:
        return 0, 0
    # distance along each ray direction to the chord's line
    e = b - a
    dirs = np.c_[np.cos(ang), np.sin(ang)]
    den = dirs[:, 0] * e[1] - dirs[:, 1] * e[0]
    ok = np.abs(den) > 1e-9  # a station on the chord's line sees no width: no evidence
    w0 = a - s
    to_chord = np.where(ok, (w0[0] * e[1] - w0[1] * e[0]) / np.where(ok, den, 1.0), np.nan)
    ok &= to_chord > 0
    through = int((ok & (dist > to_chord + cfg.occluded_beyond)).sum())
    blocked = int((ok & (dist < to_chord - cfg.occluded_beyond)).sum())
    return through, blocked


def make_rays(model: Model, cfg: Config) -> list[Rays] | None:
    """Rays through the gap-evidence band, one bundle per station, each point's ray
    from the scanner that saw it; None without any station."""
    cloud, levels = model.cloud, model.levels
    if cloud is None or levels is None:
        return None
    known = cloud.station_rows()
    if known is None:
        return None
    stations, idx = known
    p = cloud.points
    lo, hi = cfg.gap_ray_band
    sel = np.flatnonzero((p[:, 2] > levels.floor_z + lo) & (p[:, 2] < levels.floor_z + hi) & (idx >= 0))
    if len(sel) == 0:
        return None
    # one sort, then split by station: O(N log N) whatever the number of stations
    order = sel[np.argsort(idx[sel], kind="stable")]
    keys = idx[order]
    cuts = np.flatnonzero(np.diff(keys)) + 1
    bundles = [Rays(p[part, :2], stations[idx[part[0]]])
               for part in np.split(order, cuts) if len(part) >= cfg.gap_min_rays]
    return bundles or None


def _gap_target(w: Wall, end: str, cap: LineString, walls: list[Wall], cfg: Config):
    """Where the gap at a wall end closes to: the wall's own line continued, if it
    meets another wall within reach; otherwise the nearest other face or cap. A chord
    that would cross a wall body is no chord."""
    mid = Point(cap.interpolate(0.5, normalized=True))
    out = w.perp if end == "r1" else -w.perp
    ahead = LineString([mid.coords[0], tuple(np.asarray(mid.coords[0]) + out * cfg.occluded_max)])
    targets = [(o, seg) for o in walls if o is not w for seg in [s for _, s in wall_faces(o)] + wall_caps(o)]
    best = None
    for o, seg in targets:
        x = ahead.intersection(seg)
        if not x.is_empty:
            d = mid.distance(x)
            if best is None or d < best[0]:
                best = (d, o, Point(x.coords[0]) if hasattr(x, "coords") else Point(x.centroid))
    if best is None:
        for o, seg in targets:
            d = seg.distance(mid)
            if best is None or d < best[0] - 1e-9 or (abs(d - best[0]) < 1e-9 and o.id < best[1].id):
                best = (d, o, seg.interpolate(seg.project(mid)))
    if best is None or best[0] < 1e-6:
        return None
    gap, other, hit = best
    line = LineString([mid.coords[0], hit.coords[0]])
    shrunk = line.interpolate(0.02, normalized=True), line.interpolate(0.98, normalized=True)
    inner = LineString([shrunk[0].coords[0], shrunk[1].coords[0]])
    if any(inner.intersects(footprint(o)) for o in walls if o is not w and o is not other):
        return None
    return gap, other, line


def gap_chords(
    model: Model, cfg: Config, rays: Rays | None, closed: set[tuple[str, str]] = frozenset()
) -> tuple[list[Chord], list[dict]]:
    """Close an unjoined wall end's gap on evidence, or report it (§4.4.1).

    occluded — rays aimed at it are blocked in front of it and none passes: hidden,
               closed (≤ `occluded_max`).
    opening  — rays pass through and it is wider than the closure band but at most
               `opening_max`: a door-sized opening a room boundary crosses, closed,
               a stage-4 candidate.
    open     — rays pass through a wider gap: the space continues; reported.
    unknown  — neither: nothing was seen in that direction; reported, not closed.
    """
    if rays is None:
        return [], []
    chords: list[Chord] = []
    report: list[dict] = []
    seen_pairs: dict[frozenset, int] = {}
    for w in model.walls:
        for end, cap in zip(("r0", "r1"), wall_caps(w)):
            if end not in w.unjoined or end in w.doorway_ends or (w.id, end) in closed:
                continue
            target = _gap_target(w, end, cap, model.walls, cfg)
            if target is None:
                continue
            gap, other, line = target
            through, blocked = gap_evidence(line, rays, cfg)
            entry = {"wall": w.id, "end": end, "to": other.id, "gap_m": round(gap, 3),
                     "rays_through": through, "rays_blocked": blocked}
            if through >= cfg.gap_min_rays:
                kind = "opening" if gap <= cfg.opening_max else "open"
            elif blocked >= cfg.gap_min_rays:  # and fewer than gap_min_rays through: noise
                kind = "occluded" if gap <= cfg.occluded_max else "open"
            else:
                kind = "unknown"
            entry["kind"] = kind
            if kind in ("occluded", "opening"):
                pair = frozenset((w.id, other.id))
                if pair in seen_pairs and chords[seen_pairs[pair]].gap_m <= gap:
                    continue  # the mirror chord from the other wall's end is already in
                chord = Chord(wall=w.id, end=end, line=line, gap_m=gap, recorded=True, kind=kind)
                if pair in seen_pairs:
                    chords[seen_pairs[pair]] = chord
                else:
                    seen_pairs[pair] = len(chords)
                    chords.append(chord)
            else:
                report.append(entry)
    return chords, report


def partition_lines(poly: Polygon, rejected: list[dict], faces: list[LineString], cfg: Config) -> list[str]:
    """Rejected line candidates that may be an unseen partition across this room:
    each part of the line inside the room is tested on its own, by its midpoint."""
    out = []
    for x in rejected:
        if x.get("reason") not in cfg.partition_reasons or not {"dir", "offset", "r0", "r1"} <= x.keys():
            continue
        t = np.radians(x["dir"])
        u, v = np.array([np.cos(t), np.sin(t)]), np.array([-np.sin(t), np.cos(t)])
        line = LineString([x["offset"] * u + x["r0"] * v, x["offset"] * u + x["r1"] * v])
        inside = line.intersection(poly)
        parts = [g for g in getattr(inside, "geoms", [inside]) if g.geom_type == "LineString"]
        for part in parts:
            if part.length < cfg.partition_min_length:
                continue
            mid = part.interpolate(0.5, normalized=True)
            if any(f.distance(mid) < cfg.partition_face_clear for f in faces):
                continue  # lying on an accepted face is that face, not a partition
            out.append(f"{x['dir']:.2f}:{x['offset']:.3f}:{x['r0']:.2f}-{x['r1']:.2f}")
            break
    return out

# ------------------------------------------------------------------ wall geometry


def wall_faces(wall: Wall) -> list[tuple[str, LineString]]:
    """The wall's two physical faces, in plan, with the end each starts at."""
    u, v = wall.unit, wall.perp
    out = []
    for side, off in (("lo", wall.plane_offsets()[0]), ("hi", wall.plane_offsets()[1])):
        a = off * u + wall.r0 * v
        b = off * u + wall.r1 * v
        out.append((side, LineString([a, b])))
    return out


def wall_caps(wall: Wall) -> list[LineString]:
    """The wall's two end faces. A wall end is a real surface, not open space."""
    u, v = wall.unit, wall.perp
    lo, hi = wall.plane_offsets()
    return [
        LineString([lo * u + r * v, hi * u + r * v]) for r in (wall.r0, wall.r1)
    ]


def footprint(wall: Wall) -> Polygon:
    """The wall's plan footprint, used to reject the polygon that fills it."""
    u, v = wall.unit, wall.perp
    lo, hi = wall.plane_offsets()
    return Polygon(
        [
            lo * u + wall.r0 * v,
            lo * u + wall.r1 * v,
            hi * u + wall.r1 * v,
            hi * u + wall.r0 * v,
        ]
    )


# ----------------------------------------------------------------------- closure


def closure_chords(walls: list[Wall], cfg: Config) -> list[Chord]:
    """Bridge a wall's *open end* to the nearest measured surface of another wall.

    A wall's end is a surface (its cap), so the thing that can be open is the cap,
    not the face. A cap that already meets another wall's face or cap needs
    nothing - that is a corner. A cap that stops 40 mm short meets nothing exactly,
    so the ring is open by 40 mm even though the scan says the walls touch; that is
    a weld, and it is made silently. A cap half a metre from the next surface is
    closed and recorded, because a door reveal or a scan shadow can hide the last
    500 mm of a wall. Beyond `closure_max` the wall is not closing on a wall at all,
    so nothing is added and the region stays open.

    Anchoring on caps rather than on face endpoints is what stops this returning
    fifteen "chords" for a room that is already closed: every face endpoint touches
    its own cap, so the old test fired at every corner of every wall.
    """
    measured: list[tuple[str, LineString]] = []
    for wall in walls:
        measured += [(wall.id, seg) for _, seg in wall_faces(wall)]
        measured += [(wall.id, seg) for seg in wall_caps(wall)]

    chords: list[Chord] = []
    seen: set[tuple[tuple[float, float], tuple[float, float]]] = set()
    for wall in walls:
        for end, cap in zip(("r0", "r1"), wall_caps(wall)):
            if any(wid != wall.id and seg.intersects(cap) for wid, seg in measured):
                continue
            for p in (cap.coords[0], cap.coords[-1]):
                point = Point(p)
                best: tuple[float, LineString] | None = None
                for wid, seg in measured:
                    if wid == wall.id:
                        continue
                    d = seg.distance(point)
                    if best is None or d < best[0]:
                        best = (d, seg)
                if best is None or best[0] > cfg.closure_max:
                    continue
                hit = best[1].interpolate(best[1].project(point))
                key = tuple(sorted((tuple(p), tuple(hit.coords[0]))))
                if key in seen:
                    continue
                seen.add(key)
                chords.append(
                    Chord(
                        wall=wall.id,
                        end=end,
                        line=LineString([p, hit.coords[0]]),
                        gap_m=best[0],
                        recorded=best[0] > cfg.closure_silent,
                    )
                )
    return chords


# -------------------------------------------------------------------- supporting


def boundary_evidence(
    poly: Polygon, segments: list[LineString], tol_support: float, tol_bridge: float
) -> tuple[float, float, list[LineString]]:
    """How much of a boundary is measured, and which stretches are invented.

    Returns `(support, bridged_m, unsupported)`.

    `support` is the design's §4.4 acceptance quantity: the fraction of the
    perimeter within `tol_support` of a wall face or wall end cap. `bridged_m` is
    the stricter, more useful claim: the length of boundary further than
    `tol_bridge` from any measured surface, i.e. stretches this stage drew itself
    to close the ring. Boundary vertices are exact intersections of fitted lines,
    so a measured edge sits within microns, and the two tolerances are not the
    same number for a reason.

    Sampled rather than intersected: `polygonize` produces vertices collinear with
    a segment to within microns but not bit-identical, so line/line intersections
    silently return nothing.
    """
    ring = np.array(poly.exterior.coords)
    lengths = np.linalg.norm(np.diff(ring, axis=0), axis=1)

    points, owner = [], []
    for i, (a, b) in enumerate(zip(ring[:-1], ring[1:])):
        # Sample cell *centres*: endpoints are always on a fitted line by
        # construction, so sampling them would call every edge measured.
        n = max(int(lengths[i] / 0.005), 1)
        points.append(a + (b - a) * (np.arange(n)[:, None] + 0.5) / n)
        owner.append(np.full(n, i))
    P = np.vstack(points)
    owner = np.concatenate(owner)

    best = np.full(len(P), np.inf)
    for seg in segments:
        a, b = np.asarray(seg.coords[0]), np.asarray(seg.coords[-1])
        ab = b - a
        denom = ab @ ab
        if denom == 0:
            continue
        t = np.clip(((P - a) @ ab) / denom, 0.0, 1.0)
        d = np.linalg.norm(P - (a + t[:, None] * ab), axis=1)
        best = np.minimum(best, d)

    near = best <= tol_support
    branch = best <= tol_bridge
    total = float(lengths.sum())
    if total == 0.0:
        return 0.0, 0.0, []

    support = float(
        sum(lengths[i] * near[owner == i].mean() for i in range(len(lengths))) / total
    )
    bridged = float(
        sum(lengths[i] * (1.0 - branch[owner == i].mean()) for i in range(len(lengths)))
    )
    unsupported = [
        LineString([ring[i], ring[i + 1]])
        for i in range(len(lengths))
        if branch[owner == i].mean() < 0.999
    ]
    return support, bridged, unsupported


def fills_gap(chord: LineString, unsupported: list[LineString], tol: float = 0.003, share: float = 0.5) -> bool:
    """True when at least `share` of the chord lies along boundary nothing measures.

    Not all of it: a chord starts at a wall cap's midpoint, and the room's ring
    turns onto it only past the cap's room-side corner, so part of the chord is
    inside the wall body or outside this room's ring."""
    n = max(int(chord.length / 0.01), 2)
    P = np.array([chord.interpolate(s / n, normalized=True).coords[0] for s in range(n + 1)])
    on = np.zeros(len(P), bool)
    for seg in unsupported:
        a, b = np.asarray(seg.coords[0]), np.asarray(seg.coords[-1])
        ab = b - a
        if ab @ ab == 0:
            continue
        t = np.clip(((P - a) @ ab) / (ab @ ab), 0.0, 1.0)
        on |= np.linalg.norm(P - (a + t[:, None] * ab), axis=1) <= tol
    return bool(on.mean() >= share)


# ------------------------------------------------------------------- floor cover

def floor_coverage(
    points: np.ndarray,
    floor_z: float,
    rooms: list[Room],
    cell: float = 0.1,
    bridge: int = 2,
) -> dict[str, float]:
    """How much floor the scan saw, and how much of it landed in a room.

    Two numbers, because they answer two different questions and neither alone is
    honest:

    * `seen` is the floor the scan returned points from, binned to 100 mm cells
      and closed over a 0.4 m kernel so the gaps between scanner rings do not read
      as missing floor. It is a footprint, not a measurement - a cell with one
      return counts, and a cell the scanner could not reach does not.
    * `in_rooms` is how much of that observed floor lies inside a stage-3 room.

    `seen - in_rooms` is the floor the scan saw that no room claims; that is the
    number that stops "14 rooms" being read as "the floor". The reverse gap -
    room area the scan never returned floor for - is a different claim and is
    reported separately, because a room bounded by walls is still a room even
    where its floor was occluded by a desk.
    """
    band = points[(points[:, 2] > floor_z + 0.05) & (points[:, 2] < floor_z + 0.35)]
    if len(band) == 0:
        return {"seen": 0.0, "in_rooms": 0.0}

    ij = np.floor(band[:, :2] / cell).astype(np.int64)
    origin = ij.min(axis=0)
    ij -= origin
    grid = np.zeros((ij[:, 0].max() + 1, ij[:, 1].max() + 1), dtype=np.int32)
    np.add.at(grid, (ij[:, 0], ij[:, 1]), 1)

    k = 2 * bridge + 1
    # border_value=1: scipy treats out-of-frame as empty by default, which erodes
    # a band off the edge of any scan that fills the frame - a silent area loss.
    seen = ndimage.binary_closing(grid >= 1, np.ones((k, k)), border_value=1)
    seen = ndimage.binary_opening(seen, np.ones((3, 3)), border_value=1)

    cx = (origin[0] + np.arange(seen.shape[0]) + 0.5) * cell
    cy = (origin[1] + np.arange(seen.shape[1]) + 0.5) * cell
    X, Y = np.meshgrid(cx, cy, indexing="ij")
    inside = np.zeros(seen.shape, dtype=bool)
    for room in rooms:
        inside |= contains_xy(Polygon(room.polygon), X, Y)

    area = cell * cell
    return {
        "seen": float(seen.sum()) * area,
        "in_rooms": float((seen & inside).sum()) * area,
    }


# ------------------------------------------------------------------------- build


def build_rooms(model: Model, cfg: Config = Config()) -> tuple[list[Room], dict[str, float]]:
    walls = model.walls
    if not walls:
        return [], {}

    faces = [seg for wall in walls for _, seg in wall_faces(wall)]
    caps = [seg for wall in walls for seg in wall_caps(wall)]
    chords = closure_chords(walls, cfg)
    # closure-band chords (≤ 0.6 m) stay `short`: at that width rays passing a jog
    # or a wall offset are not a door. Ends they bridged need no second chord.
    rays = make_rays(model, cfg)
    evidenced, gap_report = gap_chords(model, cfg, rays, {(c.wall, c.end) for c in chords})
    chords += evidenced
    segments = faces + caps + [c.line for c in chords]

    feet = [footprint(w) for w in walls]
    faces_all = faces + caps

    rooms: list[Room] = []
    rejected = {"inside_wall": 0, "too_small": 0, "too_large": 0, "unsupported": 0}
    for poly in polygonize(unary_union(segments)):
        area = float(poly.area)
        point = poly.representative_point()
        if any(f.contains(point) for f in feet):
            rejected["inside_wall"] += 1
            continue
        if area < cfg.room_min_area:
            rejected["too_small"] += 1
            continue
        if area > cfg.room_max_area:
            rejected["too_large"] += 1
            continue
        support, bridged_m, unsupported = boundary_evidence(
            poly, faces_all, cfg.room_support_tol, cfg.room_bridge_tol
        )
        if support < cfg.room_min_support:
            rejected["unsupported"] += 1
            continue

        bounding = [
            w.id
            for w in walls
            if any(
                poly.exterior.intersection(seg.buffer(0.002)).length >= 0.25
                for seg in [s for _, s in wall_faces(w)] + wall_caps(w)
            )
        ]
        # Chords that actually fill a stretch of this ring nothing measured:
        # provenance for a bridged boundary, not a count of every chord computed.
        used = [
            {
                "wall": c.wall,
                "end": c.end,
                "gap_mm": round(c.gap_m * 1000, 1),
                "kind": c.kind,
            }
            for c in chords
            if c.recorded and fills_gap(c.line, unsupported)  # silent welds are noise
        ]
        parts = partition_lines(poly, model.rejected_faces, faces, cfg)
        ceiling_z, ceiling_cover = room_ceiling(model, poly, cfg)
        rooms.append(
            Room(
                id="",
                polygon=[(float(x), float(y)) for x, y in poly.exterior.coords],
                area_m2=area,
                perimeter_m=float(poly.length),
                floor_z=float(model.levels.floor_z) if model.levels else 0.0,
                ceiling_z=ceiling_z,
                ceiling_cover=ceiling_cover,
                ceiling_alt_z=room_ceiling_alt(model, poly, cfg, ceiling_z),
                walls=bounding,
                closure_gaps=used,
                bridged_m=bridged_m,
                support=support,
                derivation="closed-with-gap" if used else "closed",
                partition_lines=parts,
            )
        )

    rooms.sort(key=lambda r: (round(_centroid(r)[1], 2), round(_centroid(r)[0], 2), round(r.area_m2, 4)))
    for i, room in enumerate(rooms, 1):
        room.id = f"R{i:02d}"

    stats = {
        "candidates": len(rooms) + sum(rejected.values()),
        "rejected_inside_wall": rejected["inside_wall"],
        "rejected_small": rejected["too_small"],
        "rejected_large": rejected["too_large"],
        "rejected_unsupported": rejected["unsupported"],
        "chords": len(chords),
        "chords_occluded": sum(1 for c in chords if c.kind == "occluded"),
        "chords_opening": sum(1 for c in chords if c.kind == "opening"),
        "gaps_not_closed": gap_report,  # kind open (seen through, too wide) or unknown (nothing seen)
        "occluded_rule": "on" if rays else "off: no station",
        "chords_recorded": sum(1 for c in chords if c.recorded),
        "chords_on_rooms": sum(len(r.closure_gaps) for r in rooms),
        "longest_chord_m": max((c.gap_m for c in chords), default=0.0),
        "longest_room_gap_m": max(
            (g["gap_mm"] / 1000 for r in rooms for g in r.closure_gaps), default=0.0
        ),
        "closure_silent_mm": cfg.closure_silent * 1000,
        # The only chord length that changes a room: the longest stretch of an
        # accepted boundary that no measured surface supports.
        "longest_bridged_m": max((r.bridged_m for r in rooms), default=0.0),
        "rooms_with_bridged_boundary": sum(1 for r in rooms if r.bridged_m > 1e-6),
    }
    return rooms, stats


def _centroid(room: Room) -> tuple[float, float]:
    pts = np.array(room.polygon)
    return float(pts[:, 0].mean()), float(pts[:, 1].mean())


def _plane_covers(levels, poly: Polygon, planes) -> list[float] | None:
    """Share of `poly` that each plane's footprint covers, one-cell holes closed
    (light panels in a ceiling); None when the polygon holds no cell centre."""
    cell, origin = levels.cell, levels.origin
    minx, miny, maxx, maxy = poly.bounds
    i0, j0 = int(np.floor((minx - origin[0]) / cell)), int(np.floor((miny - origin[1]) / cell))
    i1, j1 = int(np.ceil((maxx - origin[0]) / cell)), int(np.ceil((maxy - origin[1]) / cell))
    ii, jj = np.meshgrid(np.arange(i0, i1), np.arange(j0, j1), indexing="ij")
    inside = contains_xy(poly, origin[0] + (ii + 0.5) * cell, origin[1] + (jj + 0.5) * cell)
    if not inside.any():
        return None
    out = []
    for plane in planes:
        mask = np.zeros(inside.shape, bool)
        c = plane.cells
        keep = (c[:, 0] >= i0) & (c[:, 0] < i1) & (c[:, 1] >= j0) & (c[:, 1] < j1)
        mask[c[keep, 0] - i0, c[keep, 1] - j0] = True
        mask = ndimage.binary_closing(mask, np.ones((3, 3)), border_value=0) | mask
        out.append(float((mask & inside).sum() / inside.sum()))
    return out


def room_ceiling(model: Model, poly: Polygon, cfg: Config) -> tuple[float | None, float]:
    """The nearest horizontal surface above *this* room (design §4.2).

    Every validated plane counts, not only the storey-sized ones: the sample's
    +2.39 m soffit is 4 m² and is the true ceiling of the rooms under it. A plane is
    this room's ceiling if it sits at least `room_min_clear` above the floor and
    covers `room_ceiling_cover` of the room once light-panel holes are closed.
    Returns `(z, coverage)`; `z` is None when no surface covers the room, which is
    reported rather than filled with the storey's height.
    """
    levels = model.levels
    if levels is None:
        return None, 0.0
    planes = [p for p in sorted(levels.planes, key=lambda p: p.z_fit)
              if p.z_fit >= levels.floor_z + cfg.room_min_clear and len(p.cells)]
    shares = _plane_covers(levels, poly, planes)
    if shares is None:
        return None, 0.0
    covers = [(float(p.z_fit), share) for p, share in zip(planes, shares)]

    # The ceiling is the surface that covers most of the room (ties: the lower),
    # so a hung panel or a cupboard top over a corner cannot win by being lowest.
    covers.sort(key=lambda zc: (-round(zc[1], 3), zc[0]))
    if not covers:
        return None, 0.0
    z, cover = covers[0]
    if cover < cfg.room_ceiling_cover:
        return None, cover
    return z, cover


def _cell_keys(c: np.ndarray) -> np.ndarray:
    return c[:, 0].astype(np.int64) * 1_000_003 + c[:, 1]  # as geometry.cell_overlap


def sunken_floors(levels, cfg: Config, report: list | None = None) -> list:
    """Validated planes a step below the floor (`room_fs_sunken_max`, round 19)
    that are a floor beside it, not under it or woven through it. Under it they
    are a slab's underside: a plane the slab-pair rule pairs as a lower face is
    skipped, and on a storey run (`floor_hint`) the rule is off, since the storey
    below's ceiling lies in the same band and cannot be told from a floor where
    the floor above it was not scanned (review R19-10). A plane sharing more than
    its rim with the floor's footprint (`room_fs_sunken_max_shared`) is skipped;
    kept planes lose the cells they share with it. Without the floor's footprint
    nothing can be told, so nothing is returned. `report` gets one entry per
    plane in the depth and area range, kept or not, and why."""
    if levels is None or cfg.room_fs_sunken_max <= 0 or cfg.floor_hint is not None:
        return []
    floor_cells = getattr(getattr(levels, "floor", None), "cells", None)
    if floor_cells is None or not len(floor_cells):
        return []
    undersides = [pr.lower for pr in getattr(levels, "pairs", None) or []]
    floor_keys = _cell_keys(floor_cells)
    out = []
    for p in getattr(levels, "planes", None) or []:
        if not cfg.side_floor_tol < levels.floor_z - p.z_fit <= cfg.room_fs_sunken_max:
            continue
        if p.area_m2 < cfg.room_fs_sunken_min_area or not len(p.cells):
            continue
        shared = np.isin(_cell_keys(p.cells), floor_keys)
        why = ("slab underside" if any(p is u for u in undersides)
               else "under or woven through the floor" if shared.mean() > cfg.room_fs_sunken_max_shared
               else None)
        if report is not None:
            report.append({"z": round(p.z_fit, 3), "area_m2": round(p.area_m2, 1),
                           "shared": round(float(shared.mean()), 3), "kept": why is None, "why": why})
        if why is None:
            out.append(replace(p, cells=p.cells[~shared]))
    return out


def room_floor(model: Model, poly: Polygon, cfg: Config, sunk: list | None = None) -> float:
    """The floor a room stands on: a sunken floor (round 19) that covers at least
    `room_floor_cover` of the room and more of it than the storey floor does; else
    the storey floor. `sunk`: `sunken_floors`, when the caller has it already."""
    levels = model.levels
    if levels is None:
        return 0.0
    sunk = sunken_floors(levels, cfg) if sunk is None else sunk
    if not sunk:
        return float(levels.floor_z)
    shares = _plane_covers(levels, poly, [levels.floor, *sunk])
    if shares is None:
        return float(levels.floor_z)
    best = int(np.argmax(shares))  # ties: the first, the storey floor
    if best == 0 or shares[best] < cfg.room_floor_cover:
        return float(levels.floor_z)
    return float(sunk[best - 1].z_fit)


def room_ceiling_alt(model: Model, poly: Polygon, cfg: Config, chosen: float | None) -> float | None:
    """A second surface covering a substantial share of the room: a two-height room."""
    if chosen is None or model.levels is None:
        return None
    saved = model.levels.planes
    try:
        model.levels.planes = [p for p in saved if abs(p.z_fit - chosen) > 1e-6]
        z, cover = room_ceiling(model, poly, cfg.with_(room_ceiling_cover=cfg.room_ceiling_alt_cover))
    finally:
        model.levels.planes = saved
    return z


# --------------------------------------------------------------------------- run


def run(model: Model, cfg: Config = Config()) -> None:
    rooms, stats = build_rooms(model, cfg)
    if cfg.room_free_space:
        from .s3_freespace import free_space_rooms

        extra, fs_stats = free_space_rooms(model, rooms, cfg)
        kept = []
        for r in extra:
            poly = Polygon(r.polygon)
            r.ceiling_z, r.ceiling_cover = room_ceiling(model, poly, cfg)
            if r.ceiling_z is None and r.ceiling_cover < cfg.room_fs_min_ceiling_cover:
                # floor at slab level with (nearly) nothing over it: a terrace or yard
                # seen through a door, not a room (review R4-4). A partly scanned
                # ceiling is still a ceiling (UoM lost a matched room at "none")
                fs_stats["rejected_no_ceiling"] = fs_stats.get("rejected_no_ceiling", 0) + 1
                continue
            ring = poly.exterior.buffer(cfg.room_fs_cell * 2.5)
            r.walls = [w.id for w in model.walls
                       if footprint(w).exterior.intersection(ring).length >= 0.25]
            kept.append(r)
        # wall-traced rooms keep the ids they had without this stage (review R4-12)
        kept.sort(key=lambda r: (round(_centroid(r)[1], 2), round(_centroid(r)[0], 2), round(r.area_m2, 4)))
        for i, room in enumerate(kept, len(rooms) + 1):
            room.id = f"R{i:02d}"
        fs_stats["added"] = len(kept)
        rooms = rooms + kept
        stats["free_space"] = fs_stats
    sunk = sunken_floors(model.levels, cfg)
    for r in rooms:
        r.floor_z = room_floor(model, Polygon(r.polygon), cfg, sunk)
    model.rooms = rooms

    cover = {"seen": 0.0, "in_rooms": 0.0}
    if model.cloud is not None and model.levels is not None:
        cover = floor_coverage(model.cloud.points, model.levels.floor_z, rooms)

    enclosed = sum(r.area_m2 for r in rooms)
    model.meta["floor_seen_m2"] = round(cover["seen"], 2)
    model.meta["floor_in_rooms_m2"] = round(cover["in_rooms"], 2)
    model.meta["floor_unclosed_m2"] = round(cover["seen"] - cover["in_rooms"], 2)
    model.meta["room_area_m2"] = round(enclosed, 2)
    # Room area the scan never returned floor for: walls prove the room, the
    # floor returns do not. Reported rather than subtracted.
    model.meta["room_area_unobserved_m2"] = round(max(enclosed - cover["in_rooms"], 0.0), 2)
    model.meta["wall_footprint_m2"] = round(sum(footprint(w).area for w in model.walls), 2)
    model.meta["room_stats"] = stats
