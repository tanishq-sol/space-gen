"""Room structure checked by scan2bim (engine "scan2bim", the default).

The legacy analyzer fixes the frame (gravity, floor, ceiling, yaw, centring:
`scan_to_scene`) and the outline, and its walls stay one per outline edge on the room's
inner surface (the contract the editor builds from). scan2bim (vendored in `./scan2bim`,
benchmarked on the ISPRS indoor LiDAR scans) then reads the same points in that frame.
Where one of its measured walls lies on an outline edge:
- the wall takes scan2bim's thickness when both faces were measured, and a confidence
  from how it was measured and how much of the edge it covers;
- its doors/windows are scan2bim's: a legacy opening it also finds is kept (finer edges,
  higher confidence), one it does not find is dropped, one only it finds is added.
Edges with no scan2bim wall keep their legacy values. If scan2bim cannot run or finds
fewer than `MIN_WALLS` walls, the legacy result is returned and a note says so.

Measured: the 5 synthetic test rooms pass unchanged (every wall matched); on
`test scene.ply` 8 of 39 outline edges matched, openings 14 -> 11 (4 unconfirmed dropped,
1 door added). Runtime about 2.5x legacy.

Frames: scene is Y-up (floor y = 0); scan2bim is Z-up. scene (X, Y, Z) <-> scan2bim (X, -Z, Y).
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from models.contracts import OpeningInterpretation, RoomInterpretation, WallInterpretation

from .analyzer import ProgressFn, RoomStructureOptions, RoomStructureResult, analyze_room
from .openings import OpeningDetector, merge_external_openings

MIN_WALLS = 3
CROP_MARGIN = 1.0  # metres around the legacy outline kept for scan2bim (floaters beyond are dropped)

# confidence by how the wall was measured (scan2bim's thickness_source / pairing)
WALL_CONFIDENCE = {"measured": 0.9, "single-sided": 0.75, "assumed": 0.6}
OPENING_CONFIDENCE = {"lintel": 0.8, "beam": 0.85, "gap": 0.7, "void": 0.5}


def _wall_confidence(w) -> float:
    src = w.thickness_source or ""
    if w.pairing == "paired" or src.startswith("measured"):
        return WALL_CONFIDENCE["measured"]
    if src.startswith("assumed"):
        return WALL_CONFIDENCE["assumed"]
    return WALL_CONFIDENCE["single-sided"]


def scene_points(
    positions: np.ndarray, opacity: np.ndarray | None, opts: RoomStructureOptions, result: RoomStructureResult
) -> np.ndarray:
    """Usable splat positions in the scene frame, cropped to the legacy outline."""
    pts = np.asarray(positions, dtype=np.float64).reshape(-1, 3)
    keep = np.isfinite(pts).all(axis=1)
    if opacity is not None:
        alpha = np.asarray(opacity, dtype=np.float64)
        if alpha.size and (alpha.min() < 0.0 or alpha.max() > 1.0):
            alpha = 1.0 / (1.0 + np.exp(-np.clip(alpha, -30.0, 30.0)))
        keep &= alpha >= opts.min_opacity
    M = np.asarray(result.scan_to_scene, dtype=np.float64).reshape(4, 4)
    q = pts[keep] @ M[:3, :3].T + M[:3, 3]  # M already carries opts.scale
    outline = np.asarray(result.interpretation.outline, dtype=np.float64)
    lo, hi = outline.min(axis=0) - CROP_MARGIN, outline.max(axis=0) + CROP_MARGIN
    h = result.interpretation.ceilingHeight
    inside = (
        (q[:, 0] >= lo[0])
        & (q[:, 0] <= hi[0])
        & (q[:, 2] >= lo[1])
        & (q[:, 2] <= hi[1])
        & (q[:, 1] > -0.3)
        & (q[:, 1] < h + 0.3)
    )
    return q[inside]


def _match(a: np.ndarray, b: np.ndarray, model) -> tuple[object, float] | None:
    """The scan2bim wall whose face lies on the outline edge a-b (Z-up xy), and the
    share of the edge it covers: parallel within 5 deg, a face (axis +- half the
    thickness) within 0.1 m of the edge line, overlapping >= 30 % of the edge."""
    d = (b - a) / max(float(np.linalg.norm(b - a)), 1e-9)
    n = np.array([-d[1], d[0]])
    length = float(np.linalg.norm(b - a))
    best = None
    for w in model.walls:
        if abs(float(w.perp @ d)) < np.cos(np.radians(5.0)):
            continue
        p0, p1 = w.axis_offset() * w.unit + w.r0 * w.perp, w.axis_offset() * w.unit + w.r1 * w.perp
        dist = abs(float(((p0 + p1) / 2 - a) @ n))
        half = max(w.thickness or 0.1, 0.02) / 2
        if min(abs(dist - half), dist) > 0.1:
            continue
        s0, s1 = sorted((float((p0 - a) @ d), float((p1 - a) @ d)))
        cover = (min(s1, length) - max(s0, 0.0)) / length
        if cover >= 0.3 and (best is None or cover > best[1]):
            best = (w, cover)
    return best


# Outline regularisation. A wall line is a scan2bim wall (its face on the room side) or a
# legacy edge well covered by wall points: confidence >= LINE_CONF and at least
# LINE_MIN_AXIS m long when within AXIS_TOL_DEG of the room's axes, LINE_MIN_OTHER m
# otherwise (shorter slanted edges are corners cut by furniture hiding the floor).
LINE_CONF = 0.9
LINE_MIN_AXIS = 1.0
LINE_MIN_OTHER = 1.5
AXIS_TOL_DEG = 10.0
# the regular outline keeps at least this share of the floor outline, and adds at most this
# share behind furniture (a sofa or cabinets along the walls)
OUTLINE_MIN_KEPT = 0.95
OUTLINE_MAX_ADDED = 0.30
INFERRED_CONFIDENCE = 0.3  # wall stretch behind furniture, with no legacy edge on it
LINE_SAME = 0.15  # m: a parallel line this close to a kept one is the same wall (no sliver walls)
MIN_EDGE = 0.3  # m: shorter outline edges are folded into their neighbours, as the legacy outline


def _lines(interp: RoomInterpretation, model) -> list[tuple[np.ndarray, np.ndarray]]:
    """Wall lines as (point, unit direction) in scene (x, z): scan2bim's measured faces
    first, longest first, then the legacy edges, longest first. A line parallel to one
    already kept and within LINE_SAME of it is the same wall and is skipped."""
    outline = np.asarray(interp.outline, dtype=np.float64)
    centre = outline.mean(axis=0)
    candidates: list[tuple[float, np.ndarray, np.ndarray]] = []  # (priority, point, direction)
    for w in model.walls:
        u = np.array([w.unit[0], -w.unit[1]])  # scan2bim (X, Y) -> scene (x, z = -Y)
        v = np.array([w.perp[0], -w.perp[1]])
        face = min(w.plane_offsets(), key=lambda o: abs(o - float(centre @ u)))  # the room side
        candidates.append((1e6 + abs(w.r1 - w.r0), face * u + (w.r0 + w.r1) / 2 * v, v))
    for wall in interp.walls:
        a, b = np.array([wall.start[0], wall.start[2]]), np.array([wall.end[0], wall.end[2]])
        length = float(np.linalg.norm(b - a))
        if length < LINE_MIN_AXIS or wall.confidence < LINE_CONF:
            continue
        d = (b - a) / length
        off_axis = abs(((np.degrees(np.arctan2(d[1], d[0])) + 45.0) % 90.0) - 45.0)
        if off_axis > AXIS_TOL_DEG and length < LINE_MIN_OTHER:
            continue
        candidates.append((length, a, d))
    lines: list[tuple[np.ndarray, np.ndarray]] = []
    for _, a, d in sorted(candidates, key=lambda c: -c[0]):
        n = np.array([-d[1], d[0]])
        if any(abs(float(dd @ d)) > np.cos(np.radians(3.0)) and abs(float((p - a) @ n)) < LINE_SAME for p, dd in lines):
            continue
        lines.append((a, d))
    return lines


def _fold_short_edges(verts: np.ndarray) -> np.ndarray:
    """Outline vertices without edges shorter than MIN_EDGE: a short edge between two
    crossing neighbours goes to their intersection; a jog between two parallel ones
    moves the shorter neighbour onto the longer one's line."""
    v = [np.asarray(p, dtype=np.float64) for p in verts]
    while len(v) > 3:
        lengths = [float(np.linalg.norm(v[(i + 1) % len(v)] - v[i])) for i in range(len(v))]
        i = int(np.argmin(lengths))
        if lengths[i] >= MIN_EDGE:
            break
        n = len(v)
        a, b = v[(i - 1) % n], v[i]  # the edge before
        c, d = v[(i + 1) % n], v[(i + 2) % n]  # the edge after
        u1, u2 = (b - a) / max(np.linalg.norm(b - a), 1e-9), (d - c) / max(np.linalg.norm(d - c), 1e-9)
        n1, n2 = np.array([-u1[1], u1[0]]), np.array([-u2[1], u2[0]])
        corner = _intersect_lines(n1, float(n1 @ a), n2, float(n2 @ c))
        if corner is None:  # a jog: the shorter neighbour moves onto the longer one's line
            if np.linalg.norm(b - a) >= np.linalg.norm(d - c):
                v[(i + 2) % n] = d + n1 * (float(n1 @ a) - float(n1 @ d))
            else:
                v[(i - 1) % n] = a + n2 * (float(n2 @ c) - float(n2 @ a))
        else:
            v[i] = corner
        del v[(i + 1) % n]
    return np.array(v)


