"""Stage 0 — read a point cloud into metres, Z-up, with unit normals.

Supported inputs:

| extension | reader | notes |
|---|---|---|
| `.e57` | `pye57` (optional) | terrestrial scanner exchange format, registered stations |
| `.ptx` | built in | Leica/Faro text export, one 4x4 pose per station |
| `.las` / `.laz` | `laspy` (optional) | aerial and mobile LiDAR |
| `.ply` | Open3D | already-registered clouds |
| `.txt` / `.xyz` / `.asc` / `.pts` / `.csv` | built in, streamed | ASCII columns: x y z [...], colour taken when the last three columns are 0-255 integers |
| `.npz` | built in | `P`, `N`, `C` arrays — the fast path for repeat runs |

The optional readers are imported lazily so the package works without them and
fails with a sentence rather than an ImportError traceback.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import numpy as np

from .config import Config
from .model import Cloud

ASCII = {".txt", ".xyz", ".asc", ".pts", ".csv"}
SUPPORTED = {".e57", ".ptx", ".las", ".laz", ".ply", ".npz"} | ASCII


def source_hash(path: str | os.PathLike, chunk: int = 1 << 20) -> str:
    """BLAKE2b-128 of the file, used for deterministic ids and provenance."""
    h = hashlib.blake2b(digest_size=16)
    with open(path, "rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def load(path: str | os.PathLike, cfg: Config = Config()) -> Cloud:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED:
        raise ValueError(f"{path.name}: unsupported input. Expected one of {', '.join(sorted(SUPPORTED))}.")

    if suffix == ".npz":
        cloud = _load_npz(path)
    elif suffix == ".e57":
        cloud = _load_e57(path, voxel=cfg.decimate)
    elif suffix in ASCII:
        cloud = _load_ascii(path, voxel=cfg.decimate, keep_time=cfg.trajectory is not None)
    elif suffix == ".ptx":
        cloud = _load_ptx(path)
    elif suffix in (".las", ".laz"):
        cloud = _load_las(path, voxel=cfg.decimate, keep_time=cfg.trajectory is not None)
    else:
        cloud = _load_open3d(path)

    cloud.source = str(path)
    if not cloud.n_input:
        cloud.n_input = len(cloud.points)

    streamed = suffix in (".e57", ".las", ".laz") or suffix in ASCII  # these decimate as they read
    if cfg.decimate > 0 and not streamed:
        cloud = decimate(cloud, cfg.decimate)
    if cloud.normals is None:
        estimate_normals(cloud)
    if cfg.trajectory:
        attach_trajectory(cloud, Path(cfg.trajectory), cfg.trajectory_step)
    return cloud


def load_trajectory(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """(times, xyz) of a sensor path file: ASCII x y z t per line, sorted by time."""
    skip, delim, ncol = _ascii_layout(path)
    if ncol < 4:
        raise ValueError(f"{path.name}: a trajectory needs x y z t columns, found {ncol}")
    arr = np.loadtxt(path, delimiter=delim, skiprows=skip, usecols=range(4), ndmin=2)
    arr = arr[np.isfinite(arr).all(1)]
    order = np.argsort(arr[:, 3], kind="stable")
    return arr[order, 3], arr[order, :3]


def attach_trajectory(cloud: Cloud, path: Path, step: float = 0.2) -> None:
    """Give every point the scanner position it was measured from.

    The path is thinned to one station per `step` metres of travel; a point takes
    the station nearest its time stamp, so its scanner is off by at most about
    step/2 plus the distance travelled in half a sample. A point timed outside the
    path gets no scanner. Heights of trajectory stations are not trusted (one
    benchmark path is flat z = 0), so only their plan positions are used."""
    if cloud.times is None:
        raise ValueError("a trajectory needs per-point time stamps: the point file's last column")
    t, xyz = load_trajectory(path)
    if len(t) < 2:
        raise ValueError(f"{path.name}: fewer than two trajectory samples")
    travelled = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(xyz[:, :2], axis=0), axis=1))]
    keep = np.r_[True, np.diff(np.floor(travelled / step)) > 0]
    keep[-1] = True
    ts, xs = t[keep], xyz[keep]
    pos = np.clip(np.searchsorted(ts, cloud.times), 1, len(ts) - 1)
    nearer = np.where(np.abs(cloud.times - ts[pos - 1]) <= np.abs(ts[pos] - cloud.times), pos - 1, pos)
    span = (cloud.times >= t[0] - 1.0) & (cloud.times <= t[-1] + 1.0)
    cloud.scan_index = np.where(span, nearer, -1).astype(np.int64)
    cloud.stations = xs.astype(np.float64)
    cloud.stations_z_known = False
    cloud.scan_stations = []
    cloud.file_station = None
    cloud.file_station_kind = f"trajectory ({path.name}, {len(xs)} stations, {travelled[-1]:.0f} m)"


# ------------------------------------------------------------------------ readers


def _load_npz(path: Path) -> Cloud:
    d = np.load(path)
    points = np.asarray(d["P"], dtype=np.float64)
    normals = np.asarray(d["N"], dtype=np.float64) if "N" in d else None
    colours = np.asarray(d["C"], dtype=np.float64) if "C" in d else None
    cloud = Cloud(points=points, normals=normals, colours=colours)
    if "SI" in d and "ST" in d:
        # multi-scan: scan index per point and one scanner position per scan
        # (e.g. tools/register_stations.py), checked per scan like an E57's poses
        st = np.asarray(d["ST"], dtype=np.float64).reshape(-1, 3)
        cloud.scan_index = np.asarray(d["SI"], dtype=np.int64)
        cloud.scan_stations = [(s, "npz ST") for s in st]
        cloud.file_station_kind = f"multi-scan npz ({len(st)} scans)"
    elif "S" in d:
        cloud.file_station = np.asarray(d["S"], dtype=np.float64).reshape(3)
        cloud.file_station_kind = "npz S"
    return cloud


def _load_open3d(path: Path) -> Cloud:
    import open3d as o3d

    pcd = o3d.io.read_point_cloud(str(path))
    points = np.asarray(pcd.points, dtype=np.float64)
    if len(points) == 0:
        raise ValueError(f"{path.name}: no points read — is the file a registered cloud?")
    colours = np.asarray(pcd.colors, dtype=np.float64) if pcd.has_colors() else None
    return Cloud(points=points, colours=colours)


def _load_e57(path: Path, voxel: float = 0.0, chunk_size: int = 5_000_000) -> Cloud:
    """Stream an E57: read in chunks, apply each scan's pose, reduce to voxel
    centroids as it goes, so a 184.6 M-point scan never sits in memory at full
    density. Colour and intensity are carried when every scan has them."""
    try:
        import pye57  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on the machine
        raise RuntimeError(
            "E57 input needs the optional 'pye57' package: pip install pye57. It wraps libE57Format and is free."
        ) from exc

    scan = pye57.E57(str(path))
    if scan.scan_count == 0:
        raise ValueError(f"{path.name}: the E57 holds no scans")
    headers = [scan.get_header(i) for i in range(scan.scan_count)]
    for i, h in enumerate(headers):
        if not set(_XYZ) <= set(h.point_fields):
            raise ValueError(
                f"{path.name}: scan {i} has no cartesian coordinates; spherical-only E57 files are not supported yet"
            )
    colour = all(set(_RGB) <= set(h.point_fields) for h in headers)
    intensity = all("intensity" in h.point_fields for h in headers)

    acc = VoxelAccumulator(voxel, compact_at=4 * chunk_size) if voxel > 0 else None
    parts: list[dict[str, np.ndarray]] = []
    n_input = n_invalid = 0
    for i, header in enumerate(headers):
        rot = _quat_matrix(np.asarray(header.rotation, dtype=np.float64))
        trans = np.asarray(header.translation, dtype=np.float64).reshape(3)
        for n_raw, cols in _e57_chunks(scan, i, header, chunk_size, colour, intensity):
            n_input += n_raw
            n_invalid += n_raw - len(cols["points"])
            cols["points"] = cols["points"] @ rot.T + trans  # the scan's pose: local -> file frame
            cols["scan"] = np.full(len(cols["points"]), i, dtype=np.int64)
            if acc is not None:
                acc.add(cols)
            else:
                parts.append(cols)
    if acc is not None:
        cols = acc.result()
    elif parts:
        cols = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    else:
        cols = {"points": np.empty((0, 3))}
    if len(cols["points"]) == 0:
        raise ValueError(f"{path.name}: no valid points in the E57")
    cloud = Cloud(
        points=cols["points"],
        colours=cols.get("colours"),
        intensity=cols.get("intensity"),
        hits=cols.get("hits"),
        n_input=n_input,
        n_dropped=n_invalid,
        scan_index=cols.get("scan") if scan.scan_count > 1 else None,
    )
    # A single scan's pose is offered as the station, to be checked by
    # establish_station. It is a hint, not a source: the sample file stores its
    # points pre-offset, so after the pose the scanner sits at the origin and the
    # pose translation (8.47, 3.67) lies outside the cloud.
    if scan.scan_count == 1 and headers[0].has_pose():
        cloud.file_station = np.asarray(headers[0].translation, dtype=np.float64).reshape(3)
        cloud.file_station_kind = "E57 pose"
    elif scan.scan_count > 1:
        cloud.file_station_kind = f"multi-scan E57 ({scan.scan_count} scans)"
        # One candidate per scan, each checked on its own by establish_station. A
        # scan without a pose is, by the E57 standard, in the file frame with its
        # sensor at the origin — in a registered multi-scan file that is the
        # reference scan. (Not applied to a single scan: a pose-less single scan is
        # usually a merged export whose origin means nothing.)
        cloud.scan_stations = [
            (np.asarray(h.translation, dtype=np.float64).reshape(3), "E57 pose")
            if h.has_pose()
            else (np.zeros(3), "E57 no pose: sensor at the file origin")
            for h in headers
        ]
    return cloud


_XYZ = ("cartesianX", "cartesianY", "cartesianZ")
_RGB = ("colorRed", "colorGreen", "colorBlue")


def _ascii_layout(path: Path) -> tuple[int, str | None, int]:
    """(header lines to skip, delimiter, columns) from the first lines of an ASCII cloud."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh):
            if i > 50:
                break
            delim = "," if "," in line else (";" if ";" in line else None)
            parts = [x for x in (line.split(delim) if delim else line.split()) if x.strip()]
            try:
                vals = [float(x) for x in parts]
            except ValueError:
                continue
            if len(vals) >= 3:
                return i, delim, len(vals)
    raise ValueError(f"{path.name}: no line with three numbers in the first 50 — not an ASCII point cloud")


