"""Stage 2 — wall solids: pair faces across their thickness, then join corners.

Pairing is thinnest-first, one-to-one, with overlap as a *filter*, not as the
objective (design §4.3). The distinction is load-bearing: a wall with a chase or a
glazed screen in front of it offers two legal partners, and an objective that
prefers the larger overlap — or the larger number of pairs — pairs surfaces across
the gap between them, producing a wall whose thickness was selected rather than
measured.

Facing decides what a pair can be. Two faces looking *away* from each other are
the two sides of one wall (`paired`, thickness measured). Two faces looking the
*same* way within `layered_max` are one wall seen through a transparent or thin
layer (`layered`, thickness inferred): a single station cannot see both sides of a
solid wall, so a same-side pair is either glazing or a lining. Anything else is two
walls.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from ..config import Config
from ..geometry import join_wall_ends
from ..model import Cloud, Face, LevelSet, Wall
from .s1_faces import CeilingMap, column_classes, storey_band


# ------------------------------------------------------------------------ pairing


def _overlap(a: Face, b: Face) -> float:
    return min(a.r1, b.r1) - max(a.r0, b.r0)


def _at(f: Face, r: float) -> float:
    """The face's offset at along-coordinate `r` (its fitted line)."""
    return float(f.k * r + f.c)


def _pair_kind(lo: Face, hi: Face, cfg: Config) -> str | None:
    """What two parallel faces `lo` (smaller offset) and `hi` can be, by facing.

    Facing +1 means the face was seen from its +u side. The two sides of one wall
    look away from each other: `lo` faces -1 and `hi` faces +1.
    """
    if lo.facing == 0 or hi.facing == 0:
        # facing unknown: the geometric rule alone, and a height mismatch refuses
        return None if lo.partial_height != hi.partial_height else "paired"
    if lo.facing == -1 and hi.facing == 1:
        # Both sides of one wall. Unreachable from a single station — one point
        # cannot be on both sides — so this needs a second station (design §4.3).
        return None if lo.partial_height != hi.partial_height else "paired"
    if lo.facing == hi.facing and hi.offset - lo.offset <= cfg.layered_max:
        # Two surfaces seen from the same side: the scanner saw the far one past
        # the near one (glazing, a lining, a gap). The near face is the room
        # boundary and the wall; the far surface only bounds its thickness. If the
        # near face stops short of the ceiling it is a credenza, screen or pod
        # panel in front of the wall, not a wall layer.
        near = lo if lo.facing == -1 else hi
        return None if near.partial_height else "layered"
    return None


def _medial_blocked(group: list[Face], i: int, j: int, cfg: Config) -> bool:
    """A third face between a pair means the pair spans a chase, not a wall."""
    lo, hi = group[i].offset, group[j].offset
    a0, a1 = max(group[i].r0, group[j].r0), min(group[i].r1, group[j].r1)
    for k, f in enumerate(group):
        if k in (i, j) or not (lo < f.offset < hi):
            continue
        if min(a1, f.r1) - max(a0, f.r0) > cfg.pair_medial_min_overlap:
            return True
    return False