def _intersect_lines(n1: np.ndarray, c1: float, n2: np.ndarray, c2: float) -> np.ndarray | None:
    det = n1[0] * n2[1] - n1[1] * n2[0]
    if abs(det) < np.sin(np.radians(10.0)):
        return None
    return np.array([(c1 * n2[1] - c2 * n1[1]) / det, (n1[0] * c2 - n2[0] * c1) / det])


def regularize_outline(interp: RoomInterpretation, model) -> tuple[RoomInterpretation, dict]:
    """The outline rebuilt from wall lines: the plan is cut along every wall line and the
    cells lying mostly inside the floor outline are kept. A bite the outline takes where
    furniture hides the floor along a wall lies in a cell that is mostly floor, so it is
    filled; corners then sit on wall-line intersections. Kept only when it has fewer
    corners, keeps OUTLINE_MIN_KEPT of the floor outline and adds at most OUTLINE_MAX_ADDED.
    One wall per edge (the editor's contract); legacy openings move to the edge they lie on."""
    from shapely.geometry import LineString, Polygon, box
    from shapely.geometry.polygon import orient
    from shapely.ops import polygonize, unary_union

    old = Polygon(interp.outline).buffer(0)
    stats: dict = {"from": len(interp.outline)}
    lines = _lines(interp, model)
    stats["lines"] = len(lines)
    if len(lines) < 3 or old.is_empty or old.geom_type != "Polygon":
        return interp, {**stats, "kept": "legacy (too few wall lines)"}
    # where no wall line closes the room (a scan fading out), it ends at the furthest floor seen
    frame = box(*old.bounds)
    reach = 2.0 * float(np.hypot(frame.bounds[2] - frame.bounds[0], frame.bounds[3] - frame.bounds[1]))
    segs = [LineString([p - reach * d, p + reach * d]).intersection(frame) for p, d in lines]
    cells = list(polygonize(unary_union([s for s in segs if not s.is_empty] + [frame.exterior])))
    keep = [c for c in cells if c.intersection(old).area >= 0.5 * c.area]
    new = unary_union(keep) if keep else Polygon()
    if new.geom_type == "MultiPolygon":
        new = max(new.geoms, key=lambda g: g.area)
    if new.is_empty or new.geom_type != "Polygon":
        return interp, {**stats, "kept": "legacy (no cells)"}
    new = orient(Polygon(new.exterior).simplify(0.02), sign=1.0)  # CCW in (x, z), as the analyzer
    new = Polygon(_fold_short_edges(np.asarray(new.exterior.coords)[:-1]))
    if not new.is_valid or new.area <= 0:
        return interp, {**stats, "kept": "legacy (invalid after folding short edges)"}
    verts = np.asarray(new.exterior.coords)[:-1]
    both = float(new.intersection(old).area)
    kept, added = both / old.area, (new.area - both) / old.area
    stats.update(to=len(verts), kept=round(kept, 3), added=round(added, 3))
    if len(verts) < 3 or len(verts) >= len(interp.outline) or kept < OUTLINE_MIN_KEPT or added > OUTLINE_MAX_ADDED:
        return interp, {**stats, "kept": "legacy"}

    old_walls = [(np.array([w.start[0], w.start[2]]), np.array([w.end[0], w.end[2]]), w) for w in interp.walls]
    walls: list[WallInterpretation] = []
    for k in range(len(verts)):
        a, b = verts[k], verts[(k + 1) % len(verts)]
        length = float(np.linalg.norm(b - a))
        d, n = (b - a) / length, np.array([-(b - a)[1], (b - a)[0]]) / length
        # confidence: the legacy edges lying on this edge, by length; the rest inferred
        support = 0.0
        for p, q, w in old_walls:
            if abs(float((q - p) @ d)) < np.cos(np.radians(10.0)) * np.linalg.norm(q - p):
                continue
            if max(abs(float((p - a) @ n)), abs(float((q - a) @ n))) > 0.15:
                continue
            s0, s1 = sorted((float((p - a) @ d), float((q - a) @ d)))
            support += max(0.0, min(s1, length) - max(s0, 0.0)) * w.confidence
        covered = min(support, length)
        conf = (covered + INFERRED_CONFIDENCE * max(length - support, 0.0)) / length
        walls.append(
            WallInterpretation(
                id=f"wall_{k}",
                start=(float(a[0]), 0.0, float(a[1])),
                end=(float(b[0]), 0.0, float(b[1])),
                height=interp.ceilingHeight,
                thickness=interp.walls[0].thickness,
                confidence=float(np.clip(conf, 0.05, 1.0)),
                provenance="auto",
            )
        )

    openings: list[OpeningInterpretation] = []
    by_id = {w.id: (p, q) for p, q, w in old_walls}
    for o in interp.openings:
        p, q = by_id[o.wallId]
        centre = p + (q - p) / max(float(np.linalg.norm(q - p)), 1e-9) * o.offset
        for k, w in enumerate(walls):
            a, b = np.array([w.start[0], w.start[2]]), np.array([w.end[0], w.end[2]])
            length = float(np.linalg.norm(b - a))
            d = (b - a) / length
            off = float((centre - a) @ d)
            if abs(float((centre - a) @ np.array([-d[1], d[0]]))) <= 0.15 and 0.0 <= off <= length:
                openings.append(o.model_copy(update={"wallId": w.id, "offset": off, "width": min(o.width, length)}))
                break
    stats["openingsDropped"] = len(interp.openings) - len(openings)
    out = interp.model_copy(
        update={"outline": [(float(x), float(z)) for x, z in verts], "walls": walls, "openings": openings}
    )
    return out, {**stats, "kept": "regularized"}