def _is_rgb(a: np.ndarray) -> bool:
    return bool(a.shape[1] == 3 and np.all((a >= 0) & (a <= 255)) and np.all(a == np.round(a)))


def _intensity_scale(v: np.ndarray):
    """A map to 0-1 for a column whose range is an intensity's, else None (a time
    stamp, an index): 0-1 as is, -2048..2047 (PTS), 0-255, 0-65535."""
    lo, hi = float(np.min(v)), float(np.max(v))
    if lo >= 0.0 and hi <= 1.0:
        return lambda x: x
    if lo >= -2048 and hi <= 2047 and lo < 0:
        return lambda x: (x + 2048.0) / 4095.0
    if lo >= 0 and hi <= 255:
        return lambda x: x / 255.0
    if lo >= 0 and hi <= 65535 and np.all(v == np.round(v)):
        return lambda x: x / 65535.0
    return None


def _ascii_attributes(arr: np.ndarray, keep_time: bool):
    """(colour columns, intensity column, intensity scale) of an ASCII cloud, from
    its first rows: x y z [i] r g b, or x y z r g b [i | t]."""
    ncol = arr.shape[1]
    rgb = icol = None
    if ncol >= 6 and _is_rgb(arr[:, -3:]):  # PTS order first: x y z i r g b reads both ways
        rgb, icol = slice(ncol - 3, ncol), (3 if ncol >= 7 else None)
    elif ncol >= 6 and _is_rgb(arr[:, 3:6]):
        rgb, icol = slice(3, 6), (6 if ncol >= 7 else None)
    # x y z v alone is not read: v may be a time stamp that looks like an intensity (TUB1)
    if icol is not None and keep_time and icol == ncol - 1:
        icol = None  # the last column is the time stamp
    scale = _intensity_scale(arr[:, icol]) if icol is not None else None
    return rgb, (icol if scale is not None else None), scale


