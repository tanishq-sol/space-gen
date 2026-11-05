"""Every threshold in one place, with where it came from.

Design §11.3 requires each number to say whether it was *measured* on the sample
scan, *derived* from another number, or *chosen a priori*. A threshold with no
provenance is a policy decision nobody can defend, which is the same failure the
design deletes `confidence` for.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class Config:
    # -- stage 0: ingest ----------------------------------------------------
    # chosen a priori: a 0.5 m cell with fewer than 25 returns is scanner noise,
    # not a surface (2,150 stray points of 10.76 M on the sample scan).
    voxel_cell: float = 0.5
    voxel_min_points: int = 25
    # derived: every point-count threshold below was set on a 10 mm uniform
    # decimation, so the input is brought to that pitch first; that keeps them
    # valid at any source density (review R12). 0 keeps every point.
    decimate: float = 0.010
    # Scanner position when the file does not carry it (`--station`). Never
    # inferred: an origin that merely looks like a station is reported, not used.
    station: tuple[float, float, float] | None = None
    # Use `station` even when it fails its plausibility check (design §4.2 step 5).
    station_force: bool = False
    # Mobile scan: the sensor path (ASCII x y z t). Each point's scanner is the
    # path position nearest its time stamp (the point file's last column), thinned
    # to one station per `trajectory_step` metres of travel (design §4.2 step 5).
    trajectory: str | None = None
    trajectory_step: float = 0.2
    # Gap evidence asks only stations within this distance of a gap (§4.4.1).
    ray_reach: float = 25.0
    # Ground below a single station (--station, npz S, a single scan's pose): an
    # instrument height, because nothing else vouches for that point.
    station_ground: tuple[float, float] = (1.0, 2.2)
    # Ground below one scan's registered pose in a multi-scan file: low tripods
    # (pump sample 0.45 m) and raised stations (manitou sample 4.3 m) are real, and
    # the registration placed the pose; inside the cloud is the decisive test.
    scan_pose_ground: tuple[float, float] = (0.2, 6.0)

    # -- stage 1: levels ----------------------------------------------------
    # chosen a priori: ± this around a histogram peak is the plane's window — the
    # same 30 mm as the largest residual a flat floor may carry (level_max_rms).
    level_tol: float = 0.030
    # chosen a priori: a level point's normal is within ~25° of vertical. Mirrors
    # the |n_z| < 0.25 test that defines a wall point.
    level_min_normal_z: float = 0.90
    level_z_bin: float = 0.02
    # chosen a priori: enough points to fit three plane coefficients robustly.
    # Not a size test — level_min_area is — so it does not scale with density.
    level_fit_min_points: int = 200
    # chosen a priori: histogram peaks examined per cloud. The sample validates 30
    # planes, so 30 was binding; 80 leaves headroom and costs a few ms.
    level_max_candidates: int = 80
    # chosen a priori: a footprint component smaller than this is clutter, not part
    # of the surface (one ceiling spanning two rooms keeps both components).
    level_component_min_area: float = 1.0
    # chosen a priori: the floor is the lowest plane at least half the area of the
    # largest; a desk run never reaches it, grade seen through glazing rarely does.
    floor_min_share: float = 0.5
    # chosen a priori: with a known station, the floor lies at least this far
    # below the instrument (tripods stand 1.0-2.2 m tall).
    floor_below_station: float = 0.5
    # round 24, chosen after looking: a floor candidate must have a higher plane
    # `floor_cover_rise` above it over this share of its cells, else it is ground
    # outside (Longyearbyen 0.08, Anoeta's concourse 0.17). Chosen floors on the
    # development set: 0.58 (Grainger) to 0.97. When no candidate passes, the rule
    # is off (a scan with no ceiling keeps the old choice).
    floor_min_covered: float = 0.5
    floor_cover_rise: tuple[float, float] = (2.0, 8.0)
    # round 27, chosen after looking (tools/explore_floor_choice.py, 11 scans, UVigo
    # hidden): the floor is the lowest substantial candidate with walls standing on it
    # (`walls_standing`) at least this share of the most any candidate has. Anoeta's
    # -2.53 m pit has 0.07 of its real floor's (-1.19); Donor's garage floor 0.18 of its
    # garage ceiling's underside (2.47, which has the ground floor's walls on it) - the
    # thinnest margin; every other scan has one substantial candidate or keeps the
    # lowest. 0 turns the test off.
    floor_min_wall_share: float = 0.15
    # chosen a priori: 30 mm is the largest residual a flat floor should carry.
    level_max_rms: float = 0.030
    # derived from §4.2: a surface sloped more than this is not a level.
    level_max_slope_deg: float = 1.0
    # derived: the coverage bin used by stage 1 for faces, reused so the two
    # measurements share a resolution.
    level_cell: float = 0.1
    # chosen a priori: a level is a room-sized surface. The sample's floor is 24.4 m²
    # and its largest furniture surface 7.4 m²; the floor-share rule, not this cut,
    # is what keeps furniture from being the floor.
    level_min_area: float = 8.0
    # derived: a slab is 100-500 mm thick in the sample and in the drawing.
    slab_min_thickness: float = 0.10
    slab_max_thickness: float = 0.50
    # chosen a priori: two surfaces are the same slab only if they share most of
    # their footprint. 0.6 keeps the sample's two ceilings (different rooms)
    # apart while pairing a real slab.
    slab_min_overlap: float = 0.60

    # -- stage 1: wall faces -------------------------------------------------
    # chosen a priori: shorter than a partition return is not a wall. Applied as a
    # column count (six 0.20 m columns), so a run snapped to its points may measure
    # down to 1.10 m.
    face_min_length: float = 1.2
    # chosen a priori: a wall face has to span at least a metre vertically.
    face_min_zspread: float = 1.0
    # chosen: ~2x the 4.7-8.3 mm scan noise; accepted runs measure 4.2-9.4 mm.
    face_max_rms: float = 0.015
    # chosen a priori: accepted runs measure 0.90-1.00, so it is not binding here.
    face_min_cover: float = 0.50
    face_cover_frac: float = 0.20
    # chosen a priori, density-dependent: points per metre of run per metre of
    # observed height. Accepted runs measure 3,295-11,564 at the 10 mm pitch.
    face_min_density: float = 250.0
    # chosen a priori: a surface 30° off the projection direction is not the
    # surface being projected.
    face_min_normal_dot: float = 0.85
    # chosen a priori, density-dependent (re-derive at §9 step 3): projection bin,
    # peak floor (fraction of the strongest peak, and an absolute floor), the
    # widest peak that is one surface, the selection window around a peak, the
    # fewest points a line or run is fitted from, and the coverage bin.
    face_bin: float = 0.02
    face_thr_frac: float = 0.05
    face_thr_min: float = 40.0
    face_max_peak_width: float = 0.40
    face_window: float = 0.06
    face_min_points: int = 300
    face_cover_bin: float = 0.25
    face_trim: float = 0.02
    # chosen a priori: candidate lines come from the whole projection and from
    # 8 m tiles along it (half-overlapping), each tile against its own peak floor
    # but never below 0.2 x the whole projection's; inside one above-threshold
    # stretch, maxima 6 cm apart whose valley falls below 0.6 x the weaker are
    # separate surfaces (12 cm merged the two faces of TUB2's thin partitions:
    # faces found 0.715 -> 0.681; each fit trims to 2 cm of its own surface);
    # seeds 3 cm apart are one line. A tile seed 3-6 cm from the global one is
    # kept (it fits a slightly skewed wall better: Fire Brigade 0.47 -> 0.50);
    # fitted faces dedupe at 3 cm as before: 6 cm merged real faces on UoM (axis
    # correctness 0.77 -> 0.65). Ghost layers vs thin walls: open item (pairing).
    face_tile: float = 8.0
    face_tile_global_frac: float = 0.2
    face_split_sep: float = 0.06
    face_split_dip: float = 0.6
    face_seed_merge: float = 0.03
    face_dedupe_tol: float = 0.03
    # stage 1b, local faces (accuracy round 6; design: s1_local.py). chosen a priori:
    # vertical returns no face explains (5 cm) are cut into 2.5 m tiles; a tile
    # whose returns share one orientation (30 % within 3 deg), at least 5 deg off
    # every building direction, is searched along it; a chord is trimmed where it
    # lies within 5 cm of a face already kept.
    local_faces: bool = True
    local_tile: float = 2.5
    local_explained: float = 0.05
    local_min_share: float = 0.30
    local_min_offaxis: float = 5.0
    local_dup_dist: float = 0.05
    # review R6: tile directions on a 1 deg grid (the two faces of a curved wall
    # then share one and pair); a chord trimmed below 0.6 m is dropped
    local_dir_step: float = 1.0
    local_min_piece: float = 0.6
    # the chord pass's own face length and line tolerance (round 15, measured below): a
    # chord of a 12 m radius curve leaves the 2 cm line after ~2 m, and pilasters break it
    local_min_length: float = 1.2
    local_face_trim: float = 0.02
    # stage 1c, curved walls as arcs (round 16; design: s1_arcs.py). chosen a priori:
    # unexplained returns vote along their normals for centres 2-40 m away on a 0.5 m
    # grid, one vote per return per cell (thinned to one per 5 cm in plan); a cell of
    # >= 50 returns (about 2.5 m of curve seen from both faces) is a candidate, refined
    # from the returns whose normal line passes within 2 deg of it, and kept when their
    # normals span >= 4 deg (parallel lines are a straight wall); returns radial within
    # 15 deg are unrolled and searched; faces come back as chords sagging <= 1.5 cm
    # (1.2 m on a 12 m radius).
    # round 16b: off. With arc_require_full_height Grainger gains 13.1 m of curved wall
    # (0.7 m false), but every building without curves gets 0.4-3.2 m of false small arcs
    # (radius 2-4.6 m; TUB1 correctness -0.019, 2 false openings). accuracy_plan.md section 6.
    arc_faces: bool = False
    arc_min_radius: float = 2.0
    arc_max_radius: float = 40.0
    arc_vote_cell: float = 0.5
    arc_thin: float = 0.05
    arc_min_votes: int = 50
    arc_max_centres: int = 8
    arc_line_deg: float = 2.0
    arc_min_span_deg: float = 4.0
    arc_radial_deg: float = 15.0
    arc_chord_sag: float = 0.015
    # round 16b, set a priori with stage 2's pairing values: keep an arc only when a second
    # arc of its centre lies one wall thickness away over most of it. Measured on Grainger:
    # it drops the clutter but also the two large curved walls (one face found each), so
    # 4.8 m of wall is added, under the 10 m bar. Off.
    arc_require_pair: bool = False
    # round 16b, chosen AFTER reading Grainger's arcs (not a priori): an arc must reach the
    # ceiling (not partial-height). Every clutter arc there stopped below 2.4 m (cases, a
    # drum); straight faces still may be partial-height. Grainger: 13.1 m on walls added,
    # 0.7 m off.
    arc_require_full_height: bool = True
    # -- ceilings over walls -------------------------------------------------
    # chosen a priori: where the band's ceiling is read — this far off the face,
    # on the side the scanner looked from — and how far a ceiling footprint is
    # grown to reach the wall line it meets.
    ceiling_probe: float = 0.30
    ceiling_reach: float = 0.30
    # chosen a priori (about 3x the 30 mm level window): a wall column's top within
    # this of a surface counts as reaching it.
    ceiling_tolerance: float = 0.10
    # chosen a priori: storey height assumed when no ceiling was scanned at all.
    fallback_ceiling_height: float = 3.0
    # -- stage 1: wall runs along a face --------------------------------------
    # A fitted line is not a wall: desk fronts, cabinets and monitor backs line up
    # on one plane across a whole room. A wall is the stretch of that line that is
    # occupied *above furniture height*, where desks cannot occlude it.
    # derived: the §4.5 opening grid (0.20 m along the run, 0.10 m in z, >= 2 pts).
    run_col: float = 0.20
    run_cell_z: float = 0.10
    run_cell_min: int = 2
    # measured: real walls fill 70-100% of 1.2-2.2 m above the floor even behind
    # desks; furniture runs and phantom lines fill 0-20% (tools/explore_face_profile.py).
    run_upper: tuple[float, float] = (1.2, 2.2)
    # chosen a priori: the band stops this far under the local ceiling (cornices,
    # ceiling edges), and is never thinner than run_min_band.
    run_ceiling_margin: float = 0.30
    run_min_band: float = 0.30
    # chosen a priori, a midpoint between the observed clusters (walls 70-100%,
    # furniture and phantom lines 0-20%) — not a measured boundary.
    run_min_upper: float = 0.5
    # chosen a priori: a column with >= 10% of both its low and band cells present,
    # but not wall, is sparse at every height — the signature of glazing.
    run_glass_occ: float = 0.10
    # chosen a priori: a column whose low zone is >= 30% present and nothing above
    # it is furniture.
    run_low_occ: float = 0.30
    # chosen a priori: a rejected line is named after a column class that covers
    # this share of it.
    run_reason_share: float = 0.30
    # chosen a priori: a run whose wall columns stop this far under the local
    # ceiling is tagged partial-height (tall furniture, a screen, a pod wall).
    run_partial_gap: float = 0.40
    # chosen a priori: a lintel needs a head zone of at least this many cells
    run_lintel_min_cells: int = 3
    # chosen a priori: a 0.4 m break is a column of clutter or a shadow, not an end.
    run_gap_free: float = 0.40
    # derived: a door or opening under a lintel is up to 2.4 m wide; a gap is
    # bridged only where >= 70% of its columns carry the lintel (>= 50% of the head
    # zone above floor+2.2 occupied).
    run_gap_lintel: float = 2.40
    run_lintel_share: float = 0.70
    run_lintel_occ: float = 0.50
    # measured (round 14, tools/explore_facade.py): on Fire Brigade's 43 m facade of
    # paired windows the piers between pairs are 0.1-0.5 m wide and their returns face
    # sideways (normals at the reveals): only 23-35% of the band's points pass the
    # normal filter, so the piers vanish and the line is rejected (31 reference windows
    # on it). A pier is a column whose band is occupied by returns of any normal, under
    # a head zone occupied by aligned returns (the wall above the windows); it anchors
    # a run like a wall column. Furniture cannot make one: it needs a surface on the
    # line above the band.
    run_piers: bool = True
    # a run that needs piers is kept only as a row of windows: at least this many
    # bridged gaps in it; elsewhere the line's runs are found as without piers (round 14:
    # piers everywhere reshaped walls already right on UoM and UVigo and lost openings)
    run_pier_min_bridges: int = 3
    # ...and only where the line's runs without piers cover less than this share of it:
    # piers are for walls stage 1 otherwise loses, not for reshaping walls it has
    # (review R14-2: a stray pier at a door leaf's edge would split a corridor wall's door)
    run_pier_needed: float = 0.9
    # measured (round 14, five buildings): openings read from the lintel alone on a
    # pier-anchored span were real 18 of 45. Such a span becomes an opening only on the
    # gap rules' evidence (round 9/13): floor through it (a door) or wall/radiator under
    # a window-shaped opening at the face (a window); else it stays wall.
    open_pier_evidence: bool = True
    # pier-anchored spans make openings at all. Measured with run_pier_min_bridges 3:
    # with the evidence and no width limit Fire Brigade +2 real doors, +4 false (ours real
    # 0.806 -> 0.763); off, UVigo lost the 2 windows its window row carries (found 0.323 ->
    # 0.258). On, up to open_pier_max_width: UVigo unchanged, Fire Brigade 0.784.
    open_pier_openings: bool = True
    # pier-anchored spans make openings only within the gap rules' measured widths
    # (open_gap, 0.6-1.3 m): the false ones on Fire Brigade were 2.2-2.4 m spans
    open_pier_max_width: float = 1.3
    # derived: two direction peaks closer than 25° are the same wall system.
    direction_pair_separation: float = 25.0
    # chosen (round 2, from the normal-angle histograms of UoM and Grainger Museum):
    # a further wall direction is a normal-angle peak 10 deg from any other, 1.25x the
    # median bin, holding 2 % of the vertical points within 2 deg; at most six.
    direction_min_separation: float = 10.0
    direction_min_contrast: float = 1.25
    direction_min_share: float = 0.02
    direction_max: int = 6
    direction_step: float = 0.5
    # chosen a priori: walls are measured on the storey band, not at the floor
    # where furniture dominates.
    band_floor_offset: float = 0.20
    band_ceiling_offset: float = 0.10
    # derived: the direction search samples the occupied middle of the storey.
    direction_band: tuple[float, float] = (0.9, 1.7)

    # -- stage 2: pairing ----------------------------------------------------
    # chosen a priori: below 40 mm two faces are one surface read twice (the
    # sample's only pair is a 59 mm layered partition).
    pair_min_thickness: float = 0.04
    # chosen a priori: a thick masonry or structural wall. No wall thicker than
    # 59 mm has been measured on the sample (design §5.5).
    pair_max_thickness: float = 0.45
    # Faces are sorted by their midpoint offsets; a pair is still checked when those
    # differ by up to this much more than the largest thickness (sloped long faces).
    pair_slope_slack: float = 0.30
    # Station-free side evidence for single-sided walls (s2_walls._side_evidence):
    # floor returns within 0.15-0.6 m of the face on a side; "present" when at least
    # this share of 0.2 m columns along the face has them, "absent" at or below.
    side_floor_present: float = 0.5
    side_floor_absent: float = 0.15
    side_floor_tol: float = 0.05  # |z - floor| for a floor return
    side_evidence_max_points: int = 3_000_000
    # A parallel layer behind a face counts as the wall's far face when a 2 cm bin
    # holds at least this many points and this share of the face's own points.
    behind_layer_min_points: int = 30
    # 0.10 (accuracy round 3, was 0.25): a far face seen from the next room is
    # sparser than the near face; at 0.25 thin walls' far faces (~24 % of the near
    # face) were missed and the point-count fallback chose the wrong side 20 of 28
    # times. Fire Brigade correctness 0.80 -> 0.83, UoM 0.79 -> 0.80.
    behind_layer_share: float = 0.10
    # chosen (review R3-3A): a far-face layer runs along >= 60 % of the face's 0.2 m
    # columns; a cabinet, radiator or reveal does not.
    behind_layer_cover: float = 0.60
    # chosen a priori: below 55% length overlap the two faces are different walls.
    pair_min_overlap: float = 0.55
    # derived from §4.3: candidates within 20 mm of each other are ambiguous.
    pair_ambiguity: float = 0.02
    # chosen (accuracy round 3): two pairs of one face are separate stretches when
    # they overlap along it by no more than this (run ends are quantised to 0.2 m).
    pair_span_slack: float = 0.20
    # chosen a priori: a third face between a pair means the pair spans a chase.
    pair_medial_min_overlap: float = 0.10
    # chosen a priori: a median stands in for an unmeasured thickness only when at
    # least three paired walls back it; otherwise a stated 100 mm partition default.
    assumed_min_samples: int = 3
    assumed_default_thickness: float = 0.10
    # User decision 2026-10-28 (was 300 mm, 2026-10-27): an envelope wall seen from
    # inside only takes this building's measured pair median when at least
    # `assumed_min_samples` pairs back it, else 200 mm. On the ISPRS references walls
    # are mostly 100-220 mm and the 300 mm body was the largest false-area source.
    envelope_default_thickness: float = 0.20
    # chosen a priori: a face counts as "beyond" a wall only over this much
    # common run; a few millimetres of overlap at a jog is not a wall behind it.
    envelope_min_overlap: float = 0.50
    # chosen a priori: two same-facing surfaces this close are one wall seen
    # through glazing or a lining; further apart they are two things.
    layered_max: float = 0.15

    # -- stage 2: corner joining ---------------------------------------------
    # derived from §4.3: beyond 300 mm the wall does not meet a perpendicular one.
    join_max_gap: float = 0.30
    # derived: the sample's two directions are 90.45° apart.
    join_perp_tol_deg: float = 5.0
    # chosen (accuracy round 3): walls of the oblique directions a radial plan has
    # meet at any angle of 20 deg or more; nearer parallel than that is not a corner.
    join_min_angle_deg: float = 20.0
    # chosen a priori: an intersection landing outside the other wall's measured
    # extent by more than this is not on that wall.
    join_extent_slack: float = 0.10
    # derived from §4.4's closure limit, revised 2026-10-27 after review: a corner
    # where both walls stop short is closed when the extension plus the partner's
    # shortfall together stay within 0.6 m and no lintel shows the gap is a door.
    join_inferred_reach: float = 0.60

    # -- stage 3: rooms ------------------------------------------------------
    # chosen a priori: a closed region smaller than this is a wall core, a duct
    # shaft or a bay, not a room. The sample's smallest real cell is 0.64 m2 and
    # its wall cores are all below 0.64 m2, so 1 m2 is the design's own cut.
    room_min_area: float = 1.0
    # chosen a priori: a storey is not 500 m2 in one space on a terrestrial scan.
    room_max_area: float = 500.0
    # -- stage 4: openings (design §4.5; accuracy round 8) ----------------------
    # derived from §4.5: 0.20 m columns x 0.10 m cells, present with >= 2 returns
    # within 3 cm of the face; a void is >= 2 cells tall and 0.4-3.0 m wide; a void
    # whose cells mostly hold returns 5-60 cm off the face is a furniture shadow.
    # measured (round 8): voids found by the face grid alone were real 9 times in 109
    # (scan gaps and furniture shadows look the same); lintel-bridged gaps 61 in 107.
    # The grid search stays available but off until it has better evidence.
    open_void_search: bool = False
    open_col: float = 0.20
    open_cell_z: float = 0.10
    open_min_pts: int = 2
    open_trim: float = 0.03
    open_min_cells: int = 2
    open_min_width: float = 0.40
    open_max_width: float = 3.0
    open_occluder: float = 0.60
    open_occluded_share: float = 0.5
    # diagnostics only (headroom step, 2026-11-01): keep each void rejected as a shadow
    # in model.meta["occluded_voids"], with the share of its off-face cells that lie
    # into the wall (behind the face, toward the wall's body) rather than in the room
    open_debug: bool = False
    # §4.5 classes: door sill <= 0.15 m, head 1.8-2.4 m, width 0.6-2.0 m;
    # window sill >= 0.45 m and >= 0.4 m tall; else unresolved
    # measured (round 14, Fire Brigade's facade): paired windows bridged as one span
    # matched one window of the two; their mullion shows as a narrow cluster of 5-19
    # returns per 5 cm within 0.15 m of the face in the glass band, empty either side.
    # A window span is split there when both parts stay >= open_min_width. On the
    # benchmark it found no more windows (Fire Brigade 0.372 either way) and added false
    # parts (UVigo ours real 0.667 -> 0.588): off.
    open_mullion_split: bool = False
    open_mullion_depth: float = 0.15
    open_mullion_pts: int = 5
    open_mullion_max_width: float = 0.20
    open_mullion_clear: float = 0.20
    door_sill_max: float = 0.15
    door_head: tuple[float, float] = (1.8, 2.4)
    door_width: tuple[float, float] = (0.6, 2.0)
    window_sill_min: float = 0.45
    window_min_height: float = 0.4
    # a lintel-bridged gap with wall returns 0.2 m up to this height below it, in half
    # its columns, is a window; an opening clipped below 0.3 m wide by a join is dropped
    open_sill_band: float = 0.9
    open_min_keep: float = 0.3
    # measured (round 9, tools/explore_gap_evidence.py): a door with no lintel over
    # it (TUB1's doors reach its 2.0-2.2 m ceiling) splits its wall in two. A gap of
    # 0.6-1.3 m between an open wall end and a collinear wall, with floor returns
    # in >= 70% of the wall's footprint continued across it (a wall's own footprint
    # is never scanned at floor level), sat on a reference door or window at most
    # such gaps on five buildings; gaps against a crossing wall far less often, so
    # they are not used. Benchmark (round 9): doors found TUB1 4 -> 12 (one false),
    # TUB2 10 -> 12 (+2 windows), Fire Brigade 1 -> 3, GM 6 -> 7. Bridging before the
    # rooms are traced (open_gap_before_rooms) cost TUB1 two matched rooms (7 -> 5):
    # off.
    open_gap_doors: bool = True
    open_gap: tuple[float, float] = (0.6, 1.3)
    open_gap_floor: float = 0.7
    # a lintel opening whose read sill is above a door's, with floor returns inside the
    # wall's footprint by the rule above, is a door: a leaf or furniture stood in it
    # (round 18; UoM and Grainger doors read as windows)
    open_floor_through_door: bool = True
    # review R9-3 (measured): floor cells need >= open_min_pts returns, clear of the
    # wall's faces by this margin, and floor must show on both sides of the line.
    # Doors found then TUB1 11 (all real), TUB2 12, Fire Brigade 2, GM 7; with no
    # margin only false openings were added (TUB1 +1, TUB2 +1).
    open_gap_face_clear: float = 0.03
    open_gap_before_rooms: bool = False
    # measured (round 10, tools/explore_gap_evidence.py walk column): a 0.6-1.3 m gap
    # between a wall end and a crossing wall that the scanner's path walks through
    # was a missed door 5 times (TUB1 2, TUB2 3) and nothing once; UVigo had none.
    # Wider walked gaps were mixed (2 doors, 5 nothing): not used.
    open_gap_walk: bool = True
    # round 13 (headroom step, accuracy_brainstorm.md §7): a collinear 0.6-1.3 m gap with no
    # floor through it is a window when the wall continues below its sill and above its
    # head: returns within the wall's footprint 0.3-0.8 m up and >= 1.9 m up in
    # `open_gap_window_share` of its 0.1 m columns. Below the sill anything within
    # `open_gap_sill_reach` of the wall line counts: radiators hide the wall under most of
    # Fire Brigade's windows (sill share was 0.0 at the wall itself). Measured on Fire
    # Brigade: windows 22 -> 25 with the glass band required mostly empty, 27 without it
    # (blinds and frames fill the band; all new windows real), so the glass test is off
    # (open_gap_glass_max 1.0). Its missed windows sit in 0.88-1.24 m gaps (headroom).
    open_gap_windows: bool = True
    open_gap_sill: tuple[float, float] = (0.3, 0.8)
    open_gap_head_min: float = 1.9
    open_gap_glass: tuple[float, float] = (1.2, 1.8)
    open_gap_window_share: float = 0.6
    open_gap_sill_reach: float = 0.35
    # returns more than this behind a wall face, inside the wall's body, are reveal
    # content (glass, frames, blinds set back in the opening), not the wall below the
    # sill or above the head: TUB2's windows sit ~20 cm back and filled the sill run
    # (round 13 review fix R13-6)
    open_gap_reveal_clear: float = 0.04
    open_gap_glass_max: float = 1.0
    # measured (round 13, all buildings): window gaps in walls seen from both sides with
    # returns filling the glass band were false 5 of 5 (Grainger Museum 3, TUB1, UoM);
    # the real ones were all in one-sided (outer) walls, glass band 0.09-1.0
    open_gap_paired_glass_max: float = 0.95
    # measured (round 10, tools/explore_ray_cross.py): with a scanner position per
    # point (a trajectory), a return beyond a wall whose beam crossed the wall's
    # axis inside its extent went through an opening there; furniture stops beams,
    # it cannot fake one. Station heights are not trusted, so only the plan
    # crossing is used, and returns above min(wall top, open_beam_zcap) are left
    # out (beams over a wall, or from the storey above, TUB2). Cells of 0.1 m with
    # >= open_beam_min crossings form runs.
    #   window: no beam lower than open_beam_window_z (the far returns' 5th
    #     percentile) — TUB1/TUB2/UVigo: 8 on reference windows, 1 off by 0.9 m;
    #   door: the scanner itself walked through the wall line in the run, its beams
    #     reach down to the floor (< open_beam_door_z) and it is a door wide:
    #     5 on reference doors, 2 at 0.9 m from one, 2 on nothing.
    # Beams with no walk-through (open doors seen from one room) were mixed; unused.
    open_beam: bool = True
    open_beam_min: int = 10
    open_beam_zcap: float = 2.4
    open_beam_sdist: float = 0.4
    open_beam_window_z: float = 1.0
    open_beam_window_width: tuple[float, float] = (0.3, 2.0)
    # first benchmark (round 10): 3 of 5 false beam openings covered their whole
    # wall (a false wall drawn across a doorway); one was 2.6 m wide (UVigo), one
    # a walk-through not shaped like a door. A run over >= this share of its wall
    # is skipped; a beam door must class as a door.
    open_beam_max_cover: float = 0.75
    # review R10 (a priori): beam height at the wall from a nominal sensor height
    # when station heights are untrusted; beams meeting the wall at under ~17 deg
    # (|cross-wall| < incidence x length) are dropped, a station error moves their
    # crossing far; a station with under this share of the median station's returns
    # in the storey is on another storey; a path step longer than walk_step is a gap.
    # measured (round 10): dropping walls seen through floor to head over >= 75 % of
    # their length raised wall correctness TUB1 0.941 -> 0.954, TUB2 0.959 -> 0.969 but
    # on the hold-out UVigo cut completeness 0.640 -> 0.580 and halved its openings
    # (real walls seen through there: glass or trajectory timing). Off.
    open_beam_drop_walls: bool = False
    # Round 22 (2026-11-03): one doorway, one opening. Openings on parallel walls (within
    # open_twin_deg) whose centres lie within open_twin_dist (the benchmark's match radius,
    # set a priori) and whose spans overlap are one opening (s4_openings.dedupe_twins).
    # Measured: 7 such pairs in TUB2, FB, UVigo and Grainger, never two real ones. 0 = off.
    open_twin_dist: float = 0.6
    open_twin_deg: float = 5.0
    # Round 23 (2026-11-03): windows between windows (s4_openings.row_windows). Walls on one
    # line: direction within open_row_deg, axis within open_row_offset (a priori). A gap between
    # two windows of ours that is a whole number (2..open_row_max_steps) of the row's step, to
    # within open_row_phase of a step, holds the windows in between; across a gap between wall
    # pieces only with wall within open_row_reach on both sides (a priori). open_row_phase chosen
    # AFTER looking: 0.15 (set first) gave 8 windows, 0.25-0.40 give the same 11 on four buildings,
    # none false (tools/explore_window_rows.py).
    open_row_windows: bool = True
    open_row_deg: float = 1.0
    open_row_offset: float = 0.2
    open_row_phase: float = 0.3
    open_row_max_steps: int = 4
    open_row_reach: float = 1.5
    open_beam_sensor_h: float = 1.4
    open_beam_incidence: float = 0.3
    open_beam_station_share: float = 0.2
    open_beam_walk_step: float = 1.0
    open_beam_door_z: float = 0.5
    open_beam_door_width: tuple[float, float] = (0.5, 1.6)
    # -- storeys (accuracy round 5) ------------------------------------------
    # chosen a priori: another storey's floor is a horizontal plane of at least
    # 40 m2, 2.2 m or more above the storey below (a clear height); two planes
    # within 0.6 m are one slab, and its upper surface is the floor; walls must
    # stand on it — vertical returns 0.9-1.7 m above it at least 15 % of the main
    # storey's — or it is a ceiling underside seen from below.
    multi_storey: bool = True
    storey_min_area: float = 40.0
    storey_min_height: float = 2.2
    storey_slab_max: float = 0.6
    storey_min_wall_share: float = 0.15
    # round 27: storeys closer than storey_min_height are told apart by the walls standing
    # on each (vertical returns `storey_wall_band` above it, inside its footprint grown
    # `storey_wall_reach`), not by height order; the wall test is the same count (it was
    # the whole cloud's band, which a wall-less pit shares with the storey above it).
    # False restores the old order (the lower floor wins, whole-cloud wall test).
    storey_by_walls: bool = True
    storey_wall_band: tuple[float, float] = (0.9, 1.7)
    storey_wall_reach: float = 1.0
    # set per storey run: take the floor as the large plane nearest this height
    floor_hint: float | None = None
    # stage 3b, rooms from free space (accuracy round 4; design: s3_freespace.py).
    # chosen a priori: 0.1 m cells; openings up to about 1.0-1.2 m clear split
    # rooms (an interior door leaf is 0.8-0.9 m); a seed under 1.5 m2 after that erosion is
    # a niche; furniture hides at most 4 m2 of floor; a region that is 30 % inside
    # a wall-traced room is that room, not a new one.
    room_free_space: bool = True
    room_fs_gap_doors: bool = True
    room_fs_small_seed_min: float = 0.5
    room_fs_small_wall_share: float = 0.6
    room_fs_cell: float = 0.10
    room_fs_door: float = 1.0
    room_fs_seed_min: float = 1.5
    room_fs_hole_max: float = 4.0
    room_fs_overlap_max: float = 0.30
    # a floor cell needs this many returns (one stray return is not floor);
    # a grid above this many cells (50 M: a 700 m square at 0.1 m) is refused
    room_fs_min_returns: int = 2
    # a free-space region with less than this share of ceiling over it is outdoors
    room_fs_min_ceiling_cover: float = 0.15
    # Round 21 (2026-11-03): ... unless our walls run along this share of its outline (within
    # room_fs_walled_reach of a wall footprint): an enclosed space whose overhead was not scanned
    # (a courtyard or a glazed roof), kept with no ceiling height. Chosen AFTER looking (Grainger:
    # the 74.5 m2 gallery 0.78 against 0-0.51 for its outdoor ground); UVigo's two such regions are
    # the out-of-sample check. 0 turns it off.
    room_fs_walled_min: float = 0.7
    room_fs_walled_reach: float = 0.3
    # chosen a priori: a room grows at most 1 m into floor hidden under furniture
    room_fs_reach: float = 1.0
    room_fs_max_cells: int = 50_000_000
    # Rooms on a sunken floor (round 19). Grainger Museum's galleries lie 0.05-0.26 m
    # below the storey floor and Fire Brigade has floors 0.16-0.38 m down; the floor
    # test (|z - floor| < side_floor_tol) saw none of it, so two scanned rooms of
    # 30-75 m2 read as unscanned. A validated horizontal plane below the floor cannot
    # be furniture (furniture stands on the floor), so its returns inside its own
    # footprint are floor too. Chosen a priori: down to 0.5 m (three risers), planes
    # of at least 4 m2 (smaller ones are steps, pits, drains). A floor beside the
    # floor shares at most its rim with the floor's footprint: set AFTER measuring,
    # on one building each way (Grainger's three 0.01-0.14 kept; Fire Brigade's 0.43
    # and 0.47 are woven through its hall's floor, not beside it: reflections or a
    # grating, and they split the hall); any value 0.15-0.4 gives the same result.
    # TUB1, TUB2, UVigo and UoM have no plane in range: unchanged by construction,
    # not evidence. Off on storey runs and for slab undersides. 0 turns it off.
    room_fs_sunken_max: float = 0.5
    room_fs_sunken_min_area: float = 4.0
    room_fs_sunken_max_shared: float = 0.25
    # a room takes a sunken floor's height only when that floor covers at least this
    # share of it (and more than the storey floor does); a patchy read keeps the
    # storey floor (review R19-3). Chosen a priori, as room_ceiling_cover.
    room_floor_cover: float = 0.5
    # erosion radii: door/2, then +0.25 m steps; seven levels reach 2.0 m (a 4 m opening)
    room_fs_levels: int = 7
    # derived from the face residual RMS (4.5-12.2 mm on the sample): a boundary
    # stretch further than this from a wall face is a chord we invented, not a
    # wall. Design §4.4 keeps 60% of the perimeter as the supporting fraction.
    room_support_tol: float = 0.02
    room_min_support: float = 0.60
    # derived from §4.2/§6.4: a ceiling is >= 2.0 m above the floor (the clear-height
    # floor), and must cover half the room after closing light-panel holes.
    room_min_clear: float = 2.0
    room_ceiling_cover: float = 0.5
    # chosen a priori: a second surface over this share of the room is recorded
    # as a second ceiling height (a room with a soffit or a step).
    room_ceiling_alt_cover: float = 0.25
    # derived from the same residual: boundary vertices are exact intersections
    # of fitted lines, so a measured edge sits within microns of its wall face.
    # Anything further than 2 mm is a stretch stage 3 drew itself, and its length
    # is reported as `bridged_m` rather than being called a wall.
    room_bridge_tol: float = 0.002
    # derived from the design's closure bands: 45 mm is measurement noise and is
    # closed silently; up to 600 mm is closed and recorded; beyond that the ring
    # is not a room and is reported as an open end instead of being invented.
    closure_silent: float = 0.045
    closure_max: float = 0.600
    # §4.4.1 gap evidence, revised after the stage-3 review. chosen a priori:
    # an occluded chord is at most 1.0 m (a hidden corner, not a missing wall);
    # evidence needs >= 3 rays (one stray return proves nothing); a ray counts as
    # through or blocked when it ends >= 0.15 m beyond or short of the chord;
    # rays are read 1.0-1.8 m above the floor, above desks and half-height
    # partitions and below door heads.
    occluded_max: float = 1.0
    gap_min_rays: int = 3
    occluded_beyond: float = 0.15
    gap_ray_band: tuple[float, float] = (1.0, 1.8)
    # chosen a priori: a gap rays pass through is an opening a room boundary may
    # cross (as at a door) up to the widest single door, 1.2 m; wider, the two
    # spaces are one and the gap is reported open.
    opening_max: float = 1.2
    # §4.4.1 hidden partitions. chosen a priori: a rejected line crossing a room
    # over >= 1.2 m (a wall's minimum run), clear of every accepted face. Only
    # reasons that are evidence of a partition: `empty-band` lines are furniture and
    # phantom lines spanning the building (measured: they crossed every room).
    partition_reasons: tuple[str, ...] = ("glass-signature", "head-only")
    partition_min_length: float = 1.2
    # measured: a lintel line 0.11 m inside a room's wall face (the header over
    # that wall) flagged the room at 0.10; a partition stands well inside a room.
    partition_face_clear: float = 0.30

    def with_(self, **kw) -> "Config":
        return replace(self, **kw)


DEFAULT = Config()