def enrich_walls(interp: RoomInterpretation, model, floor: float, detect_openings: bool):
    """Keep the outline's walls (the contract: one wall per outline edge, on the room's
    inner surface); where scan2bim measured the same wall take its thickness, raise the
    confidence, and take its doors/windows in place of the legacy ones."""
    walls: list[WallInterpretation] = []
    openings: list[OpeningInterpretation] = []
    matched = 0
    legacy_by_wall: dict[str, list[OpeningInterpretation]] = {}
    for o in interp.openings:
        legacy_by_wall.setdefault(o.wallId, []).append(o)
    for wall in interp.walls:
        a = np.array([wall.start[0], -wall.start[2]])
        b = np.array([wall.end[0], -wall.end[2]])
        hit = _match(a, b, model)
        if hit is None:
            walls.append(wall)
            openings.extend(legacy_by_wall.get(wall.id, []))
            continue
        w, cover = hit
        matched += 1
        measured = w.pairing == "paired" or not (w.thickness_source or "").startswith("assumed")
        walls.append(
            wall.model_copy(
                update={
                    "thickness": float(max(w.thickness, 0.02)) if measured and w.thickness else wall.thickness,
                    "confidence": float(max(wall.confidence, _wall_confidence(w) * min(1.0, 0.5 + cover))),
                }
            )
        )
        if not detect_openings:
            continue
        d = (b - a) / max(float(np.linalg.norm(b - a)), 1e-9)
        length = float(np.linalg.norm(b - a))
        legacy = legacy_by_wall.get(wall.id, [])
        confirmed: set[int] = set()
        for j, o in enumerate(w.openings):
            sill = max(float(o.sill_z) - floor, 0.0)
            oh = float(o.head_z) - floor - sill
            c = w.axis_offset() * w.unit + (o.along0 + o.along1) / 2 * w.perp
            off = float((c - a) @ d)
            if o.width <= 0 or oh <= 0 or not (0.0 <= off <= length):
                continue
            # the same opening read by the legacy detector: its edges are finer (0.2 m
            # columns here), so it is kept, confirmed, with the higher confidence
            twin = next(
                (
                    k
                    for k, x in enumerate(legacy)
                    if k not in confirmed
                    and min(x.offset + x.width / 2, off + o.width / 2) - max(x.offset - x.width / 2, off - o.width / 2)
                    >= 0.5 * min(x.width, o.width)
                ),
                None,
            )
            kind = o.kind if o.kind in ("door", "window") else "opening"
            conf = OPENING_CONFIDENCE.get(o.source or "void", 0.5) * (1.0 if kind != "opening" else 0.6)
            if twin is not None:
                confirmed.add(twin)
                openings.append(
                    legacy[twin].model_copy(update={"confidence": float(max(legacy[twin].confidence, conf))})
                )
                continue
            openings.append(
                OpeningInterpretation(
                    id=f"{wall.id}_opening_{j}",
                    wallId=wall.id,
                    kind=kind,
                    offset=off,
                    width=float(min(o.width, length)),
                    height=oh,
                    sill=sill,
                    confidence=float(conf),
                    provenance="auto",
                )
            )
    return walls, openings, matched