def _pair_group(group: list[Face], direction: float, cfg: Config) -> list[Wall]:
    group = sorted(group, key=lambda f: f.offset)
    n = len(group)
    legal: dict[tuple[int, int], tuple[float, str]] = {}

    for i in range(n):
        for j in range(i + 1, n):
            # Coarse cut on the faces' own offsets (sorted), with room for slope;
            # the real gap is measured where the two faces overlap, because a
            # face's `offset` is its line at its own midpoint and a long face with
            # a slight slope reads far from a short partner (UoM W13/W14: 0.53 m
            # by midpoints, 0.30 m where they overlap).
            if group[j].offset - group[i].offset > cfg.pair_max_thickness + cfg.pair_slope_slack:
                break
            ov = _overlap(group[i], group[j])
            if ov <= 0:
                continue
            rm = (max(group[i].r0, group[j].r0) + min(group[i].r1, group[j].r1)) / 2.0
            gap = (group[j].k * rm + group[j].c) - (group[i].k * rm + group[i].c)
            if not (cfg.pair_min_thickness <= gap <= cfg.pair_max_thickness):
                continue
            short = min(group[i].length, group[j].length)
            # Run ends are quantised and clutter splits runs, so a long common
            # stretch counts even when it is under 55% of the shorter face.
            if not (ov >= cfg.pair_min_overlap * short or ov >= cfg.face_min_length):
                continue
            if _medial_blocked(group, i, j, cfg):
                continue
            kind = _pair_kind(group[i], group[j], cfg)
            if kind is None:
                continue
            legal[(i, j)] = (gap, kind)

    # Thinnest first. A face may take several partners when they meet it along
    # separate stretches: one wall's face seen whole on one side and in pieces on
    # the other (clutter, a doorway) is one wall in pieces, not a choice between
    # partners (UoM: a 13 m face against three collinear pieces was demoted whole).
    # The measured thickness is still the smallest legal separation.
    def span(i: int, j: int) -> tuple[float, float]:
        return max(group[i].r0, group[j].r0), min(group[i].r1, group[j].r1)

    def free(face: int, a: float, b: float) -> bool:
        return all(b <= c0 + cfg.pair_span_slack or a >= c1 - cfg.pair_span_slack
                   for c0, c1 in claimed.get(face, []))

    matched: dict[tuple[int, int], str] = {}
    claimed: dict[int, list[tuple[float, float]]] = {}
    for (i, j), (gap, kind) in sorted(legal.items(), key=lambda kv: kv[1][0]):
        a, b = span(i, j)
        if not (free(i, a, b) and free(j, a, b)):
            continue
        matched[(i, j)] = kind
        claimed.setdefault(i, []).append((a, b))
        claimed.setdefault(j, []).append((a, b))
    taken = set(claimed)

    # A face with two legal partners of near-equal thickness cannot say which is
    # the wall and which is the thing standing in front of it — but only if the
    # other partner is actually still free, competes for the same stretch, and is
    # not a collinear piece of the chosen partner's surface.
    doubtful: set[tuple[int, int]] = set()
    contested: set[int] = set()
    for (i, j) in matched:
        chosen = legal[(i, j)][0]
        a, b = span(i, j)
        for face, other in ((i, j), (j, i)):
            for (x, y), (gap, _) in legal.items():
                if face not in (x, y) or other in (x, y):
                    continue
                k = y if x == face else x
                k0, k1 = max(group[face].r0, group[k].r0), min(group[face].r1, group[k].r1)
                if k1 <= a + cfg.pair_span_slack or k0 >= b - cfg.pair_span_slack:
                    continue  # meets the face elsewhere along it: not a competitor
                if not free(k, k0, k1):
                    continue  # already paired over that stretch
                rk = (max(k0, a) + min(k1, b)) / 2.0
                if abs(_at(group[k], rk) - _at(group[other], rk)) < cfg.pair_ambiguity:
                    continue  # the same surface as the chosen partner
                if abs(gap - chosen) < cfg.pair_ambiguity:
                    # 1B: only this pair is in doubt, not every partner of its faces
                    doubtful.add((i, j))
                    contested.add(k)
    matched = {pr: k for pr, k in matched.items() if pr not in doubtful}
    still = {x for pr in matched for x in pr}
    ambiguous = {x for pr in doubtful for x in pr} | contested
    ambiguous -= still

    walls: list[Wall] = []
    in_pair: set[int] = set()
    for (i, j), kind in sorted(matched.items(), key=lambda kv: -_overlap(group[kv[0][0]], group[kv[0][1]])):
        f, g = group[i], group[j]
        in_pair.update((i, j))
        layered = kind == "layered"
        a, b = span(i, j)
        rm = (a + b) / 2.0
        fa, ga = _at(f, rm), _at(g, rm)
        walls.append(
            Wall(
                id="",
                direction=float(direction),
                # both faces read where they overlap: a long, slightly sloped face
                # is not at its own midpoint offset over a short partner's stretch
                offset=float((fa + ga) / 2),
                thickness=float(abs(ga - fa)),
                thickness_source="bounded-by-surface-behind" if layered else "measured",
                pairing="paired",
                r0=float(a),
                r1=float(b),
                r0_meas=float(a),
                r1_meas=float(b),
                z0=float(min(f.zmin, g.zmin)),
                z1=float(max(f.zmax, g.zmax)),
                faces=[f, g] if f.offset < g.offset else [g, f],
                derivation="inferred" if layered else "measured",
            )
        )
    for i in sorted(range(n), key=lambda k: -group[k].length):
        if i in in_pair:
            continue
        f = group[i]
        walls.append(
            Wall(
                id="",
                direction=float(direction),
                offset=float(f.offset),
                thickness=None,
                thickness_source="unknown",
                pairing="ambiguous" if i in ambiguous else "single-sided",
                r0=float(f.r0),
                r1=float(f.r1),
                r0_meas=float(f.r0),
                r1_meas=float(f.r1),
                z0=float(f.zmin),
                z1=float(f.zmax),
                faces=[f],
            )
        )
    return walls