def _load_ascii(path: Path, voxel: float = 0.0, chunk_bytes: int = 64 << 20, keep_time: bool = False) -> Cloud:
    """Stream an ASCII cloud (x y z [more columns]) in 64 MB pieces, reducing to
    voxel centroids as it goes. Colour is three 0-255 integer columns in every row
    of the first piece, either the last three (x y z [i] r g b, as PTS) or right
    after xyz (x y z r g b [i|t]); intensity is the column on the other side of
    the colour, when its range is an intensity's (see _intensity_scale). Other
    columns are ignored. With `keep_time` the last column is time, never intensity."""
    import io

    skip, delim, ncol = _ascii_layout(path)
    acc = VoxelAccumulator(voxel, compact_at=20_000_000) if voxel > 0 else None
    parts: list[dict[str, np.ndarray]] = []
    n_input = n_bad = 0
    layout = None  # (colour columns or None, intensity column or None, intensity scale)
    with open(path, "rb") as fh:
        for _ in range(skip):
            fh.readline()
        tail = b""
        while True:
            block = fh.read(chunk_bytes)
            eof = not block
            data = tail + block
            if eof:
                body, tail = data, b""
            else:
                cut = data.rfind(b"\n") + 1
                if cut == 0:  # no complete line yet
                    tail = data
                    continue
                body, tail = data[:cut], data[cut:]
            if body.strip():
                try:
                    arr = np.loadtxt(
                        io.BytesIO(body), delimiter=delim, usecols=range(ncol), ndmin=2, dtype=np.float64, comments="#"
                    )
                except ValueError:
                    if not eof:
                        raise
                    # an incomplete last line: keep every complete one, count the rest
                    lines = body.rstrip().splitlines()
                    arr = np.loadtxt(
                        io.BytesIO(b"\n".join(lines[:-1])),
                        delimiter=delim,
                        usecols=range(ncol),
                        ndmin=2,
                        dtype=np.float64,
                        comments="#",
                    )
                    n_bad += 1
                n_input += len(arr)
                ok = np.isfinite(arr[:, :3]).all(1)
                n_bad += int((~ok).sum())
                arr = arr[ok]
                if layout is None and len(arr):
                    layout = _ascii_attributes(arr, keep_time)
                cols = {"points": arr[:, :3]}
                if layout and layout[0] is not None:
                    cols["colours"] = arr[:, layout[0]] / 255.0
                if layout and layout[1] is not None:
                    cols["intensity"] = np.clip(layout[2](arr[:, layout[1]]), 0.0, 1.0)
                if keep_time:
                    if ncol < 4:
                        raise ValueError(f"{path.name}: a trajectory needs a time column; the file has {ncol}")
                    cols["time"] = arr[:, -1]
                if acc is not None:
                    acc.add(cols)
                else:
                    parts.append(cols)
            if eof:
                break
    if acc is not None:
        cols = acc.result()
    elif parts:
        cols = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    else:
        cols = {"points": np.empty((0, 3))}
    if len(cols["points"]) == 0:
        raise ValueError(f"{path.name}: no valid points")
    return Cloud(
        points=cols["points"],
        colours=cols.get("colours"),
        intensity=cols.get("intensity"),
        hits=cols.get("hits"),
        times=cols.get("time"),
        n_input=n_input,
        n_dropped=n_bad,
    )