def analyze_room_scan2bim(
    positions: np.ndarray,
    opacity: np.ndarray | None = None,
    colmap_points: np.ndarray | None = None,
    options: RoomStructureOptions | None = None,
    opening_detector: OpeningDetector | None = None,
    progress: ProgressFn | None = None,
) -> RoomStructureResult:
    opts = options or RoomStructureOptions()
    report = progress or (lambda stage, fraction: None)
    base = analyze_room(positions, opacity, colmap_points, replace(opts, engine="legacy"), None, report)
    try:
        from .scan2bim.cloud import decimate
        from .scan2bim.config import Config
        from .scan2bim.model import Cloud
        from .scan2bim.pipeline import run_pipeline
    except ImportError as exc:  # scipy / shapely missing: keep the legacy result
        base.diagnostics.setdefault("notes", []).append(f"scan2bim unavailable ({exc}); legacy walls kept")
        return base

    report("walls", 0.75)
    q = scene_points(positions, opacity, opts, base)
    if colmap_points is not None and len(colmap_points):
        M = np.asarray(base.scan_to_scene, dtype=np.float64).reshape(4, 4)
        extra = np.asarray(colmap_points, dtype=np.float64).reshape(-1, 3)
        q = np.concatenate([q, extra[np.isfinite(extra).all(axis=1)] @ M[:3, :3].T + M[:3, 3]])
    cfg = Config(floor_hint=0.0, multi_storey=False)
    cloud = decimate(Cloud(points=np.c_[q[:, 0], -q[:, 2], q[:, 1]]), cfg.decimate)
    try:
        model = run_pipeline("splat", None, config=cfg, cloud=cloud)
    except Exception as exc:  # noqa: BLE001 - a failed engine costs its own result, never the job
        base.diagnostics.setdefault("notes", []).append(f"scan2bim failed ({type(exc).__name__}); legacy walls kept")
        return base
    if len(model.walls) < MIN_WALLS or model.levels is None:
        base.diagnostics.setdefault("notes", []).append(
            f"scan2bim found {len(model.walls)} walls (< {MIN_WALLS}); legacy walls kept"
        )
        return base

    interp, outline_stats = regularize_outline(base.interpretation, model)
    floor = float(model.levels.floor_z)
    walls, openings, matched = enrich_walls(interp, model, floor, opts.detect_openings)
    result_interp = interp.model_copy(update={"walls": walls, "openings": openings})
    if opening_detector is not None:
        result_interp = merge_external_openings(result_interp, opening_detector(result_interp))
    diagnostics = dict(base.diagnostics)
    diagnostics["engine"] = "scan2bim"
    diagnostics["outline"] = {
        **diagnostics.get("outline", {}),
        "vertices": len(interp.outline),
        "regularization": outline_stats,
    }
    diagnostics["scan2bim"] = {
        "walls": len(model.walls),
        "wallsMatched": matched,
        "wallsPaired": sum(1 for w in model.walls if w.pairing == "paired"),
        "openings": len(openings),
        "rooms": len(model.rooms),
        "points": int(len(cloud.points)),
    }
    return RoomStructureResult(result_interp, base.scan_to_scene, diagnostics)
