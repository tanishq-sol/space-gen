"""Stage registry and the `--until` runner.

Each stage is a module with `run(model, cfg)`. A stage may read only what earlier
stages wrote, which is what makes `--until N` meaningful: stopping at N leaves a
model that is exactly the input to N+1, with nothing half-applied.
"""

from __future__ import annotations

import time
import traceback
from pathlib import Path

import numpy as np

from . import cloud as cloudmod
from .config import Config
from .model import Model
from .stages import s1_faces, s2_walls, s3_rooms, s4_openings

# name, module, whether it is built
STAGES: dict[int, tuple[str, object | None]] = {
    0: ("ingest", None),
    1: ("levels + faces", s1_faces),
    2: ("wall solids", s2_walls),
    3: ("rooms", s3_rooms),
    4: ("openings", s4_openings),
    5: ("fixtures + MEP", None),
    6: ("verification gate", None),
    7: ("IFC4 writer", None),
    8: ("Pascal scene writer", None),
}

LAST_BUILT = max(k for k, (_, mod) in STAGES.items() if mod is not None or k == 0)


class InputRejected(RuntimeError):
    """Stage 0 refused the cloud. Distinct from a crash: the input is wrong."""


def seen_area(
    points: np.ndarray, floor_z: float, band: tuple[float, float] = (0.5, 2.0), cell: float = 0.5
) -> list[list[list[list[float]]]]:
    """Plan outline of what the scan saw on a storey: the cells of `cell` m holding a point
    floor + band[0] .. band[1] (the evaluator's wall band), grown one cell, holes filled.
    For scoring a scan against a reference that models more than it covers (evaluate's
    `*_seen` scores, round 25). A list of polygons, each [exterior, *holes] of [x, y]."""
    from scipy import ndimage
    from shapely.geometry import MultiPolygon, box
    from shapely.ops import unary_union

    z = points[:, 2]
    p = points[(z > floor_z + band[0]) & (z < floor_z + band[1]), :2]
    if len(p) == 0:
        return []
    lo = np.floor(p.min(0) / cell) * cell - cell
    ij = np.floor((p - lo) / cell).astype(np.int64)
    g = np.zeros(tuple(ij.max(0) + 2), bool)
    g[ij[:, 0], ij[:, 1]] = True
    g = ndimage.binary_fill_holes(ndimage.binary_dilation(g))
    boxes = []
    for i in range(g.shape[0]):  # one box per run of a row: far fewer than one per cell
        edges = np.flatnonzero(np.diff(np.r_[0, g[i].astype(np.int8), 0]))
        for a, b in zip(edges[::2], edges[1::2]):
            boxes.append(box(lo[0] + i * cell, lo[1] + a * cell, lo[0] + (i + 1) * cell, lo[1] + b * cell))
    u = unary_union(boxes).simplify(cell * 0.25)
    polys = u.geoms if isinstance(u, MultiPolygon) else [u]
    return [
        [[[round(x, 3), round(y, 3)] for x, y in r.coords] for r in (q.exterior, *q.interiors)]
        for q in polys
        if not q.is_empty
    ]