def _quat_matrix(q: np.ndarray) -> np.ndarray:
    """Rotation matrix of an E57 quaternion (w, x, y, z)."""
    w, x, y, z = q / np.linalg.norm(q)
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def _limits(header, group: str, names: tuple[str, ...]) -> tuple[float, float] | None:
    """(min, max) of a colour or intensity field from the scan header, if declared."""
    try:
        node = header.node[group]
        lo = min(float(node[f"{n}Minimum"].value()) for n in names)
        hi = max(float(node[f"{n}Maximum"].value()) for n in names)
        return (lo, hi) if hi > lo else None
    except Exception:  # noqa: BLE001 - optional header block, any failure means "not declared"
        return None


def _unit(values: np.ndarray, limits: tuple[float, float] | None) -> np.ndarray:
    """Scale to 0-1 by the declared limits, else by 255 for byte-ranged data."""
    if limits is not None:
        lo, hi = limits
    else:
        lo, hi = 0.0, (255.0 if values.size and values.max() > 1.0 else 1.0)
    return np.clip((values - lo) / (hi - lo), 0.0, 1.0)


def _e57_chunks(scan, index: int, header, size: int, colour: bool = False, intensity: bool = False):
    """(raw count, columns) for one E57 scan, `size` points at a time. Invalid
    and non-finite returns are dropped; the raw count includes them."""
    fields = list(_XYZ)
    has_invalid = "cartesianInvalidState" in header.point_fields
    if has_invalid:
        fields.append("cartesianInvalidState")
    if colour:
        fields += _RGB
        rgb_lim = _limits(header, "colorLimits", ("colorRed", "colorGreen", "colorBlue"))
    if intensity:
        fields.append("intensity")
        int_lim = _limits(header, "intensityLimits", ("intensity",))
    data, buffers = scan.make_buffers(fields, size)
    reader = scan.data3d[index]["points"].reader(buffers)
    try:
        read = 0
        while read < header.point_count:
            n = reader.read()
            if n == 0:
                break
            read += n
            xyz = np.c_[data["cartesianX"][:n], data["cartesianY"][:n], data["cartesianZ"][:n]].astype(np.float64)
            ok = np.isfinite(xyz).all(1)
            if has_invalid:
                ok &= data["cartesianInvalidState"][:n] == 0
            cols = {"points": xyz[ok]}
            if colour:
                rgb = np.c_[data["colorRed"][:n], data["colorGreen"][:n], data["colorBlue"][:n]].astype(np.float64)
                cols["colours"] = _unit(rgb[ok], rgb_lim)
            if intensity:
                cols["intensity"] = _unit(np.asarray(data["intensity"][:n], dtype=np.float64)[ok], int_lim)
            yield n, cols
    finally:
        reader.close()


# ------------------------------------------------------------------ voxel centroids

_BIAS = 1 << 20  # 21 bits per axis in one int64 key


class VoxelAccumulator:
    """Voxel centroids over a stream of chunks.

    Cells are aligned to multiples of `voxel` from the origin, so every chunk,
    every reader and every run agree on cell boundaries. Each kept point is the
    mean of its cell's returns (no first-arrival bias between scans or chunks);
    colour and intensity are averaged too; `firsts` columns (normals, whose sign
    is arbitrary and would cancel) keep the earliest value. `hits` counts the
    returns behind each point. Memory is bounded by the kept set: parts are
    merged when they pass `compact_at` or twice the last merged size.
    """

    FIRSTS = (
        "normals",
        "scan",
        "time",
    )  # a voxel's scan: the earliest that saw it — any observer is a true line of sight

    def __init__(self, voxel: float, compact_at: int = 20_000_000):
        if voxel <= 0:
            raise ValueError("voxel must be positive")
        self.voxel = voxel
        self.compact_at = compact_at
        self.base: np.ndarray | None = None
        self.parts: list[tuple] = []
        self.size = 0
        self.last = 0

    def _keys(self, points: np.ndarray) -> np.ndarray:
        ijk = np.floor(points / self.voxel).astype(np.int64)
        if self.base is None:
            self.base = ijk.min(0) if len(ijk) else np.zeros(3, np.int64)
        rel = ijk  # shifted in place: no second N x 3 int64 array (2026-11-04)
        rel -= self.base
        rel += _BIAS
        if len(rel) and (rel.min() < 0 or rel.max() >= 2 * _BIAS):
            span = 2 * _BIAS * self.voxel / 1000
            raise ValueError(
                f"the cloud spans more than {span:.0f} km at a {self.voxel * 1000:g} mm voxel; "
                "re-centre it or use a coarser --decimate"
            )
        return (rel[:, 0] << 42) | (rel[:, 1] << 21) | rel[:, 2]

    def add(self, cols: dict[str, np.ndarray], hits: np.ndarray | None = None) -> None:
        if len(cols["points"]) == 0:
            return
        keys = self._keys(cols["points"])
        counts = np.ones(len(keys), np.int64) if hits is None else hits.astype(np.int64)
        # rows that are already centroids (hits > 1) weigh by their returns, so a
        # re-thinned cloud stays where it was (review 2026-11-01: they were summed
        # unweighted and divided by the summed hits, pulling them toward the origin)
        w = None if hits is None else counts.astype(np.float64)
        sums = {
            k: (v if w is None else v * (w if v.ndim == 1 else w[:, None]))
            for k, v in cols.items()
            if k not in self.FIRSTS
        }
        firsts = {k: v for k, v in cols.items() if k in self.FIRSTS}
        part = _reduce(keys, sums, firsts, counts)
        del keys, counts, w, sums, firsts
        self.parts.append(part)
        self.size += len(part[0])
        if self.size > max(self.compact_at, 2 * self.last):
            self._compact()

    def _compact(self) -> None:
        if len(self.parts) > 1:
            # Merged one column at a time, each part's copy dropped once it is joined:
            # joining every column first held a second copy of the whole kept set and
            # set the reader's peak (2026-11-04, tools/profile_memory.py: Anoeta's LAZ
            # peaked at 7.26 GiB here; Astra's cloud run measured 826 -> 681 MiB on 2 M points).
            parts, self.parts = self.parts, []
            keys = np.concatenate([p[0] for p in parts])
            counts = np.concatenate([p[3] for p in parts])
            self.parts = [_reduce(keys, _Joined(parts, 1), _Joined(parts, 2), counts)]
            del parts, keys, counts
        self.size = self.last = len(self.parts[0][0]) if self.parts else 0

    def result(self) -> dict[str, np.ndarray]:
        self._compact()
        if not self.parts:
            return {"points": np.empty((0, 3))}
        _, sums, firsts, counts = self.parts.pop()
        out = {}
        for k in list(sums):
            v = sums.pop(k)
            v /= counts[:, None] if v.ndim == 2 else counts  # in place: the sums are ours
            out[k] = v
        out.update(firsts)
        out["hits"] = counts
        self.size = self.last = 0
        return out


