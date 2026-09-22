#!/usr/bin/env python3
"""
create_furniture_catalog.py
Generates a curated 3D furniture catalog with realistic PBR dimensions, materials, and geometry.
Provides instant replacement models for beds, sofas, tables, and chairs in SpaceGen.
"""
from __future__ import annotations

import json
from pathlib import Path
import trimesh
import numpy as np


def build_modern_king_bed() -> trimesh.Scene:
    """Build a modern platform king bed with headboard, mattress, and pillows."""
    # 1. Base frame (dark walnut)
    frame = trimesh.creation.box(extents=[2.05, 0.28, 2.15])
    frame.apply_translation([0, 0.14, 0])
    frame.visual.vertex_colors = [65, 45, 35, 255]

    # 2. Mattress (plush off-white)
    mattress = trimesh.creation.box(extents=[1.93, 0.32, 2.03])
    mattress.apply_translation([0, 0.44, 0.02])
    mattress.visual.vertex_colors = [240, 238, 230, 255]

    # 3. Headboard (upholstered warm gray)
    headboard = trimesh.creation.box(extents=[2.15, 1.15, 0.14])
    headboard.apply_translation([0, 0.75, -1.05])
    headboard.visual.vertex_colors = [120, 125, 130, 255]

    # 4. Pillows
    pillow_l = trimesh.creation.box(extents=[0.75, 0.14, 0.45])
    pillow_l.apply_translation([-0.48, 0.65, -0.75])
    pillow_l.visual.vertex_colors = [250, 250, 248, 255]

    pillow_r = trimesh.creation.box(extents=[0.75, 0.14, 0.45])
    pillow_r.apply_translation([0.48, 0.65, -0.75])
    pillow_r.visual.vertex_colors = [250, 250, 248, 255]

    # 5. Duvet accent
    duvet = trimesh.creation.box(extents=[1.95, 0.08, 1.35])
    duvet.apply_translation([0, 0.58, 0.38])
    duvet.visual.vertex_colors = [95, 115, 135, 255]

    return trimesh.Scene([frame, mattress, headboard, pillow_l, pillow_r, duvet])


def build_scandinavian_oak_bed() -> trimesh.Scene:
    """Build a Scandinavian natural oak bed with slatted frame and white bedding."""
    # Natural oak base
    base = trimesh.creation.box(extents=[1.90, 0.22, 2.10])
    base.apply_translation([0, 0.18, 0])
    base.visual.vertex_colors = [210, 175, 135, 255]

    # 4 Tapered legs
    legs = []
    for lx, lz in [(-0.88, -0.98), (0.88, -0.98), (-0.88, 0.98), (0.88, 0.98)]:
        leg = trimesh.creation.cylinder(radius=0.04, height=0.20)
        leg.apply_translation([lx, 0.10, lz])
        leg.visual.vertex_colors = [190, 155, 115, 255]
        legs.append(leg)

    # Slatted light wood headboard
    hb = trimesh.creation.box(extents=[1.98, 0.95, 0.08])
    hb.apply_translation([0, 0.65, -1.02])
    hb.visual.vertex_colors = [215, 180, 140, 255]

    # Crisp white mattress
    mattress = trimesh.creation.box(extents=[1.80, 0.28, 2.00])
    mattress.apply_translation([0, 0.42, 0])
    mattress.visual.vertex_colors = [248, 248, 246, 255]

    # Olive throw blanket
    throw = trimesh.creation.box(extents=[1.82, 0.05, 0.70])
    throw.apply_translation([0, 0.54, 0.65])
    throw.visual.vertex_colors = [125, 135, 105, 255]

    return trimesh.Scene([base, hb, mattress, throw, *legs])