def pair_faces(faces: list[Face], cfg: Config = Config()) -> list[Wall]:
    walls: list[Wall] = []
    for direction in sorted({f.direction for f in faces}):
        walls.extend(_pair_group([f for f in faces if f.direction == direction], direction, cfg))
    return walls


# -------------------------------------------------------------- single-sided body


def _body_side(face: Face, points: np.ndarray, cfg: Config) -> int:
    """+1 or -1: which side of the measured face the wall body occupies.

    A single-sided wall keeps its measured face exactly where the scan put it and
    extrudes the assumed thickness into the space the scanner could not see
    (design §4.3). Which side that is, is decided by where the points are: in a
    multi-position scan the body side holds the far face and the next room.
    """
    t = np.deg2rad(face.direction)
    u = np.array([np.cos(t), np.sin(t)])
    v = np.array([-np.sin(t), np.cos(t)])
    s = points[:, 0] * u[0] + points[:, 1] * u[1]
    r = points[:, 0] * v[0] + points[:, 1] * v[1]
    d = s - (face.k * r + face.c)
    inside = (
        (r > face.r0 - 0.10)
        & (r < face.r1 + 0.10)
        & (points[:, 2] > face.zmin - 0.20)
        & (points[:, 2] < face.zmax + 0.20)
    )
    plus = int((inside & (d > 0.06) & (d < 0.50)).sum())
    minus = int((inside & (d < -0.06) & (d > -0.50)).sum())
    if plus == minus:
        return 1
    # Measured on the benchmark (accuracy rounds 3 and 6): in a cloud scanned from
    # several positions, what lies 6-50 cm behind a wall is its far face and the
    # next room, while a room side is often empty above 0.3 m — the side with
    # *more* returns is the body. The old rule (body on the emptier side) was wrong
    # 20 of 28 and 26 of 29 times on reference-matched faces. A single known
    # station never reaches this rule (facing decides).
    return 1 if plus > minus else -1