class _Joined:
    """One kind of column (`idx` 1 sums, 2 firsts) of several parts, joined on demand,
    one column at a time, each part's copy released as soon as it is joined."""

    def __init__(self, parts: list[tuple], idx: int):
        self.parts, self.idx = parts, idx

    def items(self):
        for name in list(self.parts[0][self.idx]):
            v = np.concatenate([p[self.idx][name] for p in self.parts])
            for p in self.parts:
                del p[self.idx][name]
            yield name, v
            del v


def _reduce(keys, sums, firsts, counts):
    """Merge rows sharing a key: sum `sums` and `counts`, keep the earliest `firsts`.
    `sums`/`firsts` are anything with `.items()`; each column is taken and reduced in
    turn, so at most one is reordered at a time."""
    order = np.argsort(keys, kind="stable")
    k = keys[order]
    starts = np.flatnonzero(np.r_[True, k[1:] != k[:-1]])
    out_k = k[starts]
    del k
    out_s = {}
    for n, v in sums.items():
        out_s[n] = np.add.reduceat(v[order], starts, axis=0)
        del v
    first = order[starts]
    out_f = {n: v[first] for n, v in firsts.items()}
    return out_k, out_s, out_f, np.add.reduceat(counts[order], starts)


def _load_ptx(path: Path) -> Cloud:
    """PTX: `cols rows`, `cols rows` of scanner position, then a 4x4 pose, then points.

    Repeated per station. The pose maps scanner-local to project coordinates, and
    ignoring it is how multi-station PTX files end up stacked on top of each other.
    """
    blocks = []
    with open(path, "r", encoding="ascii", errors="replace") as fh:
        while True:
            header = fh.readline()
            while header and not header.strip():
                header = fh.readline()
            if not header:
                break
            try:
                cols, rows = (int(v) for v in header.split()[:2])
            except ValueError:
                break
            fh.readline()  # scanner origin, unprojected
            pose = np.array([[float(v) for v in fh.readline().split()[:4]] for _ in range(4)])
            raw = np.loadtxt(fh, max_rows=cols * rows, usecols=(0, 1, 2), ndmin=2)
            if raw.shape[0] < cols * rows:
                raw = np.vstack([raw, np.full((cols * rows - raw.shape[0], 3), np.nan)])
            xyz = raw.reshape(-1, 3)
            xyz = xyz[np.isfinite(xyz).all(1) & (np.abs(xyz).sum(1) > 0)]
            blocks.append(xyz @ pose[:3, :3].T + pose[:3, 3])
    if not blocks:
        raise ValueError(f"{path.name}: no PTX stations parsed")
    return Cloud(points=np.concatenate(blocks).astype(np.float64))


