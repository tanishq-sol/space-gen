"""Local & Cloud video ingestion and Gaussian Splatting training pipeline.

Persists reconstruction jobs and serves 3D Gaussian Splat (.ply, .spz, .ksplat)
artifacts for real-time browser rendering.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from db.database import db

router = APIRouter(prefix="/api/reconstruction", tags=["reconstruction"])
ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path("D:/spacegen_data/reconstruction")
try:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
except Exception:
    DATA_ROOT = ROOT / "data" / "reconstruction"
    DATA_ROOT.mkdir(parents=True, exist_ok=True)


# Auto-register known local paths for COLMAP, ffmpeg, and Nerfstudio
_EXTRA_PATHS = [
    Path("C:/colmap"),
    Path("C:/colmap/bin"),
    Path.home() / "colmap",
    Path.home() / "colmap" / "bin",
    Path.home() / "miniconda3" / "envs" / "nerfstudio" / "Library" / "bin",
    Path.home() / "miniconda3" / "envs" / "nerfstudio" / "Library" / "usr" / "bin",
    Path.home() / "miniconda3" / "envs" / "nerfstudio" / "Library" / "mingw-w64" / "bin",
    Path.home() / "miniconda3" / "envs" / "nerfstudio" / "Scripts",
    Path.home() / "miniconda3" / "envs" / "nerfstudio",
    Path.home() / "Anaconda3" / "envs" / "nerfstudio" / "Library" / "bin",
    Path.home() / "Anaconda3" / "envs" / "nerfstudio" / "Scripts",
]

_current_path = os.environ.get("PATH", "")
_path_parts = _current_path.split(os.pathsep)
for _p in _EXTRA_PATHS:
    if _p.exists() and str(_p) not in _path_parts:
        _path_parts.insert(0, str(_p))
os.environ["PATH"] = os.pathsep.join(_path_parts)
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"


def _find_tool(name: str) -> str | None:
    """Find a binary in PATH or known local install directories."""
    found = shutil.which(name)
    if found:
        return found
    for _p in _EXTRA_PATHS:
        for ext in [".exe", ".bat", ".cmd", ""]:
            candidate = _p / f"{name}{ext}"
            if candidate.exists():
                return str(candidate)
    return None


def _update(job_id: str, **values: Any) -> None:
    db.update_job(job_id, **values)


def _run(command: list[str], cwd: Path, job_id: str, step: str) -> None:
    """Run a CLI command and stream the last line into persistent job state."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
    )
    assert process.stdout is not None
    for line in process.stdout:
        line = line.strip()
        if line:
            _update(job_id, step=step, log=line[-240:])
    code = process.wait()
    if code:
        raise RuntimeError(f"{step} failed with exit code {code}")


def _worker(job_id: str, video_path: Path, job_dir: Path, mode: str = "fast") -> None:
    try:
        _update(job_id, status="running", progress=12, step="Extracting keyframes", log="Extracting keyframes for reconstruction…")
        frames = job_dir / "frames"
        script = ROOT / "scripts" / "process_video.py"
        fps_val = "2" if mode == "fast" else "3"
        min_frames = "28" if mode == "fast" else "36"
        thresh = "45" if mode == "fast" else "40"
        max_iters = "6000" if mode == "fast" else "15000"

        if script.exists():
            _run([sys.executable, str(script), str(video_path), str(frames), "--fps", fps_val, "--min-frames", min_frames, "--quality-threshold", thresh], ROOT, job_id, "Extracting keyframes")

        ns_process = _find_tool("ns-process-data")
        ns_train = _find_tool("ns-train")
        ns_export = _find_tool("ns-export")
        if not (ns_process and ns_train):
            _update(job_id, status="ready_for_training", progress=38,
                    step="Frames ready — install Nerfstudio or use Cloud GPU",
                    log="Keyframes extracted. Ready for Gaussian Splatting training.",
                    frames_dir=str(frames))
            return

        processed = job_dir / "processed"
        _update(job_id, progress=45, step="Estimating camera poses", log="Running fast sequential feature extraction & bundle adjustment…")
        _run([
            ns_process, "images",
            "--data", str(frames),
            "--output-dir", str(processed),
            "--camera-type", "perspective",
            "--matching-method", "sequential",
            "--num-downscales", "2",
        ], ROOT, job_id, "Estimating camera poses")
        
        output = job_dir / "output"
        _update(job_id, progress=58, step="Training Gaussian Splatting", log=f"Training splatfacto on GPU ({max_iters} steps)…")
        _run([
            ns_train, "splatfacto",
            "--data", str(processed),
            "--output-dir", str(output),
            "--max-num-iterations", max_iters,
            "--pipeline.model.num-downscales", "1",
            "--viewer.quit-on-train-completion", "True",
        ], ROOT, job_id, "Training Gaussian Splatting")

        export_dir = job_dir / "export"
        if ns_export:
            configs = sorted(output.glob("**/config.yml"), key=lambda p: p.stat().st_mtime, reverse=True)
            if configs:
                _update(job_id, progress=88, step="Exporting scene", log="Packaging the trained splat for the viewer…")
                _run([ns_export, "gaussian-splat", "--load-config", str(configs[0]), "--output-dir", str(export_dir)], ROOT, job_id, "Exporting scene")
        _update(job_id, status="completed", progress=100, step="Scene ready", log="Gaussian Splatting scene completed.", scene_path=str(export_dir))
    except Exception as exc:
        _update(job_id, status="failed", step="Reconstruction failed", log=str(exc))


