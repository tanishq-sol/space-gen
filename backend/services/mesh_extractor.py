#!/usr/bin/env python3
"""
mesh_extractor.py
Converts 3D Gaussian Splatting point clouds (.ply / .splat) into solid polygon meshes (.glb)
and partitions them into independent semantic objects (bed, sofa, room_shell) for 6-DOF manipulation.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import open3d as o3d
from plyfile import PlyData
import trimesh


def extract_points_and_colors_from_ply(ply_path: Path, max_sample_points: int = 120000) -> Tuple[np.ndarray, np.ndarray]:
    """Load Gaussian Splat means and convert base colors from spherical harmonics or vertex colors."""
    ply = PlyData.read(str(ply_path))
    v = ply["vertex"]

    total_pts = len(v)
    if total_pts == 0:
        raise ValueError("PLY file contains 0 vertices.")

    # Subsample if massive (for fast reconstruction)
    if total_pts > max_sample_points:
        indices = np.random.choice(total_pts, max_sample_points, replace=False)
    else:
        indices = np.arange(total_pts)

    pts = np.stack([v["x"][indices], v["y"][indices], v["z"][indices]], axis=-1).astype(np.float64)

    # Extract RGB colors
    if "f_dc_0" in v:
        f_dc = np.stack([v["f_dc_0"][indices], v["f_dc_1"][indices], v["f_dc_2"][indices]], axis=-1)
        # Convert SH degree 0 to RGB [0..1]
        c0 = 0.28209479177387814
        colors = np.clip(0.5 + c0 * f_dc, 0.0, 1.0).astype(np.float64)
    elif "red" in v and "green" in v and "blue" in v:
        colors = (np.stack([v["red"][indices], v["green"][indices], v["blue"][indices]], axis=-1) / 255.0).astype(np.float64)
    else:
        colors = np.full((len(pts), 3), 0.7, dtype=np.float64)

    return pts, colors


def convert_splat_to_mesh(
    ply_path: Path,
    output_dir: Path,
    scene_objects: Optional[List[Dict[str, Any]]] = None,
    depth: int = 8,
    max_triangles: int = 150000,
) -> Dict[str, Any]:
    """
    Run Poisson surface reconstruction on splat points and partition into semantic sub-meshes.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    pts, colors = extract_points_and_colors_from_ply(ply_path)

    # 1. Build Open3D Point Cloud and estimate surface normals
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(pts)
    pcd.colors = o3d.utility.Vector3dVector(colors)

    # Estimate normals using hybrid KD-Tree
    pcd.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.15, max_nn=30))
    pcd.orient_normals_consistent_tangent_plane(k=15)

    # 2. Poisson Surface Reconstruction
    mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(pcd, depth=depth)
    densities = np.asarray(densities)

    # Prune low-density extrapolated ghost vertices
    if len(densities) > 0:
        thresh = np.quantile(densities, 0.03)
        vertices_to_remove = densities < thresh
        mesh.remove_vertices_by_mask(vertices_to_remove)

    # Clean non-manifold vertices & degenerate triangles
    mesh.remove_degenerate_triangles()
    mesh.remove_duplicated_triangles()
    mesh.remove_duplicated_vertices()
    mesh.remove_non_manifold_edges()

    # 3. Decimate to target triangle budget for smooth 60-144 FPS WebGL
    if len(mesh.triangles) > max_triangles:
        mesh = mesh.simplify_quadric_decimation(target_number_of_triangles=max_triangles)

    mesh.compute_vertex_normals()

    # 4. Save master unified GLB
    verts = np.asarray(mesh.vertices)
    faces = np.asarray(mesh.triangles)
    v_colors = np.asarray(mesh.vertex_colors)
    if len(v_colors) == len(verts):
        rgba_colors = (np.column_stack([v_colors, np.ones(len(v_colors))]) * 255).astype(np.uint8)
    else:
        rgba_colors = None

    master_tm = trimesh.Trimesh(vertices=verts, faces=faces, vertex_colors=rgba_colors, process=False)
    master_glb_path = output_dir / "scene_mesh.glb"
    master_glb_data = master_tm.export(file_type="glb")
    master_glb_path.write_bytes(master_glb_data)

    # Calculate overall scene bounds
    min_bound = np.min(verts, axis=0)
    max_bound = np.max(verts, axis=0)
    center = (min_bound + max_bound) / 2.0
    floor_y = float(min_bound[1])

    # 5. Semantic Object Partitioning
    # If no objects provided in scene_graph, synthesize default furniture bounding boxes
    if not scene_objects:
        scene_objects = [
            {
                "entity_id": "bed_primary",
                "name": "King Bed",
                "category": "bed",
                "position": {"x": float(center[0]), "y": floor_y + 0.45, "z": float(center[2])},
                "dimensions": {"width_m": 2.0, "height_m": 0.9, "depth_m": 2.1},
            },
            {
                "entity_id": "nightstand_left",
                "name": "Nightstand",
                "category": "table",
                "position": {"x": float(center[0]) - 1.4, "y": floor_y + 0.3, "z": float(center[2])},
                "dimensions": {"width_m": 0.6, "height_m": 0.6, "depth_m": 0.5},
            }
        ]

    segmented_objects = []
    object_masks = []

    for obj in scene_objects:
        entity_id = obj.get("entity_id", "obj")
        pos = obj.get("position", {"x": 0, "y": 0, "z": 0})
        dim = obj.get("dimensions", {"width_m": 1.0, "height_m": 1.0, "depth_m": 1.0})

        half_w = (dim.get("width_m", 1.0) / 2.0) + 0.1
        half_h = (dim.get("height_m", 1.0) / 2.0) + 0.1
        half_d = (dim.get("depth_m", dim.get("width_m", 1.0)) / 2.0) + 0.1

        box_min = np.array([pos["x"] - half_w, pos["y"] - half_h, pos["z"] - half_d])
        box_max = np.array([pos["x"] + half_w, pos["y"] + half_h, pos["z"] + half_d])

        aabb = o3d.geometry.AxisAlignedBoundingBox(box_min, box_max)
        sub_mesh = mesh.crop(aabb)

        if len(sub_mesh.triangles) > 10:
            sub_verts = np.asarray(sub_mesh.vertices)
            sub_faces = np.asarray(sub_mesh.triangles)
            sub_colors = np.asarray(sub_mesh.vertex_colors)
            sub_rgba = (np.column_stack([sub_colors, np.ones(len(sub_colors))]) * 255).astype(np.uint8) if len(sub_colors) == len(sub_verts) else None

            # Pivot to local origin for easy 3D gizmo translation/rotation
            local_verts = sub_verts - np.array([pos["x"], pos["y"], pos["z"]])
            sub_tm = trimesh.Trimesh(vertices=local_verts, faces=sub_faces, vertex_colors=sub_rgba, process=False)
            sub_path = output_dir / f"{entity_id}.glb"
            sub_path.write_bytes(sub_tm.export(file_type="glb"))

            segmented_objects.append({
                "entity_id": entity_id,
                "name": obj.get("name", entity_id),
                "category": obj.get("category", "furniture"),
                "position": pos,
                "dimensions": dim,
                "mesh_file": f"{entity_id}.glb",
                "triangles": len(sub_faces),
                "vertices": len(sub_verts),
            })

    # 6. Generate Planar Floor Infill Mesh
    # Ensures moving furniture never exposes voids
    floor_margin = 0.5
    floor_min_x, floor_max_x = float(min_bound[0] - floor_margin), float(max_bound[0] + floor_margin)
    floor_min_z, floor_max_z = float(min_bound[2] - floor_margin), float(max_bound[2] + floor_margin)

    floor_verts = np.array([
        [floor_min_x, floor_y, floor_min_z],
        [floor_max_x, floor_y, floor_min_z],
        [floor_max_x, floor_y, floor_max_z],
        [floor_min_x, floor_y, floor_max_z],
    ], dtype=np.float64)

    floor_faces = np.array([
        [0, 1, 2],
        [0, 2, 3]
    ], dtype=np.int64)

    floor_tm = trimesh.Trimesh(vertices=floor_verts, faces=floor_faces, process=False)
    floor_glb_path = output_dir / "floor_infill.glb"
    floor_glb_path.write_bytes(floor_tm.export(file_type="glb"))

    manifest = {
        "master_mesh": "scene_mesh.glb",
        "floor_infill": "floor_infill.glb",
        "bounds": {
            "min": min_bound.tolist(),
            "max": max_bound.tolist(),
            "center": center.tolist(),
            "floor_y": floor_y,
        },
        "total_vertices": len(verts),
        "total_triangles": len(faces),
        "objects": segmented_objects,
    }

    manifest_path = output_dir / "mesh_manifest.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return manifest