def run_pipeline(
    input_path,
    out_dir=None,
    until: int = LAST_BUILT,
    config: Config = Config(),
    export_ifc: bool = False,
    export_scene: bool = False,
    cloud=None,
) -> Model:
    """Run the stages on `input_path`, or on `cloud` (a `Cloud` already in memory,
    Z-up metres; then `input_path` only names the source in the report)."""
    if until not in STAGES:
        raise ValueError(f"--until must be 0..8, got {until}")
    if until > LAST_BUILT:
        missing = [f"{k} ({STAGES[k][0]})" for k in range(LAST_BUILT + 1, until + 1)]
        raise NotImplementedError(
            f"stage {until} is designed but not built. Not built: {', '.join(missing)}. Run with --until {LAST_BUILT}."
        )

    model = Model()
    path = Path(input_path)
    model.meta = {
        "source": str(path),
        "converter": "scan2bim 0.1.0",
        "units": "metres",
        "up_axis": "Z",
        "seed": 0,
    }

    def timed(stage: int, label: str, fn):
        start = time.perf_counter()
        try:
            fn()
        except Exception:
            raise RuntimeError(f"stage {stage} ({label}) failed:\n{traceback.format_exc()}") from None
        model.timings[f"{stage}_{label}"] = time.perf_counter() - start

    def stage0():
        if cloud is not None:
            loaded = cloud
            if loaded.normals is None:
                cloudmod.estimate_normals(loaded)
        else:
            model.meta["source_hash"] = cloudmod.source_hash(path)
            loaded = cloudmod.load(path, config)
        # a cloud we read is ours to trim in place; a caller's cloud is left untouched
        loaded = cloudmod.voxel_trim(loaded, config, in_place=cloud is None)
        cloudmod.establish_station(
            loaded,
            config.station,
            height=config.station_ground,
            force=config.station_force,
            pose_height=config.scan_pose_ground,
        )
        model.meta["decimate_m"] = config.decimate
        model.meta["points_read"] = loaded.n_input
        model.meta["points_dropped"] = loaded.n_dropped
        reasons = cloudmod.validate(loaded)
        if reasons:
            raise InputRejected("; ".join(reasons))
        model.cloud = loaded

    timed(0, "ingest", stage0)

    for stage in range(1, until + 1):
        label, module = STAGES[stage]
        if module is None:
            raise NotImplementedError(f"stage {stage} ({label}) is not built")
        timed(stage, label, lambda m=module: m.run(model, config))  # type: ignore[union-attr]
    if model.levels is not None and model.cloud is not None:
        model.meta["seen_area"] = seen_area(model.cloud.points, model.levels.floor_z)

    if config.multi_storey and until >= 2 and model.levels is not None and model.cloud is not None:

        def storeys() -> None:
            from .stages.s1_faces import find_storeys

            floors = find_storeys(model.cloud, model.levels, config, report=model.meta)
            model.meta["storey_floors"] = [round(f, 3) for f in floors]
            for k, f in enumerate(floors):
                if abs(f - model.levels.floor_z) < 1e-6:
                    continue
                top = floors[k + 1] - 0.05 if k + 1 < len(floors) else np.inf
                keep = (model.cloud.points[:, 2] > f - 0.30) & (model.cloud.points[:, 2] < top)
                sub = Model()
                sub.meta = {
                    **{
                        k2: v
                        for k2, v in model.meta.items()
                        if k2 in ("source", "source_hash", "converter", "units", "up_axis", "decimate_m")
                    },
                    "storey_of": model.meta.get("source"),
                    "storey_floor_hint": round(f, 3),
                }
                sub.cloud = model.cloud.take(keep)
                cfg_k = config.with_(floor_hint=float(f), multi_storey=False)
                try:
                    for stage in range(1, until + 1):
                        STAGES[stage][1].run(sub, cfg_k)  # type: ignore[union-attr]
                except Exception as exc:  # noqa: BLE001 - one storey failing costs that storey
                    model.meta.setdefault("storeys_skipped", []).append(
                        {"floor_z": round(f, 3), "why": f"{type(exc).__name__}: {exc}"[:200]}
                    )
                    continue
                if not sub.walls:
                    model.meta.setdefault("storeys_skipped", []).append({"floor_z": round(f, 3), "why": "no walls"})
                    continue
                if sub.levels is not None:
                    sub.meta["seen_area"] = seen_area(sub.cloud.points, sub.levels.floor_z)
                sub.cloud = None  # not kept: the main model holds the cloud
                model.storeys.append(sub)

        timed(9, "storeys", storeys)

    def export(kind: str, suffix: str, write) -> None:
        if out_dir is None:
            raise ValueError(f"{kind} export needs an output directory")
        if model.levels is None or not model.walls:
            # Unattended runs must still leave a model and a report: a scan with no
            # walls is a partial result to review, not a crash.
            why = "no walls were found" if until >= 2 else "--until is below 2"
            model.meta.setdefault("exports_skipped", {})[kind] = why
            return
        stem = Path(str(model.meta.get("source", "scan"))).stem or "scan"
        # Written before write_run so the summary lands in the model JSON. A
        # writer that fails costs its own file, never the model and report.
        try:
            model.meta[kind] = write(model, Path(out_dir) / f"{stem}{suffix}")
        except Exception as exc:  # noqa: BLE001 - recorded, run reported as partial
            model.meta.setdefault("exports_skipped", {})[kind] = f"{type(exc).__name__}: {exc}"

    if export_ifc:
        from .export_ifc import write_ifc

        export("ifc", ".ifc", write_ifc)
    if export_scene:
        from .export_pascal import write_scene

        export("scene", ".scene.json", write_scene)

    if out_dir is not None:
        from .report import write_run

        write_run(model, Path(out_dir), until=until)

    return model
