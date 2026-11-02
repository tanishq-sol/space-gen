"""Planar geometry: line intersection, perpendicular tests, corner joining.

The corner-joining rule is design §4.3: a wall's *centreline* is intersected with
the *near face* of the perpendicular wall it meets, cut square, not mitred. With
`min_angle_deg` (accuracy round 3) the same rule joins walls meeting at any angle
of at least that much — radial plans; the cut stays square to the wall. The
distinction between "centreline" and "near face" is worth t/2 — 142 mm on the
285 mm wall in the sample scan, three times the 50 mm overrun budget.
"""

from __future__ import annotations

import math

import numpy as np

from .model import Join, Wall


def unit(direction_deg: float) -> np.ndarray:
    t = math.radians(direction_deg)
    return np.array([math.cos(t), math.sin(t)])


def perp(direction_deg: float) -> np.ndarray:
    t = math.radians(direction_deg)
    return np.array([-math.sin(t), math.cos(t)])


def line_intersection(n1: np.ndarray, c1: float, n2: np.ndarray, c2: float) -> np.ndarray | None:
    """Solve `p . n1 = c1`, `p . n2 = c2`. None when the lines are parallel."""
    det = n1[0] * n2[1] - n1[1] * n2[0]
    if abs(det) < 1e-9:
        return None
    x = (c1 * n2[1] - c2 * n1[1]) / det
    y = (n1[0] * c2 - n2[0] * c1) / det
    return np.array([x, y])


def angle_from_perpendicular(d1: float, d2: float) -> float:
    """Degrees by which the angle between two directions departs from 90."""
    return abs(((d2 - d1) % 180.0) - 90.0)


def is_perpendicular(d1: float, d2: float, tol_deg: float = 5.0) -> bool:
    return angle_from_perpendicular(d1, d2) <= tol_deg


def crossing_angle(d1: float, d2: float) -> float:
    """The acute angle (0-90 degrees) at which two wall directions cross."""
    a = (d2 - d1) % 180.0
    return min(a, 180.0 - a)


def can_meet(d1: float, d2: float, perp_tol_deg: float, min_angle_deg: float | None) -> bool:
    """Two walls can form a corner: perpendicular within `perp_tol_deg`, or, when
    `min_angle_deg` is set (buildings with oblique wall directions), crossing at
    `min_angle_deg` or more. Near-parallel walls never meet."""
    if is_perpendicular(d1, d2, perp_tol_deg):
        return True
    return min_angle_deg is not None and crossing_angle(d1, d2) >= min_angle_deg


def cell_overlap(a: np.ndarray, b: np.ndarray) -> float:
    """Share of the smaller plane's footprint that both planes cover.

    Encodes (i, j) grid cells as one int64 so the intersection is a sort, not a
    set of Python tuples.
    """
    if len(a) == 0 or len(b) == 0:
        return 0.0

    def keys(c: np.ndarray) -> np.ndarray:
        return c[:, 0].astype(np.int64) * 1_000_003 + c[:, 1]

    ka, kb = keys(a), keys(b)
    both = np.intersect1d(ka, kb, assume_unique=False)
    return len(both) / min(len(ka), len(kb))


# --------------------------------------------------------------------- corner join


def near_face(wall: Wall, end: str, other: Wall) -> float:
    """The face of `other` that `wall` approaches from.

    Not the face nearest the end: if a wall overruns a thin partition, the nearest
    face is the *far* side of that partition, and trimming to it leaves the wall
    solid lying inside the partition. The face that matters is the one the wall
    comes from, which the outward direction at that end decides.
    """
    outward = wall.perp if end == "r1" else -wall.perp
    approach = float(outward @ other.unit)
    low, high = other.plane_offsets()
    return low if approach > 0 else high


def _candidate_joins(
    wall: Wall,
    end: str,
    walls: list[Wall],
    max_gap: float,
    perp_tol_deg: float,
    extent_slack: float,
    covers_slack: float = 0.10,
    min_angle_deg: float | None = None,
) -> list[tuple[Wall, float, float, float, bool, float]]:
    """Every legal (other, face offset, along-coordinate, distance, covers, miss).

    Candidates are the near faces of perpendicular walls whose crossing with this
    wall's centreline lies within `max_gap` of the measured end and within the
    other wall's own face extent ± `extent_slack`. `covers` always uses the
    measured slack, whatever slack admitted the candidate; `miss` is how far the
    crossing lies beyond the partner's face extent (0 when on it).
    """
    u = wall.unit
    axis = wall.axis_offset()
    end_r = wall.r0_meas if end == "r0" else wall.r1_meas
    mid = (wall.r0_meas + wall.r1_meas) / 2.0
    out = []

    for other in walls:
        if other is wall:
            continue
        if not can_meet(wall.direction, other.direction, perp_tol_deg, min_angle_deg):
            continue
        face = near_face(wall, end, other)
        p = line_intersection(u, axis, other.unit, face)
        if p is None:
            continue
        r = float(p @ wall.perp)
        gap = abs(r - end_r)
        if gap > max_gap:
            continue
        # must stay on this wall's side of the middle, so a wall crossing the
        # middle is never mistaken for the wall an end meets
        if end == "r0" and not (r <= mid):
            continue
        if end == "r1" and not (r >= mid):
            continue
        r_other = float(p @ other.perp)
        lo, hi = other.face_extent()
        if not (lo - extent_slack <= r_other <= hi + extent_slack):
            continue
        covers = other.r0_meas - covers_slack <= r_other <= other.r1_meas + covers_slack
        miss = max(lo - r_other, r_other - hi, 0.0)
        out.append((other, face, r, gap, covers, miss))
    return out


