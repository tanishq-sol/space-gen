#!/usr/bin/env python3
"""
SpaceGen AI — Reconstruction Guide

Step-by-step guide for running 3D reconstruction on captured video.
This is NOT an automated script — it provides commands to run.

Pre-requisites:
    - NVIDIA GPU with 12+ GB VRAM (or cloud GPU: RunPod, Google Colab)
    - COLMAP 4.0 installed
    - Nerfstudio installed (pip install nerfstudio)
    - Frames extracted via process_video.py
"""

GUIDE = """
# SpaceGen AI — 3D Reconstruction Guide

## Step 1: Extract Frames
```bash
python scripts/process_video.py your_room_video.mp4 data/frames/ --fps 2
```

## Step 2: Run COLMAP (Camera Pose Estimation)

### Option A: Using Nerfstudio's ns-process-data (RECOMMENDED)
```bash
ns-process-data images \\
    --data data/frames/ \\
    --output-dir data/processed/ \\
    --camera-type perspective
```
This runs COLMAP internally and outputs camera poses in Nerfstudio format.

### Option B: Using COLMAP directly
```bash
# Feature extraction
colmap feature_extractor \\
    --database_path data/colmap/database.db \\
    --image_path data/frames/ \\
    --ImageReader.camera_model OPENCV \\
    --ImageReader.single_camera 1

# Feature matching
colmap exhaustive_matcher \\
    --database_path data/colmap/database.db

# Sparse reconstruction (uses GLOMAP in COLMAP 4.0)
colmap mapper \\
    --database_path data/colmap/database.db \\
    --image_path data/frames/ \\
    --output_path data/colmap/sparse/

# Bundle adjustment
colmap bundle_adjuster \\
    --input_path data/colmap/sparse/0/ \\
    --output_path data/colmap/sparse/0/
```

## Step 3: Train Gaussian Splatting

### Using Nerfstudio (RECOMMENDED)
```bash
ns-train splatfacto \\
    --data data/processed/ \\
    --output-dir data/output/ \\
    --max-num-iterations 30000 \\
    --pipeline.model.num-downscales 2
```

Training takes 5-15 minutes on RTX 4090, 15-30 minutes on RTX 3090.

### Export to SPZ (for web viewer)
```bash
ns-export gaussian-splat \\
    --load-config data/output/splatfacto/<timestamp>/config.yml \\
    --output-dir data/export/
```

## Step 4: Verify Output

Check these files exist:
```
data/export/
├── point_cloud.ply     # Gaussian Splat (raw)
├── scene.spz           # Compressed for web (if supported)
└── cameras.json        # Camera poses
```

## Cloud GPU Options (if no local GPU)

### RunPod (~$0.40/hr for RTX 4090)
1. Go to runpod.io
2. Deploy a PyTorch template
3. Install nerfstudio: pip install nerfstudio
4. Upload frames
5. Run ns-train

### Google Colab (free tier)
1. Open a Colab notebook
2. Select T4 GPU runtime
3. Install: !pip install nerfstudio
4. Upload frames to /content/frames/
5. Run ns-process-data + ns-train

Note: Free Colab T4 has 16GB VRAM — sufficient for small-medium rooms.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| COLMAP fails (no poses) | Try DUSt3R: pip install dust3r; Use MASt3R for initialization |
| Out of VRAM | Reduce --pipeline.model.num-downscales to 3 or 4 |
| Blurry result | Extract more frames (--fps 3) or higher quality threshold |
| Holes in reconstruction | Need more frames covering those areas |
| Training too slow | Reduce --max-num-iterations to 15000 for quick preview |
"""

if __name__ == "__main__":
    print(GUIDE)