def _load_las(path: Path, voxel: float = 0.0, keep_time: bool = False, chunk_size: int = 5_000_000) -> Cloud:
    """Stream a LAS/LAZ in chunks, reducing to voxel centroids as it goes (as the E57
    reader does), so a 585 M-point file never sits in memory at full density.
    Colour is carried when the point format has it; intensity when any point has a
    non-zero value (Grainger's LAS stores all zeros, which means "not recorded")."""
    try:
        import laspy  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on the machine
        raise RuntimeError("LAS/LAZ input needs the optional 'laspy' package: pip install laspy") from exc

    acc = VoxelAccumulator(voxel, compact_at=4 * chunk_size) if voxel > 0 else None
    parts: list[dict[str, np.ndarray]] = []
    n_input = 0
    any_intensity = False
    with laspy.open(str(path)) as fh:
        dims = set(fh.header.point_format.dimension_names)
        colour = {"red", "green", "blue"} <= dims
        has_time = keep_time and "gps_time" in dims
        for ch in fh.chunk_iterator(chunk_size):
            n_input += len(ch)
            cols = {
                "points": np.c_[np.asarray(ch.x), np.asarray(ch.y), np.asarray(ch.z)].astype(np.float64, copy=False)
            }
            if colour:
                rgb = np.c_[ch.red, ch.green, ch.blue].astype(np.float64)
                rgb /= 65535.0
                cols["colours"] = rgb
            if "intensity" in dims:
                inten = np.asarray(ch.intensity, dtype=np.float64) / 65535.0
                any_intensity |= bool(inten.max(initial=0.0) > 0.0)
                cols["intensity"] = inten
            if has_time:
                cols["time"] = np.asarray(ch.gps_time, dtype=np.float64)  # for a trajectory (round 11)
            if acc is not None:
                acc.add(cols)
            else:
                parts.append(cols)
    if acc is not None:
        cols = acc.result()
    elif parts:
        cols = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    else:
        cols = {"points": np.empty((0, 3))}
    if len(cols["points"]) == 0:
        raise ValueError(f"{path.name}: no points in the LAS file")
    return Cloud(
        points=cols["points"],
        colours=cols.get("colours"),
        intensity=cols.get("intensity") if any_intensity else None,
        hits=cols.get("hits"),
        times=cols.get("time"),
        n_input=n_input,
    )


# ----------------------------------------------------------------------- cleaning


def decimate(cloud: Cloud, voxel: float) -> Cloud:
    """Voxel centroids at `voxel` metres, on the same origin-aligned grid the E57
    reader uses, so every input path keeps the same cells (design §4.1)."""
    if len(cloud) == 0:
        return cloud
    if cloud.scan_index is not None and len(np.unique(cloud.scan_index)) > 1:
        # multi-scan: thinned per scan, so every centroid keeps its one scanner
        # (round 11: a merged centroid of two scans has none)
        parts = []
        for k in np.unique(cloud.scan_index):
            part = cloud.take(cloud.scan_index == k)
            part.scan_index = None
            part = decimate(part, voxel)
            part.scan_index = np.full(len(part), k, np.int64)
            parts.append(part)
        out = cloud.take(np.arange(0))
        for name in ("points", "normals", "colours", "intensity", "hits", "scan_index", "times"):
            vals = [getattr(p, name) for p in parts]
            setattr(out, name, None if any(v is None for v in vals) else np.concatenate(vals))
        return out
    acc = VoxelAccumulator(voxel, compact_at=max(len(cloud), 1))
    cols = {"points": cloud.points}
    for name in ("normals", "colours", "intensity"):
        if getattr(cloud, name) is not None:
            cols[name] = getattr(cloud, name)
    if cloud.times is not None:
        cols["time"] = cloud.times  # the cell's first time (FIRSTS), as the ASCII reader keeps it
    acc.add(cols, hits=cloud.hits)
    out = acc.result()
    kept = cloud.take(np.arange(0))  # carries provenance and station fields
    kept.points = out["points"]
    kept.normals = out.get("normals")
    kept.colours = out.get("colours")
    kept.intensity = out.get("intensity")
    kept.hits = out["hits"]
    kept.times = out.get("time")
    # one scan (or none): every centroid keeps it; take(0) left these empty (R11-1)
    kept.scan_index = None if cloud.scan_index is None else np.full(len(kept.points), cloud.scan_index[0], np.int64)
    return kept


def voxel_trim(cloud: Cloud, cfg: Config = Config(), in_place: bool = False) -> Cloud:
    """Drop returns from cells too sparse to be a surface.

    This is not noise removal for its own sake: 2,150 stray points in the sample
    scan are enough to seed a fake face if a projection bin happens to collect
    them. It runs before normals, because a normal estimated from noise is worse
    than no normal.

    `in_place` trims `cloud` itself, one array at a time, instead of returning a
    trimmed copy: a copy holds the whole cloud twice.
    """
    if len(cloud) == 0:
        return cloud
    lo = cloud.points.min(0)
    # one temporary N x 3 array, worked in place (2026-11-04: the chained form held four)
    idx = cloud.points - lo
    idx /= cfg.voxel_cell
    np.floor(idx, out=idx)
    idx = idx.astype(np.int64)
    span = idx.max(0) + 1
    key = (idx[:, 0] * span[1] + idx[:, 1]) * span[2] + idx[:, 2]  # one int64 per cell: fast unique
    del idx
    _, inv, counts = np.unique(key, return_inverse=True, return_counts=True)
    del key
    keep = counts[inv.reshape(-1)] >= cfg.voxel_min_points
    del inv, counts
    dropped = int((~keep).sum())
    if in_place:
        if dropped:
            cloud.keep_only(keep)
        cloud.n_dropped += dropped
        return cloud
    out = cloud.take(keep)
    out.n_dropped = cloud.n_dropped + dropped
    return out