def join_wall_ends(
    walls: list[Wall],
    max_gap: float = 0.30,
    perp_tol_deg: float = 5.0,
    extent_slack: float = 0.10,
    min_length: float = 0.05,
    inferred_reach: float = 0.0,
    is_doorway=None,
    min_angle_deg: float | None = None,
) -> None:
    """Trim (or, if the wall stopped short, extend) every end to the wall it meets.

    The partner tests use measured extents, so a previously trimmed wall is still
    eligible and the processing order cannot change a result.

    An end the measured rule cannot place may still close a corner where *both*
    walls stop short of it — a desk shadow at the corner. It is extended (never
    trimmed beyond `max_gap`) to a perpendicular wall when the extension plus the
    partner's own shortfall together stay within `inferred_reach`, and the join is
    flagged `inferred`. It is **refused** where `is_doorway(wall, end, r_from,
    r_to)` finds a lintel over the gap: that gap is a door, and walling it up is
    the error the converter exists to avoid. Anything else keeps its measured
    extent and is recorded as `unjoined`, which is a number the report can count.

    Walls are processed in id order. Face positions never move and every join is
    computed from measured extents, so the order cannot change a result.
    """
    for wall in walls:
        for end in ("r0", "r1"):
            end_r = wall.r0_meas if end == "r0" else wall.r1_meas
            cands = _candidate_joins(wall, end, walls, max_gap, perp_tol_deg, extent_slack, extent_slack,
                                     min_angle_deg)
            inferred = False
            if not cands and inferred_reach > 0.0:
                ahead = 1.0 if end == "r1" else -1.0
                cands = []
                for c in _candidate_joins(
                    wall, end, walls, inferred_reach, perp_tol_deg, inferred_reach, extent_slack,
                    min_angle_deg,
                ):
                    extension = max((c[2] - end_r) * ahead, 0.0)
                    if (c[2] - end_r) * ahead < -max_gap:
                        continue
                    if extension + c[5] > inferred_reach:
                        continue
                    if is_doorway is not None and extension > 0 and is_doorway(
                        wall, end, end_r, c[2]
                    ):
                        wall.doorway_ends.append(end)
                        continue
                    cands.append(c)
                inferred = bool(cands)
            if not cands:
                wall.unjoined.append(end)
                continue
            # an oblique partner only when no perpendicular one is in reach (review R3-2A)
            square = [c for c in cands if is_perpendicular(wall.direction, c[0].direction, perp_tol_deg)]
            cands = square or cands

            # nearest face wins; on a tie prefer a wall whose solid is actually
            # there over a face that merely continues past its own wall, then the
            # face the wall approached from
            def rank(c) -> tuple[float, int, int]:
                _, _, r, gap, covers, _ = c
                approached = r <= end_r if end == "r1" else r >= end_r
                return (round(gap, 6), 0 if covers else 1, 0 if approached else 1)

            other, face, r, _, covers, _ = min(cands, key=rank)
            # +1 at r1, -1 at r0: moving either end inward shortens the wall
            sign = 1.0 if end == "r1" else -1.0
            wall.joins[end] = Join(
                other=other.id,
                face_offset=float(face),
                delta=float(r - end_r),
                new_end=float(r),
                trimmed=float((end_r - r) * sign),
                partner_covers=covers,
                inferred=inferred,
            )
            if end == "r0":
                wall.r0 = r
            else:
                wall.r1 = r

        # an end that joined after all is not a doorway end
        wall.doorway_ends = sorted({e for e in wall.doorway_ends if e not in wall.joins})
        if wall.r1 - wall.r0 < min_length:
            # a join that eats the whole wall is not a join; keep what was measured
            wall.r0, wall.r1 = wall.r0_meas, wall.r1_meas
            wall.joins.clear()
            wall.unjoined = ["r0", "r1"]


def overrun_report(walls: list[Wall]) -> dict[str, float]:
    """Metres each joined end was trimmed back, keyed `wall_id:end`."""
    return {
        f"{w.id}:{end}": j.overrun
        for w in walls
        for end, j in w.joins.items()
        if j.overrun > 0
    }