def _side_evidence(face: Face, points: np.ndarray, floor_pts: np.ndarray, cfg: Config) -> dict:
    """What lies either side of a face, measured from the cloud with no station.

    floor_plus/minus: share of 0.2 m columns along the face with floor returns
    0.15–0.6 m off the face on that side — the room side has floor, the outside of
    an exterior wall has none. behind_plus/minus: distance to the first dense
    layer of points parallel to the face within 0.04–0.45 m on that side (the
    wall's far face, when the next room was scanned), or None.
    """
    t = np.deg2rad(face.direction)
    u = np.array([np.cos(t), np.sin(t)])
    v = np.array([-np.sin(t), np.cos(t)])
    out: dict = {}
    ncol = max(int((face.r1 - face.r0) / 0.2), 1)

    def frame(p):
        r = p[:, 0] * v[0] + p[:, 1] * v[1]
        d = p[:, 0] * u[0] + p[:, 1] * u[1] - (face.k * r + face.c)
        return r, d

    if len(floor_pts):
        r, d = frame(floor_pts)
        on = (r > face.r0) & (r < face.r1)
        col = np.clip(((r - face.r0) / 0.2).astype(int), 0, ncol - 1)
        for sign, key in ((1, "floor_plus"), (-1, "floor_minus")):
            m = on & (sign * d > 0.15) & (sign * d < 0.60)
            out[key] = len(np.unique(col[m])) / ncol
    r, d = frame(points)
    near = (r > face.r0) & (r < face.r1) & (points[:, 2] > face.zmin) & (points[:, 2] < face.zmax) & (np.abs(d) < 0.47)
    d_all = d
    d = d[near]
    own = int((np.abs(d) < 0.02).sum())
    for sign, key in ((1, "behind_plus"), (-1, "behind_minus")):
        h, edges = np.histogram(sign * d, bins=np.arange(0.04, 0.4701, 0.02))
        hit = np.flatnonzero(h >= max(cfg.behind_layer_min_points, cfg.behind_layer_share * own))
        out[key] = float((edges[hit[0]] + edges[hit[0] + 1]) / 2) if len(hit) else None
        out[key + "_cover"] = 0.0
        if out[key] is not None:
            # a wall's far face runs along the whole face; a cabinet or radiator does not
            lay = near & (np.abs(sign * d_all - out[key]) < 0.03)
            out[key + "_cover"] = len(np.unique(np.clip(((r[lay] - face.r0) / 0.2).astype(int), 0, ncol - 1))) / ncol
    return out


def _far_layer(ev: dict, side: int, fp: float, fm: float, cfg: Config) -> bool:
    """Is there a far-face layer on `side`: found, running along most of the face
    (`behind_layer_cover`), and not on the side with more floor (that is a room,
    and the layer is furniture in it)?"""
    key = "behind_plus" if side > 0 else "behind_minus"
    if ev.get(key) is None or ev.get(key + "_cover", 0.0) < cfg.behind_layer_cover:
        return False
    here, there = (fp, fm) if side > 0 else (fm, fp)
    return here < there or here <= cfg.side_floor_absent


def _is_envelope(w: Wall, walls: list[Wall], cfg: Config) -> bool:
    """A single-sided wall is envelope when nothing lies beyond it on its body side:
    no other face in its direction, overlapping its run, further out."""
    f = w.faces[0]
    if f.partial_height:
        # a wall the scan loses short of the ceiling is a screen or pod wall as
        # often as a facade; it is not given the envelope's thickness or top
        return False
    for o in walls:
        if o is w or o.direction != w.direction:
            continue
        for g in o.faces:
            if _overlap(f, g) < cfg.envelope_min_overlap:
                continue
            if (g.offset - f.offset) * w.body_side > 0:
                return False
    return True


