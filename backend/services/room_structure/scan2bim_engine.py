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


def scene_points(positions: np.ndarray, opacity: np.ndarray | None, opts: RoomStructureOptions,
                 result: RoomStructureResult) -> np.ndarray:
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
    inside = ((q[:, 0] >= lo[0]) & (q[:, 0] <= hi[0]) & (q[:, 2] >= lo[1]) & (q[:, 2] <= hi[1])
              & (q[:, 1] > -0.3) & (q[:, 1] < h + 0.3))
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
        walls.append(wall.model_copy(update={
            "thickness": float(max(w.thickness, 0.02)) if measured and w.thickness else wall.thickness,
            "confidence": float(max(wall.confidence, _wall_confidence(w) * min(1.0, 0.5 + cover))),
        }))
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
            twin = next((k for k, x in enumerate(legacy) if k not in confirmed and
                         min(x.offset + x.width / 2, off + o.width / 2) - max(x.offset - x.width / 2, off - o.width / 2)
                         >= 0.5 * min(x.width, o.width)), None)
            kind = o.kind if o.kind in ("door", "window") else "opening"
            conf = OPENING_CONFIDENCE.get(o.source or "void", 0.5) * (1.0 if kind != "opening" else 0.6)
            if twin is not None:
                confirmed.add(twin)
                openings.append(legacy[twin].model_copy(update={"confidence": float(max(legacy[twin].confidence, conf))}))
                continue
            openings.append(OpeningInterpretation(
                id=f"{wall.id}_opening_{j}", wallId=wall.id, kind=kind, offset=off,
                width=float(min(o.width, length)), height=oh, sill=sill,
                confidence=float(conf), provenance="auto",
            ))
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
            f"scan2bim found {len(model.walls)} walls (< {MIN_WALLS}); legacy walls kept")
        return base

    interp = base.interpretation
    floor = float(model.levels.floor_z)
    walls, openings, matched = enrich_walls(interp, model, floor, opts.detect_openings)
    result_interp = interp.model_copy(update={"walls": walls, "openings": openings})
    if opening_detector is not None:
        result_interp = merge_external_openings(result_interp, opening_detector(result_interp))
    diagnostics = dict(base.diagnostics)
    diagnostics["engine"] = "scan2bim"
    diagnostics["scan2bim"] = {
        "walls": len(model.walls),
        "wallsMatched": matched,
        "wallsPaired": sum(1 for w in model.walls if w.pairing == "paired"),
        "openings": len(openings),
        "rooms": len(model.rooms),
        "points": int(len(cloud.points)),
    }
    return RoomStructureResult(result_interp, base.scan_to_scene, diagnostics)