def estimate_normals(cloud: Cloud, radius: float = 0.10, max_nn: int = 30) -> None:
    """Unit normals by local PCA. Sign is arbitrary; stage 1 only uses |n·u|."""
    import open3d as o3d

    pts = cloud.points
    # Round 24b: on map coordinates (UTM northing 8.7e6 m) Open3D's normals snap to
    # 0/45/90/135 deg - its PCA loses the precision - and every wall direction is
    # wrong (Longyearbyen, Anoeta, Jolastokieta). Normals do not depend on where the
    # cloud sits, so far from the origin they are taken on a shifted copy.
    if len(pts) and float(np.abs(pts).max()) > 1000.0:
        pts = pts - np.floor(pts.min(0))
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(pts)
    pcd.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=radius, max_nn=max_nn))
    cloud.normals = np.asarray(pcd.normals, dtype=np.float64)


def _ground_below(p: np.ndarray, xy: np.ndarray, z: float, ring: float = 1.5) -> float | None:
    near = (np.hypot(p[:, 0] - xy[0], p[:, 1] - xy[1]) < ring) & (p[:, 2] < z)
    if near.sum() < 100:
        return None
    return z - float(np.percentile(p[near, 2], 2.0))


def _check_station(cloud: Cloud, s: np.ndarray, height: tuple[float, float]) -> tuple[bool, str]:
    """Plausibility of a scanner position: inside the cloud, ground one instrument
    height below. A plausibility test only — any point at standing height in a
    room passes it."""
    lo, hi = cloud.bounds
    if not bool(np.all(lo <= s) and np.all(s <= hi)):
        return False, "outside the cloud"
    ground = _ground_below(cloud.points, s[:2], float(s[2]))
    if ground is None:
        return False, "no ground below it"
    if not height[0] <= ground <= height[1]:
        return False, f"ground {ground:.2f} m below is not an instrument height"
    return True, f"inside the cloud, ground {ground:.2f} m below"


def _xyz(s: np.ndarray) -> str:
    return "(" + ", ".join(f"{float(v):.3f}" for v in s) + ")"


def establish_station(
    cloud: Cloud,
    given: tuple[float, float, float] | None = None,
    height: tuple[float, float] = (1.0, 2.2),
    force: bool = False,
    conflict_m: float = 0.5,
    pose_height: tuple[float, float] = (0.2, 6.0),
) -> None:
    """Where the scanner stood: from `--station` or the file. Never inferred.

    Facing, body side, envelope and pairing all hang on this point, and an origin
    that merely *looks* like a station (a cloud re-centred on its middle passes any
    geometric test) would invert every one of them silently. Rules (design §4.2
    step 5), every candidate checked by `_check_station`:

    - `--station` that passes is used; it overrides a file station, and a
      disagreement over `conflict_m` is recorded.
    - `--station` that fails is not used (the file station, if it passes, is used
      instead) unless `force`, when it is used and marked FAILED.
    - A file station is a hint: used only if it passes, rejected otherwise. The
      sample E57's pose translation is a project offset 5 m outside the cloud.
    - Nothing usable: the station is unknown, and the origin is checked as a hint.

    The decision is kept structured in `cloud.station_info` and rendered once
    into `cloud.station_source`.
    """
    if len(cloud) == 0:
        return
    if len(cloud.scan_stations) > 1 or (cloud.scan_stations and cloud.file_station_kind.startswith("multi-scan npz")):
        _establish_per_scan(cloud, given, pose_height)
        return
    if cloud.file_station_kind.startswith("trajectory"):
        _establish_trajectory(cloud, given)
        return
    notes: list[str] = []
    fs, kind = cloud.file_station, cloud.file_station_kind
    file_ok, file_check = _check_station(cloud, fs, height) if fs is not None else (False, None)
    if fs is not None and not file_ok:
        notes.append(f"file station ({kind}) {_xyz(fs)} rejected: {file_check}")
    elif fs is None and kind.startswith("multi-scan"):
        notes.append(f"{kind}: the file offers no per-scan stations")

    g = None if given is None else np.asarray(given, dtype=np.float64).reshape(3)
    given_ok, given_check = _check_station(cloud, g, height) if g is not None else (False, None)

    if g is not None and (given_ok or force):
        station, used, check, ok = g, "user", given_check, given_ok
        if not given_ok:
            notes.append("used anyway because of --station-force")
        if file_ok and float(np.linalg.norm(g - fs)) > conflict_m:
            notes.append(f"overrides the file station ({kind}) {_xyz(fs)}, {float(np.linalg.norm(g - fs)):.2f} m away")
    elif file_ok:
        station, used, check, ok = fs, "file", file_check, True
        if g is not None:
            notes.append(f"--station {_xyz(g)} not used: {given_check}; pass --station-force to use it")
    else:
        station, used, check, ok = None, "none", None, False
        if g is not None:
            notes.append(f"--station {_xyz(g)} not used: {given_check}; pass --station-force to use it")
        origin_ok, origin_check = _check_station(cloud, np.zeros(3), height)
        notes.append(
            f"the origin is {origin_check}"
            + (" — pass --station 0,0,0 if the file is in the scanner's own frame" if origin_ok else "")
        )

    cloud.station = station
    cloud.station_info = {
        "used": used,
        "station": None if station is None else [round(float(v), 3) for v in station],
        "check": check,
        "check_passed": ok,
        "file_station": None if fs is None else [round(float(v), 3) for v in fs],
        "file_kind": kind or None,
        "file_check": file_check,
        "given": None if g is None else [round(float(v), 3) for v in g],
        "given_check": given_check,
        "notes": notes,
    }
    head = {
        "user": "user (--station)",
        "file": f"file ({kind})",
        "none": "unknown",
    }[used]
    if check is not None:
        head += f"; check: {check}" + ("" if ok else " — FAILED")
    cloud.station_source = "; ".join([head, *notes])
    if station is not None:
        cloud.stations = station.reshape(1, 3)
        cloud.scan_index = None