def assign_single_sided(walls: list[Wall], cloud: Cloud, levels: LevelSet, cfg: Config = Config()) -> None:
    """Give every single-sided wall a body side and an assumed thickness, and say
    where both came from (design §4.3, §8.12).

    Body side: the wall extrudes away from the side the scanner saw it from
    (`Face.facing`). Only when the station is unknown does it fall back to counting
    points either side, and the source says so.

    Thickness: envelope walls (nothing beyond them) take the building's measured pair
    median when `assumed_min_samples` pairs back it, else `envelope_default_thickness`
    — pairs only ever form on partitions, so a partition median says nothing about
    an exterior wall. Interior walls take the per-direction median when at least
    `assumed_min_samples` pairs back it, else the global median, else the default.
    """
    by_direction: dict[float, list[float]] = {}
    counted: set[int] = set()
    for w in walls:
        if w.pairing == "paired" and w.thickness_source == "measured":
            # pieces of one wall share a face: that wall is one sample, not several
            if any(id(f) in counted for f in w.faces):
                continue
            counted.update(id(f) for f in w.faces)
            by_direction.setdefault(w.direction, []).append(w.thickness)
    overall = [t for ts in by_direction.values() for t in ts]
    n_min = cfg.assumed_min_samples

    top = max((c.z_fit for c in levels.ceilings), default=levels.floor_z + cfg.fallback_ceiling_height)
    inside = (cloud.points[:, 2] > levels.floor_z - 0.30) & (cloud.points[:, 2] < top + 0.30)
    points = cloud.points[inside]
    if len(points) > cfg.side_evidence_max_points:  # evidence is a count: a fixed subsample keeps it cheap
        points = points[:: int(np.ceil(len(points) / cfg.side_evidence_max_points))]
    floor_pts = points[np.abs(points[:, 2] - levels.floor_z) < cfg.side_floor_tol]
    # One scanner never sees behind a wall: a layer behind a face is then something
    # seen through a gap, not the wall's far face. Several viewpoints (stations, a
    # trajectory) or a merged cloud with none recorded can see both sides.
    known = cloud.station_rows()
    one_viewpoint = known is not None and int(np.isfinite(known[0]).all(1).sum()) == 1

    for w in walls:
        if w.thickness is not None:
            continue
        f = w.faces[0]
        ev = _side_evidence(f, points, floor_pts, cfg)
        fp, fm = ev.get("floor_plus", 0.0), ev.get("floor_minus", 0.0)
        if f.facing:
            w.body_side = -f.facing
            side_source = "facing"
        elif fp <= cfg.side_floor_absent and fm >= cfg.side_floor_present:
            w.body_side, side_source = 1, "floor support (room on the - side)"
        elif fm <= cfg.side_floor_absent and fp >= cfg.side_floor_present:
            w.body_side, side_source = -1, "floor support (room on the + side)"
        elif (not one_viewpoint and not f.partial_height
              and (layer_plus := _far_layer(ev, 1, fp, fm, cfg)) != _far_layer(ev, -1, fp, fm, cfg)):
            # the wall's far face, scanned from the next room, is a dense parallel
            # layer within a wall thickness on the body side only (accuracy round 3:
            # the point count below chose the wrong side 34 times in 41 on Grainger
            # Museum, because that layer *adds* points on the body side)
            w.body_side = 1 if layer_plus else -1
            side_source = "far-face layer"
        else:
            w.body_side = _body_side(f, points, cfg)
            side_source = ("point-count (station unknown, floor on both sides)"
                           if min(fp, fm) > cfg.side_floor_absent else "point-count (station unknown)")
        body_floor = fp if w.body_side > 0 else fm
        # Envelope needs nothing beyond it *and* no floor beyond it: a partition
        # whose next room was scanned is not a facade (TUB1 W04).
        w.envelope = _is_envelope(w, walls, cfg) and body_floor <= cfg.side_floor_absent
        behind = ev["behind_plus"] if w.body_side > 0 else ev["behind_minus"]
        if not _far_layer(ev, w.body_side, fp, fm, cfg):
            behind = None  # a short or floor-side layer is furniture, not the far face
        sample = by_direction.get(w.direction, [])
        if behind is not None and not f.partial_height and not one_viewpoint:
            # a dense parallel layer just behind the face: the wall's far face
            w.thickness = behind
            w.thickness_source = f"bounded-by-points-behind({behind:.2f} m)"
        elif w.envelope and len(overall) >= n_min:
            w.thickness = float(np.median(overall))
            w.thickness_source = f"assumed-envelope-measured-median(n={len(overall)})"
        elif w.envelope:
            w.thickness = cfg.envelope_default_thickness
            w.thickness_source = "assumed-envelope-default"
        elif len(sample) >= n_min:
            w.thickness = float(np.median(sample))
            w.thickness_source = f"assumed-paired-median(n={len(sample)}, direction={w.direction:.2f})"
        elif len(overall) >= n_min:
            w.thickness = float(np.median(overall))
            w.thickness_source = f"assumed-global-median(n={len(overall)})"
        else:
            w.thickness = cfg.assumed_default_thickness
            w.thickness_source = f"assumed-default(paired n={len(overall)} < {n_min})"
        w.thickness_source += f"; body side by {side_source}"
        w.derivation = "partial"