@router.post("/jobs", status_code=202)
async def create_reconstruction_job(video: UploadFile = File(...), mode: str = "fast"):
    allowed = {".mp4", ".mov", ".m4v", ".webm", ".avi"}
    suffix = Path(video.filename or "capture.mp4").suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, "Upload an MP4, MOV, M4V, WebM, or AVI video.")
    job_id = uuid.uuid4().hex[:12]
    job_dir = DATA_ROOT / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    video_path = job_dir / f"capture{suffix}"
    with video_path.open("wb") as target:
        shutil.copyfileobj(video.file, target)
    
    job_data = {
        "job_id": job_id, 
        "status": "queued", 
        "progress": 4,
        "step": "Queued", 
        "log": f"Video uploaded ({mode} mode) — waiting for worker…",
        "video_path": str(video_path),
        "mode": mode,
    }
    db.save_job(job_id, job_data)
    asyncio.create_task(asyncio.to_thread(_worker, job_id, video_path, job_dir, mode))
    return job_data


@router.post("/upload-model", status_code=201)
async def upload_existing_model(model: UploadFile = File(...)):
    """Upload an existing 3D Gaussian Splat (.ply, .spz, .splat, .ksplat) or mesh (.glb) to view immediately."""
    allowed = {".ply", ".spz", ".splat", ".ksplat", ".glb", ".gltf"}
    suffix = Path(model.filename or "model.ply").suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, f"Unsupported 3D model format. Allowed: {', '.join(allowed)}")
    
    job_id = f"import_{uuid.uuid4().hex[:8]}"
    job_dir = DATA_ROOT / job_id
    export_dir = job_dir / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    
    target_filename = "splat.ply" if suffix == ".ply" else f"scene{suffix}"
    target_path = export_dir / target_filename
    with target_path.open("wb") as out:
        shutil.copyfileobj(model.file, out)
        
    size_mb = round(target_path.stat().st_size / (1024 * 1024), 1)
    job_data = {
        "job_id": job_id,
        "status": "completed",
        "progress": 100,
        "step": "Model ready",
        "log": f"Imported {model.filename} ({size_mb} MB) successfully.",
        "scene_path": str(export_dir),
        "splat_url": f"/api/reconstruction/jobs/{job_id}/model"
    }
    db.save_job(job_id, job_data)
    return job_data


@router.get("/models")
async def list_available_models():
    """List all available 3D Gaussian Splat models stored on disk."""
    models = []
    if DATA_ROOT.exists():
        job_dirs = sorted([d for d in DATA_ROOT.iterdir() if d.is_dir()], key=lambda d: d.stat().st_mtime, reverse=True)
        for d in job_dirs:
            export_dir = d / "export"
            for candidate_name in ["splat.ply", "scene.spz", "scene.ksplat", "point_cloud.ply"]:
                target_file = export_dir / candidate_name
                if target_file.exists():
                    size_mb = round(target_file.stat().st_size / (1024 * 1024), 1)
                    models.append({
                        "job_id": d.name,
                        "filename": candidate_name,
                        "size_mb": size_mb,
                        "format": target_file.suffix.replace(".", ""),
                        "url": f"/api/reconstruction/jobs/{d.name}/model",
                        "modified": target_file.stat().st_mtime,
                    })
                    break
    return models


@router.get("/jobs/latest")
async def get_latest_reconstruction_job():
    """Get the most recent reconstruction job or check data directory for existing splats."""
    job = db.get_latest_job()
    if job:
        return job
    
    # Check DATA_ROOT for existing completed jobs
    if DATA_ROOT.exists():
        job_dirs = sorted([d for d in DATA_ROOT.iterdir() if d.is_dir()], key=lambda d: d.stat().st_mtime, reverse=True)
        for d in job_dirs:
            splat_file = d / "export" / "splat.ply"
            if splat_file.exists():
                return {
                    "job_id": d.name,
                    "status": "completed",
                    "progress": 100,
                    "step": "Scene ready",
                    "log": "Gaussian Splatting scene ready.",
                    "scene_path": str(d / "export"),
                    "splat_url": f"/api/reconstruction/jobs/{d.name}/model",
                }
    raise HTTPException(404, "No reconstruction jobs found")


@router.api_route("/jobs/{job_id}/model", methods=["GET", "HEAD"])
async def get_reconstruction_model(job_id: str):
    """Serve the exported 3D Gaussian Splat PLY/SPZ model for a reconstruction job."""
    job_dir = DATA_ROOT / job_id
    if not job_dir.exists():
        fallback_dir = ROOT / "data" / "reconstruction" / job_id
        if fallback_dir.exists():
            job_dir = fallback_dir

    export_dir = job_dir / "export"
    for filename in ["splat.ply", "point_cloud.ply", "scene.spz", "scene.ksplat"]:
        candidate = export_dir / filename
        if candidate.exists():
            return FileResponse(
                path=candidate,
                media_type="application/octet-stream",
                filename=filename,
                headers={"Access-Control-Allow-Origin": "*"},
            )
    
    ply_files = list(job_dir.glob("**/*.ply"))
    if ply_files:
        return FileResponse(
            path=ply_files[0],
            media_type="application/octet-stream",
            filename=ply_files[0].name,
            headers={"Access-Control-Allow-Origin": "*"},
        )
    
    raise HTTPException(404, f"3D model file (splat.ply) not found for job {job_id}")


@router.get("/jobs/{job_id}")
async def get_reconstruction_job(job_id: str):
    job = db.get_job(job_id)
    if job:
        return job

    job_dir = DATA_ROOT / job_id
    splat_file = job_dir / "export" / "splat.ply"
    if splat_file.exists():
        return {
            "job_id": job_id,
            "status": "completed",
            "progress": 100,
            "step": "Scene ready",
            "log": "Gaussian Splatting scene completed.",
            "scene_path": str(job_dir / "export"),
            "splat_url": f"/api/reconstruction/jobs/{job_id}/model",
        }
    raise HTTPException(404, "Reconstruction job not found")