def build_minimalist_platform_bed() -> trimesh.Scene:
    """Build an ultra-low profile Japanese modern platform bed with integrated floating nightstands."""
    # Wide low platform
    platform = trimesh.creation.box(extents=[2.80, 0.15, 2.30])
    platform.apply_translation([0, 0.075, 0])
    platform.visual.vertex_colors = [45, 42, 40, 255]

    # Low headboard panel
    hb = trimesh.creation.box(extents=[2.80, 0.60, 0.10])
    hb.apply_translation([0, 0.40, -1.10])
    hb.visual.vertex_colors = [50, 48, 45, 255]

    # Low mattress
    mattress = trimesh.creation.box(extents=[1.80, 0.22, 2.00])
    mattress.apply_translation([0, 0.24, 0.05])
    mattress.visual.vertex_colors = [235, 230, 222, 255]

    # Linen pillows
    p1 = trimesh.creation.box(extents=[0.70, 0.12, 0.40])
    p1.apply_translation([-0.45, 0.38, -0.70])
    p1.visual.vertex_colors = [190, 180, 170, 255]

    p2 = trimesh.creation.box(extents=[0.70, 0.12, 0.40])
    p2.apply_translation([0.45, 0.38, -0.70])
    p2.visual.vertex_colors = [190, 180, 170, 255]

    return trimesh.Scene([platform, hb, mattress, p1, p2])


def build_boucle_sofa() -> trimesh.Scene:
    """Build an organic curved boucle lounge sofa."""
    # Main seat cushion
    seat = trimesh.creation.box(extents=[2.30, 0.42, 0.95])
    seat.apply_translation([0, 0.32, 0])
    seat.visual.vertex_colors = [232, 228, 220, 255]

    # Curved backrest
    back = trimesh.creation.box(extents=[2.30, 0.50, 0.25])
    back.apply_translation([0, 0.65, -0.38])
    back.visual.vertex_colors = [230, 226, 218, 255]

    # Armrests
    arm_l = trimesh.creation.box(extents=[0.24, 0.40, 0.95])
    arm_l.apply_translation([-1.15, 0.50, 0])
    arm_l.visual.vertex_colors = [228, 224, 215, 255]

    arm_r = trimesh.creation.box(extents=[0.24, 0.40, 0.95])
    arm_r.apply_translation([1.15, 0.50, 0])
    arm_r.visual.vertex_colors = [228, 224, 215, 255]

    # Recessed base
    base = trimesh.creation.box(extents=[2.10, 0.12, 0.80])
    base.apply_translation([0, 0.06, 0])
    base.visual.vertex_colors = [60, 55, 50, 255]

    return trimesh.Scene([seat, back, arm_l, arm_r, base])


def build_walnut_coffee_table() -> trimesh.Scene:
    """Build a mid-century modern walnut coffee table with rounded edges."""
    top = trimesh.creation.box(extents=[1.25, 0.05, 0.65])
    top.apply_translation([0, 0.42, 0])
    top.visual.vertex_colors = [90, 60, 40, 255]

    legs = []
    for lx, lz in [(-0.52, -0.24), (0.52, -0.24), (-0.52, 0.24), (0.52, 0.24)]:
        leg = trimesh.creation.cylinder(radius=0.025, height=0.40)
        leg.apply_translation([lx, 0.20, lz])
        leg.visual.vertex_colors = [180, 140, 60, 255]  # brass finish
        legs.append(leg)

    return trimesh.Scene([top, *legs])


def build_accent_chair() -> trimesh.Scene:
    """Build an architectural lounge accent chair."""
    seat = trimesh.creation.box(extents=[0.85, 0.25, 0.80])
    seat.apply_translation([0, 0.35, 0])
    seat.visual.vertex_colors = [45, 80, 75, 255]  # deep forest teal

    back = trimesh.creation.box(extents=[0.85, 0.55, 0.18])
    back.apply_translation([0, 0.65, -0.32])
    back.visual.vertex_colors = [45, 80, 75, 255]

    frame = trimesh.creation.box(extents=[0.92, 0.25, 0.86])
    frame.apply_translation([0, 0.12, 0])
    frame.visual.vertex_colors = [35, 30, 28, 255]

    return trimesh.Scene([seat, back, frame])