def assign_heights(walls: list[Wall], levels: LevelSet, ceilings: CeilingMap, cfg: Config) -> None:
    """Base on the level's floor, top at the ceiling over the wall's room side.

    The observed z range (z0, z1) stays as evidence; it starts at the storey band
    and stops wherever the scan stopped, so it is not the wall's height.
    """
    for w in walls:
        w.base_z = levels.floor_z
        f = w.faces[0]
        side = f.facing if f.facing else (-w.body_side if w.body_side else 1)
        n = max(int((w.r1 - w.r0) / cfg.run_col), 1)
        rs = w.r0 + (np.arange(n) + 0.5) * (w.r1 - w.r0) / n
        off = (w.plane_offsets()[1] if side > 0 else w.plane_offsets()[0]) + side * cfg.ceiling_probe
        xy = off * w.unit[None, :] + rs[:, None] * w.perp[None, :]
        # A wall stops short of the ceiling only if its room-side face does: for a
        # bounded (same-side) pair that is the near face, for a two-sided pair both.
        if w.thickness_source.startswith("bounded"):
            partial = False  # the near face is full-height, or it would not pair
        else:
            partial = all(fc.partial_height for fc in w.faces)
        if partial:
            # where the scan shows it stop; nothing above that is supported
            w.top_z = float(w.z1)
            w.top_source = "observed top (partial-height face)"
            continue
        above = np.full(n, w.z1 - cfg.ceiling_tolerance)
        w.top_z = float(np.median(ceilings.at(xy, above=above)))
        w.top_source = f"local ceiling (median of {n}); fallback {ceilings.source}"


def doorway_check(cloud: Cloud, levels: LevelSet, ceilings: CeilingMap, cfg: Config):
    """Is the gap between a wall's end and the crossing it would extend to a door?

    Looks along the wall's own measured face, beyond its end: if most columns of
    the gap carry a lintel and the furniture-free band is empty, the gap is a
    doorway and must not be walled up.
    """
    band, normals = storey_band(cloud, levels, cfg, top=ceilings.highest)
    tree = None  # built on first use: only the points near a gap are projected (review R6-H2)

    def check(wall: Wall, end: str, r_from: float, r_to: float) -> bool:
        a, b = sorted((r_from, r_to))
        if b - a < cfg.run_col:
            return False
        f = wall.faces[0]
        u, v = wall.unit, wall.perp
        nonlocal tree
        if tree is None:
            from scipy.spatial import cKDTree

            tree = cKDTree(band[:, :2])
        mid = f.k * (a + b) / 2 + f.c
        centre = mid * u + (a + b) / 2 * v
        near = np.asarray(tree.query_ball_point(centre, (b - a) / 2 + 0.2), dtype=np.int64)
        if not len(near):
            return False
        pts = band[near]
        s, r = pts[:, :2] @ u, pts[:, :2] @ v
        aligned = np.abs(normals[near, :2] @ u) >= cfg.face_min_normal_dot
        m = (np.abs(s - (f.k * r + f.c)) < cfg.face_trim) & (r >= a) & (r < b) & aligned
        if not m.any():
            # nothing scanned in the gap: an occlusion shadow and an unscanned
            # door look the same; recorded as a limitation (design §8)
            return False
        ncol = max(int(np.ceil((b - a) / cfg.run_col)), 1)
        rc = a + (np.arange(ncol) + 0.5) * (b - a) / ncol
        # the same rule as the faces: the wall's own ceiling is at or above its top,
        # read on the side it was seen from (both sides, lower wins, when unknown)
        above = np.full(ncol, wall.z1 - cfg.ceiling_tolerance)
        sides = [f.facing] if f.facing else [1, -1]
        ceil = np.min(
            [ceilings.at((f.offset + sd * cfg.ceiling_probe) * u[None, :] + rc[:, None] * v[None, :], above=above)
             for sd in sides],
            axis=0,
        )
        col = np.clip(((r[m] - a) / ((b - a) / ncol)).astype(int), 0, ncol - 1)
        cls = column_classes(col, pts[m, 2], ncol, levels.floor_z, ceil, cfg)
        return bool(cls["lintel"].mean() >= cfg.run_lintel_share)

    return check