def _establish_trajectory(cloud: Cloud, given, margin: float = 1.0, min_inside: float = 0.9) -> None:
    """A sensor path is used when it runs inside the cloud: at least 90 % of its
    stations within the cloud's plan extent (+1 m). A path in another frame fails
    that and is dropped whole."""
    lo, hi = cloud.bounds
    st = cloud.stations
    inside = float(np.mean(np.all((st[:, :2] >= lo[:2] - margin) & (st[:, :2] <= hi[:2] + margin), axis=1)))
    notes = []
    if given is not None:
        notes.append("--station ignored: the trajectory gives each point its own scanner")
    covered = float(np.mean(cloud.scan_index >= 0)) if cloud.scan_index is not None else 0.0
    ok = inside >= min_inside and covered > 0
    if not ok:
        notes.append(
            f"trajectory rejected: {inside:.0%} of its stations inside the cloud, "
            f"{covered:.0%} of points timed within it"
        )
        cloud.stations, cloud.scan_index = None, None
    cloud.station = None
    cloud.station_info = {
        "used": "trajectory" if ok else "none",
        "kind": cloud.file_station_kind,
        "stations": 0 if st is None else len(st),
        "stations_inside": round(inside, 3),
        "points_with_station": round(covered, 3),
        "heights_trusted": False,
        "notes": notes,
    }
    head = f"{cloud.file_station_kind}: {covered:.0%} of points timed on it" if ok else "unknown"
    cloud.station_source = "; ".join([head, *notes])


def _establish_per_scan(cloud: Cloud, given, height: tuple[float, float]) -> None:
    """A registered multi-scan file: one station per scan, each checked on its own.

    A scan whose station fails keeps its points but gives no evidence: its points
    get no scanner, so they decide no facing and cast no rays. `--station` names
    one point and cannot stand for several scanners, so it is not applied here.
    """
    rows, scans, notes = [], [], []
    for i, (xyz, kind) in enumerate(cloud.scan_stations):
        if xyz is None:
            ok, check = False, "no station offered"
        else:
            ok, check = _check_station(cloud, np.asarray(xyz, dtype=np.float64), height)
        rows.append(np.asarray(xyz, dtype=np.float64) if ok else np.full(3, np.nan))
        scans.append(
            {
                "scan": i,
                "kind": kind,
                "offered": None if xyz is None else [round(float(v), 3) for v in xyz],
                "check": check,
                "check_passed": ok,
            }
        )
        if not ok:
            notes.append(f"scan {i} ({kind}) has no usable station: {check}")
    if given is not None:
        notes.append("--station ignored: a multi-scan file uses one station per scan")
    cloud.stations = np.array(rows)
    valid = int(np.isfinite(cloud.stations).all(1).sum())
    cloud.station = None
    if valid == 1:
        cloud.station = cloud.stations[np.isfinite(cloud.stations).all(1)][0]
    n = len(rows)
    covered = 0.0
    if cloud.scan_index is not None and len(cloud):
        ok_rows = np.isfinite(cloud.stations).all(1)
        covered = float((ok_rows[np.clip(cloud.scan_index, 0, n - 1)] & (cloud.scan_index >= 0)).mean())
    cloud.station_info = {
        "used": "per-scan" if valid else "none",
        "scans": scans,
        "valid": valid,
        "points_with_station": round(covered, 3),
        "notes": notes,
    }
    head = f"per scan ({cloud.file_station_kind}): {valid} of {n} stations pass" if valid else "unknown"
    cloud.station_source = "; ".join([head + f", {covered:.0%} of points covered", *notes])


def validate(cloud: Cloud) -> list[str]:
    """Stage 0's rejection tests. Returns reasons; empty means the cloud is usable."""
    reasons: list[str] = []
    if len(cloud) < 1000:
        reasons.append(f"only {len(cloud):,} points")
    if cloud.normals is None:
        reasons.append("no normals")
    elif not np.isfinite(cloud.normals).all():
        reasons.append("non-finite normals")

    lo, hi = cloud.bounds
    extent = hi - lo
    if not np.isfinite(extent).all():
        reasons.append("non-finite coordinates")
        return reasons
    if extent.max() > 1000:
        reasons.append(f"extent {extent.max():.0f} m — probably millimetres, not metres")
    if extent[2] < 1.0:
        reasons.append(f"height {extent[2]:.2f} m — no storey in the cloud")
    # A registered multi-station cloud fills its volume; a single unregistered
    # station leaves one corner empty. This is a warning, not a rejection.
    return reasons