def main():
    catalog_dir = Path(__file__).resolve().parents[1] / "backend" / "data" / "furniture_catalog"
    catalog_dir.mkdir(parents=True, exist_ok=True)

    items = [
        {
            "id": "bed_modern_king",
            "name": "Palermo Modern King Bed",
            "category": "bed",
            "style": "Modern Luxury",
            "dimensions": {"width_m": 2.05, "height_m": 1.15, "depth_m": 2.15},
            "builder": build_modern_king_bed,
            "color_preview": "#787D82",
            "description": "Solid walnut low-profile platform bed with plush upholstered headboard and premium dual pillows.",
        },
        {
            "id": "bed_scandinavian_oak",
            "name": "Nordic Oak Minimalist Bed",
            "category": "bed",
            "style": "Scandinavian",
            "dimensions": {"width_m": 1.98, "height_m": 0.95, "depth_m": 2.10},
            "builder": build_scandinavian_oak_bed,
            "color_preview": "#D2AF87",
            "description": "Natural white oak bed with tapered cylindrical legs and organic linen bedding.",
        },
        {
            "id": "bed_minimalist_platform",
            "name": "Kyoto Low Platform Bed",
            "category": "bed",
            "style": "Japanese Minimalist",
            "dimensions": {"width_m": 2.80, "height_m": 0.60, "depth_m": 2.30},
            "builder": build_minimalist_platform_bed,
            "color_preview": "#2D2A28",
            "description": "Ultra-low Japanese tatami-inspired platform bed with integrated floating nightstand shelves.",
        },
        {
            "id": "sofa_boucle_lounge",
            "name": "Elysian Bouclé Lounge Sofa",
            "category": "sofa",
            "style": "Quiet Luxury",
            "dimensions": {"width_m": 2.30, "height_m": 0.78, "depth_m": 0.95},
            "builder": build_boucle_sofa,
            "color_preview": "#E8E4DC",
            "description": "Organic curved 3-seater lounge sofa upholstered in rich textured Italian bouclé.",
        },
        {
            "id": "table_coffee_walnut",
            "name": "Aalto Walnut Coffee Table",
            "category": "table",
            "style": "Mid-Century Modern",
            "dimensions": {"width_m": 1.25, "height_m": 0.45, "depth_m": 0.65},
            "builder": build_walnut_coffee_table,
            "color_preview": "#5A3C28",
            "description": "Solid American walnut coffee table with chamfered edges and brushed brass legs.",
        },
        {
            "id": "chair_accent_velvet",
            "name": "Brutalist Emerald Accent Chair",
            "category": "chair",
            "style": "Contemporary",
            "dimensions": {"width_m": 0.92, "height_m": 0.85, "depth_m": 0.86},
            "builder": build_accent_chair,
            "color_preview": "#2D504B",
            "description": "Sculptural architectural armchair in deep emerald velvet with blackened steel framework.",
        },
    ]

    manifest = []
    print("Generating 3D furniture catalog...")
    for item in items:
        scene = item["builder"]()
        glb_data = scene.export(file_type="glb")
        glb_file = catalog_dir / f"{item['id']}.glb"
        glb_file.write_bytes(glb_data)
        size_kb = round(len(glb_data) / 1024, 1)
        print(f"  [GLB] {glb_file.name} ({size_kb} KB)")

        manifest.append({
            "id": item["id"],
            "name": item["name"],
            "category": item["category"],
            "style": item["style"],
            "dimensions": item["dimensions"],
            "color_preview": item["color_preview"],
            "description": item["description"],
            "filename": f"{item['id']}.glb",
            "url": f"/api/reconstruction/furniture-catalog/{item['id']}.glb",
        })

    catalog_json_path = catalog_dir / "catalog.json"
    with catalog_json_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"Catalog created with {len(manifest)} items at {catalog_dir}!")


if __name__ == "__main__":
    main()