# ----------------------------------------------------------- residual face extent


def residual_walls(walls: list[Wall], cfg: Config) -> list[Wall]:
    """Stretches of a paired face that the pair does not reach.

    A face can be longer than the wall it proves: it meets a partner over part of
    its run, and the back of the rest was never scanned. If the excess is dropped
    it is not "unpaired", it is *invisible* — no solid stands where the wall does,
    corners terminate on a plane no wall occupies, and stage 3 cannot close a room
    along it. (No residual reaches 1.2 m on the current sample; the rule is pinned
    by tests/test_pairing.py.)

    So a paired face yields two solids: the paired one over the overlap, and a
    single-sided one over each surplus stretch. The surplus is the same
    single-sided case §4.3 already defines — one measured face, thickness
    assumed, `derivation = partial` — so it needs no new category.
    """
    # every paired wall a face belongs to, so a face paired along several
    # stretches yields its surplus once, not once per pair
    uses: dict[int, list[Wall]] = {}
    face_of: dict[int, object] = {}
    for w in walls:
        if len(w.faces) != 2:
            continue
        for f in w.faces:
            uses.setdefault(id(f), []).append(w)
            face_of[id(f)] = f

    out: list[Wall] = []
    for key, ws in uses.items():
        f = face_of[key]
        # stretches no pair covers. A lintel-bridged doorway stays inside the wall
        # (doors are openings cut later, design §4.7), as it does in any wall run;
        # excluding it split surpluses below 1.2 m and lost wall (review R3-1F, measured)
        covered = sorted((w.r0_meas, w.r1_meas) for w in ws)
        gaps, cur = [], f.r0
        for c0, c1 in covered:
            if c0 > cur:
                gaps.append((cur, c0))
            cur = max(cur, c1)
        if f.r1 > cur:
            gaps.append((cur, f.r1))
        for a, b in gaps:
            if b - a < cfg.face_min_length:
                continue
            # the stretch continues the nearest pair along the face, and inherits its kind
            w = min(ws, key=lambda x: min(abs(x.r0_meas - b), abs(x.r1_meas - a)))
            piece = replace(f, r0=float(a), r1=float(b), length=float(b - a),
                            offset=float(f.k * (a + b) / 2.0 + f.c),
                            points=int(round(f.points * (b - a) / max(f.length, 1e-9))),
                            bridged=[x for x in f.bridged if a <= x[0] and x[1] <= b],
                            pier_bridged=[x for x in f.pier_bridged if a <= x[0] and x[1] <= b])
            if w.thickness_source.startswith("bounded"):
                # Only the near face is a wall. Its surplus is an ordinary single-sided
                # wall (thickness assumed later); the far surface's surplus is nothing.
                lo_f, hi_f = sorted(w.faces, key=lambda x: x.offset)
                if f is not (lo_f if lo_f.facing == -1 else hi_f):
                    continue
                out.append(Wall(id="", direction=w.direction, offset=piece.offset, thickness=None,
                                thickness_source="unknown", pairing="single-sided",
                                r0=float(a), r1=float(b), r0_meas=float(a), r1_meas=float(b),
                                z0=float(f.zmin), z1=float(f.zmax), faces=[piece]))
                continue
            lo, hi = w.plane_offsets()
            side = 1 if abs(f.offset - lo) <= abs(f.offset - hi) else -1
            out.append(
                Wall(
                    id="",
                    direction=w.direction,
                    offset=piece.offset,
                    thickness=w.thickness,
                    thickness_source="paired-continuation",
                    pairing="single-sided",
                    r0=float(a),
                    r1=float(b),
                    r0_meas=float(a),
                    r1_meas=float(b),
                    z0=float(f.zmin),
                    z1=float(f.zmax),
                    faces=[piece],
                    body_side=side,
                    derivation="partial",
                )
            )
    return out


