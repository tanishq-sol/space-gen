#!/usr/bin/env python3
"""
SpaceGen AI — Video Processing Script

Extracts keyframes from a room capture video for 3D reconstruction.

Usage:
    python process_video.py input_video.mp4 output_dir/ [--fps 2] [--quality-threshold 50]

What it does:
1. Probes video metadata (resolution, duration, fps)
2. Extracts frames at specified FPS
3. Scores each frame for quality (blur detection)
4. Selects best keyframes based on quality + temporal spacing
5. Outputs keyframes as numbered JPEG files

Requirements:
    pip install opencv-python numpy
    FFmpeg must be installed and in PATH
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Fix Windows console encoding issues
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import cv2
import numpy as np


def probe_video(video_path: str) -> dict:
    """Get video metadata using FFmpeg."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        video_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        video_stream = next(s for s in data["streams"] if s["codec_type"] == "video")
        return {
            "width": int(video_stream["width"]),
            "height": int(video_stream["height"]),
            "fps": eval(video_stream.get("r_frame_rate", "30/1")),
            "duration": float(data["format"]["duration"]),
            "codec": video_stream["codec_name"],
            "total_frames": int(video_stream.get("nb_frames", 0)),
        }
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("[WARN] FFmpeg/FFprobe not found. Using OpenCV fallback.")
        cap = cv2.VideoCapture(video_path)
        info = {
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": cap.get(cv2.CAP_PROP_FPS),
            "duration": cap.get(cv2.CAP_PROP_FRAME_COUNT) / max(cap.get(cv2.CAP_PROP_FPS), 1),
            "codec": "unknown",
            "total_frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
        }
        cap.release()
        return info


def compute_blur_score(frame: np.ndarray) -> float:
    """Compute Laplacian variance as blur score. Higher = sharper."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def compute_exposure_score(frame: np.ndarray) -> float:
    """Score exposure quality. 0-1, higher is better."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mean_brightness = float(np.mean(gray))
    # Penalize very dark or very bright
    if mean_brightness < 30 or mean_brightness > 225:
        return 0.3
    elif mean_brightness < 60 or mean_brightness > 200:
        return 0.7
    return 1.0


def extract_keyframes(
    video_path: str,
    output_dir: str,
    target_fps: float = 2.0,
    quality_threshold: float = 50.0,
    max_frames: int = 500,
    min_frames: int = 50,
) -> dict:
    """Extract quality keyframes from video."""
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Probe video
    info = probe_video(video_path)
    print(f"[INFO] Video: {info['width']}x{info['height']} @ {info['fps']:.1f}fps, {info['duration']:.1f}s")
    
    if info["width"] < 1080:
        print(f"[WARN] Resolution {info['width']}x{info['height']} is below recommended 1080p")
    
    if info["duration"] < 10:
        print("[WARN] Video is very short. Capture at least 30 seconds for good reconstruction.")
    elif info["duration"] > 300:
        print("[WARN] Video is very long (>5min). Processing may be slow.")
    
    # Open video
    cap = cv2.VideoCapture(video_path)
    source_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    # Calculate frame sampling interval
    frame_interval = max(1, int(source_fps / max(target_fps, 0.1)))
    
    print(f"[INFO] Sampling every {frame_interval} frames ({target_fps} fps target)")
    
    # Extract and score frames
    candidates = []
    frame_idx = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        if frame_idx % frame_interval == 0:
            blur_score = compute_blur_score(frame)
            exposure_score = compute_exposure_score(frame)
            
            candidates.append({
                "frame_idx": frame_idx,
                "timestamp": frame_idx / source_fps,
                "blur_score": blur_score,
                "exposure_score": exposure_score,
                "quality_score": blur_score * exposure_score,
            })
        
        frame_idx += 1
        
        # Progress
        if frame_idx % 100 == 0:
            pct = (frame_idx / max(total_frames, 1)) * 100
            print(f"  Analyzing... {pct:.0f}%", end="\r")
    
    cap.release()
    print(f"\n[INFO] Analyzed {len(candidates)} candidate frames")
    
    # Filter by quality
    quality_frames = [f for f in candidates if f["blur_score"] >= quality_threshold]
    
    if len(quality_frames) < min_frames:
        print(f"[WARN] Only {len(quality_frames)} frames passed quality filter. Lowering threshold.")
        candidates.sort(key=lambda x: x["quality_score"], reverse=True)
        quality_frames = candidates[:max(min_frames, len(candidates))]
    
    # Sort by timestamp and limit
    quality_frames.sort(key=lambda x: x["timestamp"])
    if len(quality_frames) > max_frames:
        # Uniformly sample
        step = len(quality_frames) / max_frames
        quality_frames = [quality_frames[int(i * step)] for i in range(max_frames)]
    
    print(f"[OK] Selected {len(quality_frames)} keyframes")
    
    # Save keyframes
    cap = cv2.VideoCapture(video_path)
    saved = 0
    frame_indices = {f["frame_idx"] for f in quality_frames}
    frame_idx = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        if frame_idx in frame_indices:
            filename = f"frame_{saved:04d}.jpg"
            filepath = output_path / filename
            cv2.imwrite(str(filepath), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            saved += 1
            
            if saved % 50 == 0:
                print(f"  Saving... {saved}/{len(quality_frames)}", end="\r")
        
        frame_idx += 1
    
    cap.release()
    
    # Save metadata
    blur_scores = [f["blur_score"] for f in quality_frames] or [0.0]
    quality_scores = [f["quality_score"] for f in quality_frames] or [0.0]
    
    metadata = {
        "video": info,
        "extraction": {
            "target_fps": target_fps,
            "quality_threshold": quality_threshold,
            "total_candidates": len(candidates),
            "selected_keyframes": len(quality_frames),
            "avg_blur_score": float(np.mean(blur_scores)),
            "avg_quality_score": float(np.mean(quality_scores)),
        },
        "keyframes": quality_frames,
    }
    
    metadata_path = output_path / "metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    
    print(f"\n[OK] Saved {saved} keyframes to {output_dir}")
    print(f"[INFO] Metadata saved to {metadata_path}")
    
    # Quality summary
    print(f"\n[INFO] Quality Summary:")
    print(f"   Blur scores: min={min(blur_scores):.1f}, max={max(blur_scores):.1f}, avg={np.mean(blur_scores):.1f}")
    if quality_frames:
        print(f"   Frame coverage: {quality_frames[0]['timestamp']:.1f}s - {quality_frames[-1]['timestamp']:.1f}s")
    
    return metadata


def main():
    parser = argparse.ArgumentParser(description="SpaceGen AI — Video Frame Extractor")
    parser.add_argument("video", help="Path to input video file")
    parser.add_argument("output", help="Output directory for keyframes")
    parser.add_argument("--fps", type=float, default=2.0, help="Target extraction FPS (default: 2)")
    parser.add_argument("--quality-threshold", type=float, default=50.0, help="Minimum blur score (default: 50)")
    parser.add_argument("--max-frames", type=int, default=500, help="Maximum keyframes (default: 500)")
    parser.add_argument("--min-frames", type=int, default=50, help="Minimum keyframes (default: 50)")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.video):
        print(f"[ERROR] Video not found: {args.video}")
        sys.exit(1)
    
    extract_keyframes(
        args.video,
        args.output,
        target_fps=args.fps,
        quality_threshold=args.quality_threshold,
        max_frames=args.max_frames,
        min_frames=args.min_frames,
    )


if __name__ == "__main__":
    main()
