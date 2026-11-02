"""The internal model.

One geometric model feeds both writers (IFC4 and the Pascal scene), so nothing in
here knows which format will consume it. Fields are named after what they measure,
not after the IFC entity they become — see design §7.

Units are metres and degrees everywhere. Angles are the *normal* direction of a
wall face, counter-clockwise from +x, taken modulo 180, so a wall and the same wall
seen from the other side share a direction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

# --------------------------------------------------------------------------- cloud


@dataclass(slots=True)
class Cloud:
    """Points in metres, Z-up, with unit normals.

    `normals` may be None for formats that do not carry them; stage 1 estimates
    them when it needs them. `colours` (0-1 RGB) and `intensity` (0-1) are carried
    but deliberately unused by the classifier (design §4.6). After decimation each
    point is a voxel centroid and `hits` is how many raw returns it averages.
    """

    points: np.ndarray
    normals: np.ndarray | None = None
    colours: np.ndarray | None = None
    intensity: np.ndarray | None = None
    hits: np.ndarray | None = None
    source: str = ""
    n_input: int = 0
    n_dropped: int = 0
    # Scanner position for a single-station cloud, and how it was established.
    # Decides which side of every face was observed (design §4.2 step 6).
    station: np.ndarray | None = None
    station_source: str = ""
    # Structured form of the same decision (see cloud.establish_station).
    station_info: dict[str, Any] = field(default_factory=dict)
    # A station the file offers, before establish_station checks it.
    file_station: np.ndarray | None = None
    file_station_kind: str = ""
    # Multi-scan input: the scan each point came from, and each scan's offered
    # station (None: nothing usable) with how the file gave it. establish_station
    # turns these into `stations` (one row per scan, NaN where unknown); a point's
    # scanner is stations[scan_index].
    scan_index: np.ndarray | None = None
    scan_stations: list[tuple[np.ndarray | None, str]] = field(default_factory=list)
    stations: np.ndarray | None = None
    # Station heights can be trusted (tripod poses) or not (a trajectory's z may be
    # the platform, not the sensor): only plan positions are used when False.
    stations_z_known: bool = True
    # Acquisition time per point, when the file has it (mobile scans).
    times: np.ndarray | None = None

    def __len__(self) -> int:
        return len(self.points)

    def take(self, idx: np.ndarray) -> "Cloud":
        """A copy keeping only the points at `idx` (indices or a boolean mask)."""
        pick = lambda a: None if a is None else a[idx]
        return Cloud(
            points=self.points[idx], normals=pick(self.normals), colours=pick(self.colours),
            intensity=pick(self.intensity), hits=pick(self.hits), source=self.source,
            n_input=self.n_input, n_dropped=self.n_dropped, station=self.station,
            station_source=self.station_source, station_info=dict(self.station_info),
            file_station=self.file_station, file_station_kind=self.file_station_kind,
            scan_index=pick(self.scan_index), scan_stations=list(self.scan_stations),
            stations=self.stations, stations_z_known=self.stations_z_known, times=pick(self.times),
        )

    def station_rows(self) -> tuple[np.ndarray, np.ndarray] | None:
        """(stations (S, 3), scan index per point) for every known station, or None.

        One code path for one station and many: a single-station cloud is one row
        with every point on it. Points whose scan has no station get index -1."""
        if self.stations is not None and np.isfinite(self.stations).all(1).any():
            idx = self.scan_index if self.scan_index is not None else np.zeros(len(self.points), np.int64)
            ok = np.isfinite(self.stations).all(1)
            idx = np.where((idx >= 0) & (idx < len(ok)) & ok[np.clip(idx, 0, len(ok) - 1)], idx, -1)
            return self.stations, idx
        if self.station is not None:
            return self.station.reshape(1, 3), np.zeros(len(self.points), np.int64)
        return None

    @property
    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        return self.points.min(0), self.points.max(0)


# -------------------------------------------------------------------------- levels


@dataclass(slots=True)
class Plane:
    """A validated horizontal surface.

    `cells` holds the occupied cells of the global 0.1 m grid and is what makes two
    planes at similar heights distinguishable: a slab's top and bottom share a
    footprint, two ceilings in two rooms do not.
    """

    z: float
    z_fit: float
    rms_m: float
    slope_deg: float
    area_m2: float
    fill: float
    n_points: int
    cells: np.ndarray = field(repr=False, default_factory=lambda: np.zeros((0, 2), np.int32))

    def to_dict(self) -> dict[str, Any]:
        return {
            "z": round(self.z, 3),
            "z_fit": round(self.z_fit, 4),
            "rms_mm": round(self.rms_m * 1000, 2),
            "slope_deg": round(self.slope_deg, 2),
            "area_m2": round(self.area_m2, 2),
            "fill": round(self.fill, 2),
            "n_points": self.n_points,
        }


@dataclass(slots=True)
class SlabPair:
    """Two parallel planes 100-500 mm apart that share a footprint: one slab.

    `lower` is its underside (the ceiling of the space below), `upper` its top
    (the floor of the space above).
    """

    lower: Plane
    upper: Plane
    overlap: float
    thickness: float


@dataclass(slots=True)
class LevelSet:
    planes: list[Plane]
    pairs: list[SlabPair]
    floor: Plane
    floor_z: float
    ceilings: list[Plane]
    # world xy of grid cell (0, 0) for every plane's `cells`, and the cell size
    origin: np.ndarray = field(default_factory=lambda: np.zeros(2))
    cell: float = 0.1

    def to_dict(self) -> dict[str, Any]:
        return {
            "floor_z": round(self.floor_z, 3),
            "floor": self.floor.to_dict(),
            "pairs": [
                {
                    "lower": round(p.lower.z_fit, 3),
                    "upper": round(p.upper.z_fit, 3),
                    "thickness": round(p.thickness, 3),
                    "overlap": round(p.overlap, 2),
                }
                for p in self.pairs
            ],
            "ceilings": [p.to_dict() for p in self.ceilings],
            "planes": [p.to_dict() for p in self.planes],
        }


# --------------------------------------------------------------------------- faces


@dataclass(slots=True)
class Opening:
    """A void in a wall face. Classified in stage 4; stage 2 only carries the hole."""

    along0: float
    along1: float
    sill_z: float
    head_z: float
    kind: str = "unresolved"
    derivation: str = "unresolved"
    # "lintel" (stage-1 bridged gap), "pier" (one anchored by a pier, round 14), "gap"
    # (between walls), "beam" (seen through) or "void" (face grid)
    source: str = "void"

    @property
    def width(self) -> float:
        return self.along1 - self.along0

    @property
    def height(self) -> float:
        return self.head_z - self.sill_z

    def to_dict(self) -> dict[str, Any]:
        return {
            "along": [round(self.along0, 3), round(self.along1, 3)],
            "width": round(self.width, 3),
            "sill_z": round(self.sill_z, 3),
            "head_z": round(self.head_z, 3),
            "kind": self.kind,
            "source": self.source,
            "derivation": self.derivation,
        }


@dataclass(slots=True)
class Face:
    """One measured planar surface, found by 1-D projection in one direction.

    The line is `s = k*r + c` in the face's own (along, across) frame, where
    `s = p . u` and `r = p . v`. The solid only keeps `offset` — the line
    evaluated at the middle of its extent — because a wall is one rectangle and a
    tilt is not representable (design §4.3).
    """

    direction: float
    offset: float
    k: float
    c: float
    r0: float
    r1: float
    length: float
    rms_m: float
    zspread: float
    zmin: float
    zmax: float
    cover: float
    density: float
    normal_dot: float
    points: int
    openings: list[Opening] = field(default_factory=list)
    # +1: the scanner saw this face from the +u side, -1 from the -u side, 0 unknown
    facing: int = 0
    # how close the face's wall columns reach the local ceiling (m below it)
    top_gap: float = 0.0
    partial_height: bool = False
    # lintel-bridged gaps inside the run: (r0, r1) pairs, opening candidates
    bridged: list[tuple[float, float]] = field(default_factory=list)
    # the bridged gaps whose run anchor at one end or both is a pier, not a wall
    # column (round 14): openings read there are tagged source "pier"
    pier_bridged: list[tuple[float, float]] = field(default_factory=list)

    def offset_at(self, r: float) -> float:
        return self.k * r + self.c

    def to_dict(self) -> dict[str, Any]:
        return {
            "dir": round(self.direction, 3),
            "offset": round(self.offset, 4),
            "facing": self.facing,
            "top_gap": round(self.top_gap, 3),
            "partial_height": self.partial_height,
            "bridged": [[round(a, 3), round(b, 3)] for a, b in self.bridged],
            "r0": round(self.r0, 3),
            "r1": round(self.r1, 3),
            "length": round(self.length, 3),
            "rms_mm": round(self.rms_m * 1000, 2),
            "zspread": round(self.zspread, 3),
            "zmin": round(self.zmin, 3),
            "zmax": round(self.zmax, 3),
            "cover": round(self.cover, 3),
            "density": round(self.density),
            "normal_dot": round(self.normal_dot, 3),
            "points": self.points,
            "openings": [o.to_dict() for o in self.openings],
        }


# --------------------------------------------------------------------------- walls


@dataclass(slots=True)
class Join:
    """How one end of a wall was placed against a perpendicular wall."""

    other: str
    face_offset: float
    delta: float  # new end minus the measured end, along the wall
    new_end: float
    trimmed: float = 0.0  # metres shortened; negative means the wall was extended
    partner_covers: bool = True  # the partner's *solid* spans the crossing
    # closed across a gap no scan point covers (design §7.3: a wall can be measured
    # and still inferred at its ends); the extension length is `-trimmed`
    inferred: bool = False

    @property
    def overrun(self) -> float:
        """Measured metres that had to be cut away at this end.

        Deliberately the *solid's* trim, not the longest face's: a paired wall's
        solid spans only where both faces exist, while one of those faces can
        belong to a plane that runs metres further as a different wall (the
        sample's W05 hangs on a 7 m plane but is 1.34 m long). Measuring against
        the longest face reported a 5.6 m "overrun" on a wall that had not moved.

        Extensions carry no overrun — nothing was removed, and the extension is
        bounded by the perpendicular wall's near face and by `join_max_gap`.
        """
        return max(0.0, self.trimmed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "other": self.other,
            "face_offset": round(self.face_offset, 4),
            "delta": round(self.delta, 4),
            "new_end": round(self.new_end, 4),
            "trimmed": round(self.trimmed, 4),
            "overrun": round(self.overrun, 4),
            "partner_covers": self.partner_covers,
            "inferred": self.inferred,
        }


@dataclass(slots=True)
class Room:
    """A closed region of floor, bounded by wall faces.

    The polygon is the *inner face* boundary, so its area is the floor area a
    reader expects rather than the centreline area (design §4.4). `closure_gaps`
    records every place the ring only closed because a gap was bridged: a room
    whose boundary relied on a 590 mm chord is a different claim from one whose
    walls touched, and the file has to say which it is.
    """

    id: str
    polygon: list[tuple[float, float]]
    area_m2: float
    perimeter_m: float
    floor_z: float
    ceiling_z: float | None
    ceiling_cover: float = 0.0  # share of the room under the chosen ceiling plane
    ceiling_alt_z: float | None = None  # a second ceiling height over >= 25% of the room
    walls: list[str] = field(default_factory=list)
    closure_gaps: list[dict[str, Any]] = field(default_factory=list)
    bridged_m: float = 0.0
    support: float = 1.0
    derivation: str = "measured"
    # rejected line candidates crossing the room: it may be two rooms (§4.4.1)
    partition_lines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "area_m2": round(self.area_m2, 3),
            "perimeter_m": round(self.perimeter_m, 3),
            "floor_z": round(self.floor_z, 3),
            "ceiling_z": None if self.ceiling_z is None else round(self.ceiling_z, 3),
            "height_m": None if self.ceiling_z is None else round(self.ceiling_z - self.floor_z, 3),
            "ceiling_cover": round(self.ceiling_cover, 2),
            "ceiling_alt_z": None if self.ceiling_alt_z is None else round(self.ceiling_alt_z, 3),
            "walls": self.walls,
            "support": round(self.support, 3),
            "bridged_m": round(self.bridged_m, 3),
            "bridged_share": (
                round(self.bridged_m / self.perimeter_m, 3) if self.perimeter_m else 0.0
            ),
            "closure_gaps": self.closure_gaps,
            "derivation": self.derivation,
            "possible_partition": bool(self.partition_lines),
            "partition_lines": self.partition_lines,
            "polygon": [[round(x, 3), round(y, 3)] for x, y in self.polygon],
        }


# thickness sources that rest on two observed surfaces (stage 2); anything else
# (assumed-*, paired-continuation, unknown) is not a measurement
MEASURED_THICKNESS = ("measured", "bounded-by-surface-behind", "layered-same-side")
EXPORT_THICKNESS_FALLBACK = 0.1


@dataclass(frozen=True, slots=True)
class WallExport:
    """A wall as the writers see it, in model plan coordinates (metres)."""

    line_a: np.ndarray  # stored reference line: measured face, or the axis
    line_b: np.ndarray
    axis_a: np.ndarray  # centre of the body, for writers that extrude about it
    axis_b: np.ndarray
    body: np.ndarray | None  # unit plan direction of the body from the line; None = centred
    thickness: float
    thickness_note: str
    line: str
    height: float  # level floor to wall top
    base_offset: float  # wall base above the level floor (0 when it stands on it)


@dataclass(slots=True)
class Wall:
    """A wall solid: one rectangle, `axis + extent + thickness + z range`.

    For a paired wall `offset` is the axis (midway between the two measured faces).
    For a single-sided wall `offset` is the *measured face* and `body_side` says
    which way the assumed thickness extrudes, so the measured face stays exactly
    where the scan put it (design §4.3, and Pascal's `justification` field).
    """

    id: str
    direction: float
    offset: float
    thickness: float | None
    thickness_source: str
    pairing: str  # paired | single-sided | ambiguous (a same-side "layered" pair is
    # paired with thickness_source = "layered-same-side")
    r0: float
    r1: float
    r0_meas: float
    r1_meas: float
    z0: float  # observed vertical extent: evidence, not geometry
    z1: float
    faces: list[Face] = field(default_factory=list)
    body_side: int = 0  # +1 / -1 for a single-sided wall, 0 for a paired one
    derivation: str = "measured"
    # the wall's geometry in z: base on its level's floor, top at the local ceiling
    base_z: float | None = None
    top_z: float | None = None
    top_source: str = ""
    envelope: bool = False
    joins: dict[str, Join] = field(default_factory=dict)
    unjoined: list[str] = field(default_factory=list)
    # ends left open because a lintel shows the gap beyond them is a doorway
    doorway_ends: list[str] = field(default_factory=list)
    # voids in the wall's measured faces, along its r coordinate (stage 4)
    openings: list[Opening] = field(default_factory=list)
    # doorways between this wall and a collinear one that the wall was extended
    # across (round 9), along its r coordinate; stage 4 makes each an opening
    door_gaps: list[tuple[float, float]] = field(default_factory=list)
    # the same for windows: a gap with wall below its sill and above its head (round 13)
    window_gaps: list[tuple[float, float]] = field(default_factory=list)

    # -- frame -------------------------------------------------------------
    @property
    def unit(self) -> np.ndarray:
        t = math.radians(self.direction)
        return np.array([math.cos(t), math.sin(t)])

    @property
    def perp(self) -> np.ndarray:
        t = math.radians(self.direction)
        return np.array([-math.sin(t), math.cos(t)])

    @property
    def length(self) -> float:
        return self.r1 - self.r0

    # -- geometry ----------------------------------------------------------
    def axis_offset(self) -> float:
        """Perpendicular coordinate of the wall's centre plane."""
        if self.pairing == "paired":
            return self.offset
        t = self.thickness or 0.0
        return self.offset + self.body_side * t / 2.0

    def plane_offsets(self) -> tuple[float, float]:
        """Perpendicular coordinates of the two physical faces, low then high."""
        t = self.thickness or 0.0
        if self.pairing == "paired":
            return self.offset - t / 2.0, self.offset + t / 2.0
        face = self.offset
        other = face + self.body_side * t
        return (face, other) if face <= other else (other, face)

    def face_extent(self) -> tuple[float, float]:
        """Where the measured faces actually run.

        For a paired wall this is wider than `r0_meas`/`r1_meas`, which are the
        *overlap* of the two faces — the stretch where the thickness is proven.
        At a corner one face usually runs past the other, so joining and the
        overrun measurement have to use the faces, not the overlap.
        """
        if not self.faces:
            return self.r0_meas, self.r1_meas
        return min(f.r0 for f in self.faces), max(f.r1 for f in self.faces)

    def endpoints(self) -> tuple[np.ndarray, np.ndarray]:
        u, v = self.unit, self.perp
        a = self.axis_offset() * u + self.r0 * v
        b = self.axis_offset() * u + self.r1 * v
        return a, b

    def thickness_measured(self) -> bool:
        """True only when the thickness comes from two observed surfaces."""
        return self.thickness_source.startswith(MEASURED_THICKNESS)

    def export_frame(self, floor_z: float) -> "WallExport":
        """The one description of this wall every writer consumes (design §4.8),
        so the IFC and Pascal outputs cannot place it differently.

        The reference line is the measured face of a single-sided wall, else the
        axis; `body` is the plan direction the thickness extrudes from that line
        (None: centred on it). Height runs from the level floor, because neither
        output has a per-wall base offset; a wall whose base is not the floor says
        so in `base_offset`.
        """
        u, v = self.unit, self.perp
        note = ""
        t = self.thickness
        if not t or t <= 0:
            t, note = EXPORT_THICKNESS_FALLBACK, (
                f"assumed {EXPORT_THICKNESS_FALLBACK} m at export: the model has no thickness"
            )
        if self.pairing == "paired":
            line, body, kind = self.offset, None, "centreline"
        elif self.body_side:
            line, body, kind = self.offset, self.body_side * u, "measured face"
        else:
            line, body, kind = self.offset, None, "measured face, body centred"
        top = self.top_z if self.top_z is not None else self.z1
        base = self.base_z if self.base_z is not None else floor_z
        axis = line + (0.0 if body is None else self.body_side * t / 2.0)
        return WallExport(
            line_a=line * u + self.r0 * v, line_b=line * u + self.r1 * v,
            axis_a=axis * u + self.r0 * v, axis_b=axis * u + self.r1 * v,
            body=body, thickness=float(t), thickness_note=note, line=kind,
            height=float(top - floor_z), base_offset=float(base - floor_z),
        )

    def corner(self, end: str) -> np.ndarray:
        a, b = self.endpoints()
        return a if end == "r0" else b

    def to_dict(self) -> dict[str, Any]:
        ax, bx = self.endpoints()
        return {
            "id": self.id,
            "dir": round(self.direction, 3),
            "axis_offset": round(self.axis_offset(), 4),
            "thickness": None if self.thickness is None else round(self.thickness, 4),
            "thickness_source": self.thickness_source,
            "pairing": self.pairing,
            "derivation": self.derivation,
            "extent": [round(self.r0, 4), round(self.r1, 4)],
            "measured_extent": [round(self.r0_meas, 4), round(self.r1_meas, 4)],
            "length": round(self.length, 3),
            "z": [round(self.z0, 3), round(self.z1, 3)],
            "base_z": None if self.base_z is None else round(self.base_z, 4),
            "top_z": None if self.top_z is None else round(self.top_z, 4),
            "top_source": self.top_source,
            "envelope": self.envelope,
            "body_side": self.body_side,
            "endpoints": [[round(float(ax[0]), 4), round(float(ax[1]), 4)],
                          [round(float(bx[0]), 4), round(float(bx[1]), 4)]],
            "faces": [round(f.offset, 4) for f in self.faces],
            "openings": [o.to_dict() for o in self.openings],
            "joins": {k: j.to_dict() for k, j in self.joins.items()},
            "unjoined": self.unjoined,
            "doorway_ends": sorted(set(self.doorway_ends)),
        }


# --------------------------------------------------------------------------- state


@dataclass(slots=True)
class Model:
    """What stages hand to each other. Every field is optional until its stage ran."""

    cloud: Cloud | None = None
    levels: LevelSet | None = None
    faces: list[Face] = field(default_factory=list)
    walls: list[Wall] = field(default_factory=list)
    rooms: list[Room] = field(default_factory=list)
    direction: list[float] = field(default_factory=list)
    # line candidates that did not become faces, with the reason: what is absent
    # is reported, not silent (design §4.2 step 5, review B3)
    rejected_faces: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    timings: dict[str, float] = field(default_factory=dict)
    # further storeys of the same scan, each a full model of its own (round 5)
    storeys: list["Model"] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        paired = [w for w in self.walls if w.pairing == "paired"]
        single = [w for w in self.walls if w.pairing != "paired"]
        return {
            "points": 0 if self.cloud is None else len(self.cloud),
            "directions": self.direction,
            "levels": None if self.levels is None else self.levels.to_dict(),
            "faces": len(self.faces),
            "face_run_m": round(sum(f.length for f in self.faces), 2),
            "walls": len(self.walls),
            "paired": len(paired),
            "single_sided": len(single),
            "wall_run_m": round(sum(w.length for w in self.walls), 2),
            "unjoined_ends": sum(len(w.unjoined) for w in self.walls),
            "station": None if self.cloud is None or self.cloud.station is None
            else [round(float(v), 3) for v in self.cloud.station],
            "station_source": None if self.cloud is None else self.cloud.station_source,
            "station_info": None if self.cloud is None else self.cloud.station_info,
            "rejected_faces": len(self.rejected_faces),
            "recall_by_direction": self.meta.get("recall_by_direction"),
            "rooms": len(self.rooms),
            "room_area_m2": round(sum(r.area_m2 for r in self.rooms), 2),
            "floor_seen_m2": self.meta.get("floor_seen_m2"),
            "floor_unclosed_m2": self.meta.get("floor_unclosed_m2"),
            "timings_s": {k: round(v, 2) for k, v in self.timings.items()},
            "storeys": [round(float(s.levels.floor_z), 3) for s in self.storeys if s.levels is not None],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "meta": self.meta,
            "summary": self.summary(),
            "faces": [f.to_dict() for f in self.faces],
            "rejected_faces": self.rejected_faces,
            "walls": [w.to_dict() for w in self.walls],
            "rooms": [r.to_dict() for r in self.rooms],
            # further storeys, each in this same shape (round 5)
            "storeys": [s.to_dict() for s in self.storeys],
        }