# --------------------------------------------------------------------------- ids


def assign_ids(walls: list[Wall]) -> None:
    """Stable ids: direction first, then position along it, so runs agree."""
    ordered = sorted(walls, key=lambda w: (round(w.direction, 2), round(w.axis_offset(), 2), w.r0_meas))
    for i, w in enumerate(ordered, 1):
        w.id = f"W{i:02d}"


# --------------------------------------------------------------------------- run


def unpaired_opposite_neighbours(walls: list[Wall], cfg: Config) -> int:
    """Unpaired face pairs that pass every geometric pairing rule (gap, overlap,
    medial) but were refused by facing or height. A high count means the pairing
    rate is being suppressed by those rules, not that the building is single-sided."""
    n = 0
    for direction in sorted({w.direction for w in walls}):
        # every face blocks medially, paired or not; only unpaired faces are counted
        group = sorted((f for w in walls if w.direction == direction for f in w.faces),
                       key=lambda f: f.offset)
        unpaired = {id(w.faces[0]) for w in walls if w.direction == direction and w.pairing != "paired" and w.faces}
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                lo, hi = group[i], group[j]
                if id(lo) not in unpaired or id(hi) not in unpaired:
                    continue
                gap = hi.offset - lo.offset
                if not (cfg.pair_min_thickness <= gap <= cfg.pair_max_thickness):
                    continue
                ov, short = _overlap(lo, hi), min(lo.length, hi.length)
                if not (ov >= cfg.pair_min_overlap * short or ov >= cfg.face_min_length):
                    continue
                if _medial_blocked(group, i, j, cfg):
                    continue
                # geometrically a pair; facing or height refused it
                if _pair_kind(lo, hi, cfg) is None:
                    n += 1
    return n


def run(model, cfg: Config = Config()) -> None:
    ceilings = CeilingMap(model.levels, cfg)
    model.walls = pair_faces(model.faces, cfg)
    model.meta["unpaired_opposite_neighbours"] = unpaired_opposite_neighbours(model.walls, cfg)
    model.walls.extend(residual_walls(model.walls, cfg))
    assign_single_sided(model.walls, model.cloud, model.levels, cfg)  # type: ignore[arg-type]
    assign_ids(model.walls)
    join_wall_ends(
        model.walls,
        max_gap=cfg.join_max_gap,
        perp_tol_deg=cfg.join_perp_tol_deg,
        min_angle_deg=cfg.join_min_angle_deg,
        extent_slack=cfg.join_extent_slack,
        inferred_reach=cfg.join_inferred_reach,
        is_doorway=doorway_check(model.cloud, model.levels, ceilings, cfg),
    )
    assign_heights(model.walls, model.levels, ceilings, cfg)
    if cfg.open_gap_before_rooms:
        from .s4_openings import bridge_door_gaps

        model.meta["gap_door_stats"] = bridge_door_gaps(model, cfg)
