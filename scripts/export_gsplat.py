#!/usr/bin/env python3
"""
export_gsplat.py
Optimized 3D Gaussian Splatting exporter and compressor powered by gsplat.

Features:
- Converts uncompressed 3DGS PLY files into ultra-compact streamable .splat files (up to 8x smaller).
- Prunes invisible/degenerate splats (alpha thresholding) to eliminate floaters and boost viewport FPS.
- Culls extreme outlier splats to keep bounding boxes tight and centered.
- Exports both pristine .ply and instant-streaming .splat formats.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import torch

try:
    import gsplat
except ImportError:
    gsplat = None

try:
    from plyfile import PlyData, PlyElement
except ImportError:
    PlyData = None


def parse_ply_to_tensors(ply_path: Path) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    """Parse a Gaussian Splat PLY file into PyTorch tensors."""
    if PlyData is None:
        raise RuntimeError("plyfile is required: pip install plyfile")

    ply = PlyData.read(str(ply_path))
    v = ply["vertex"]

    means = torch.from_numpy(np.stack([v["x"], v["y"], v["z"]], axis=-1).astype(np.float32))

    # Scale: Nerfstudio & Inria store as log(scale)
    if "scale_0" in v:
        scales = torch.from_numpy(np.stack([v["scale_0"], v["scale_1"], v["scale_2"]], axis=-1).astype(np.float32))
        # If mean scale is <= 0, it's stored in log space -> exponentiate
        if scales.mean() < 2.0:
            scales = torch.exp(scales)
    else:
        scales = torch.full_like(means, 0.05)

    # Rotation quaternions [w, x, y, z]
    if "rot_0" in v:
        quats = torch.from_numpy(np.stack([v["rot_0"], v["rot_1"], v["rot_2"], v["rot_3"]], axis=-1).astype(np.float32))
        quats = quats / torch.clamp(torch.norm(quats, dim=-1, keepdim=True), min=1e-8)
    else:
        quats = torch.tensor([[1.0, 0.0, 0.0, 0.0]], dtype=torch.float32).repeat(len(means), 1)

    # Opacity: stored as logit(opacity) or linear opacity
    if "opacity" in v:
        raw_opac = torch.from_numpy(v["opacity"].astype(np.float32))
        # If any values outside [0, 1] or mean < 0, it's logits
        if raw_opac.min() < 0.0 or raw_opac.max() > 1.0:
            opacities = torch.sigmoid(raw_opac)
        else:
            opacities = torch.clamp(raw_opac, 0.0, 1.0)
    else:
        opacities = torch.ones((len(means),), dtype=torch.float32)

    # SH0 (Base RGB color)
    if "f_dc_0" in v:
        sh0 = torch.from_numpy(np.stack([v["f_dc_0"], v["f_dc_1"], v["f_dc_2"]], axis=-1).astype(np.float32)).unsqueeze(1)
    elif "red" in v and "green" in v and "blue" in v:
        # Vertex colors [0..255] converted to SH0
        r = v["red"].astype(np.float32) / 255.0
        g = v["green"].astype(np.float32) / 255.0
        b = v["blue"].astype(np.float32) / 255.0
        rgb = np.stack([r, g, b], axis=-1)
        # Convert RGB to SH0 (approx C0 = 0.28209479177387814)
        c0 = 0.28209479177387814
        sh0_np = (rgb - 0.5) / c0
        sh0 = torch.from_numpy(sh0_np).unsqueeze(1)
    else:
        sh0 = torch.zeros((len(means), 1, 3), dtype=torch.float32)

    # Higher degree Spherical Harmonics
    sh_names = sorted([p.name for p in v.properties if p.name.startswith("f_rest_")], key=lambda x: int(x.split("_")[-1]))
    if sh_names:
        shN = torch.from_numpy(np.stack([v[name] for name in sh_names], axis=-1).astype(np.float32)).reshape(len(means), -1, 3)
    else:
        shN = torch.zeros((len(means), 0, 3), dtype=torch.float32)

    return means, scales, quats, opacities, sh0, shN


def optimize_and_export(
    input_ply: Path,
    output_dir: Path,
    alpha_threshold: float = 0.01,
    max_scale: float = 2.0,
    export_formats: Tuple[str, ...] = ("splat", "ply"),
) -> dict:
    """Filter floaters, prune low-opacity splats, and export optimized assets."""
    if gsplat is None:
        raise RuntimeError("gsplat is required: pip install gsplat")

    output_dir.mkdir(parents=True, exist_ok=True)
    means, scales, quats, opacities, sh0, shN = parse_ply_to_tensors(input_ply)
    initial_count = len(means)

    # 1. Filter: alpha culling (removes invisible splats)
    valid_mask = opacities >= alpha_threshold

    # 2. Filter: scale culling (removes giant camera-covering floaters)
    max_dim_scale = torch.max(scales, dim=-1)[0]
    valid_mask &= max_dim_scale <= max_scale

    # 3. Filter: NaN / Inf checks
    finite_mask = torch.isfinite(means).all(dim=-1) & torch.isfinite(scales).all(dim=-1)
    valid_mask &= finite_mask

    means = means[valid_mask]
    scales = scales[valid_mask]
    quats = quats[valid_mask]
    opacities = opacities[valid_mask]
    sh0 = sh0[valid_mask]
    if shN.shape[1] > 0:
        shN = shN[valid_mask]
    else:
        shN = torch.zeros((len(means), 0, 3), dtype=torch.float32)

    final_count = len(means)
    results = {
        "initial_splats": initial_count,
        "final_splats": final_count,
        "pruned_splats": initial_count - final_count,
        "pruned_percent": round((1.0 - final_count / max(1, initial_count)) * 100, 1),
        "files": {},
    }

    # Export formats
    if "splat" in export_formats:
        splat_out = output_dir / "scene.splat"
        splat_bytes = gsplat.export_splats(means, scales, quats, opacities, sh0, shN, format="splat")
        splat_out.write_bytes(splat_bytes)
        size_mb = round(len(splat_bytes) / (1024 * 1024), 2)
        results["files"]["splat"] = {"path": str(splat_out), "size_mb": size_mb}

    if "ply" in export_formats:
        ply_out = output_dir / "splat.ply"
        ply_bytes = gsplat.export_splats(means, scales, quats, opacities, sh0, shN, format="ply")
        ply_out.write_bytes(ply_bytes)
        size_mb = round(len(ply_bytes) / (1024 * 1024), 2)
        results["files"]["ply"] = {"path": str(ply_out), "size_mb": size_mb}

    return results


def main():
    parser = argparse.ArgumentParser(description="Export & compress 3D Gaussian Splats via gsplat")
    parser.add_argument("--input", "-i", type=Path, required=True, help="Path to input 3DGS .ply file")
    parser.add_argument("--output-dir", "-o", type=Path, default=None, help="Output directory (defaults to input's dir)")
    parser.add_argument("--alpha-thresh", type=float, default=0.01, help="Minimum opacity threshold (default: 0.01)")
    parser.add_argument("--max-scale", type=float, default=2.0, help="Maximum allowed splat scale (default: 2.0)")
    parser.add_argument("--format", choices=["splat", "ply", "all"], default="all", help="Output format")

    args = parser.parse_args()
    input_ply = args.input
    if not input_ply.exists():
        print(f"Error: input file {input_ply} does not exist", file=sys.stderr)
        sys.exit(1)

    out_dir = args.output_dir or input_ply.parent
    formats = ("splat", "ply") if args.format == "all" else (args.format,)

    print(f"Reading and optimizing {input_ply}...")
    res = optimize_and_export(input_ply, out_dir, args.alpha_thresh, args.max_scale, formats)
    print(f"Done! Splat count: {res['initial_splats']:,} -> {res['final_splats']:,} ({res['pruned_percent']}% pruned)")
    for fmt, info in res["files"].items():
        print(f"  [{fmt.upper()}] {info['path']} ({info['size_mb']} MB)")


if __name__ == "__main__":
    main()
