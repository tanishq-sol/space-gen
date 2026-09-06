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
from typing import Any, Optional

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
    allowed = {".ply", ".spz", ".splat", ".ksplat", ".glb", ".gltf", ".obj"}
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
        "splat_url": f"/api/reconstruction/jobs/{job_id}/model/{target_filename}"
    }
    db.save_job(job_id, job_data)
    return job_data


@router.get("/models")
async def list_available_models():
    """List all available 3D Gaussian Splat and mesh models stored on disk."""
    models = []
    supported_exts = {".ply", ".spz", ".ksplat", ".splat", ".glb", ".gltf", ".obj"}
    if DATA_ROOT.exists():
        job_dirs = sorted([d for d in DATA_ROOT.iterdir() if d.is_dir()], key=lambda d: d.stat().st_mtime, reverse=True)
        for d in job_dirs:
            export_dir = d / "export"
            if not export_dir.exists():
                export_dir = d

            found_file = None
            # Check preferred candidate names first
            for candidate_name in ["splat.ply", "scene.glb", "scene.spz", "scene.ksplat", "scene.splat", "scene.gltf", "scene.obj", "point_cloud.ply"]:
                target_file = export_dir / candidate_name
                if target_file.exists():
                    found_file = target_file
                    break
            
            # If not found by candidate name, search for any supported 3D file
            if not found_file and export_dir.exists():
                for f in export_dir.iterdir():
                    if f.is_file() and f.suffix.lower() in supported_exts:
                        found_file = f
                        break

            if found_file:
                size_mb = round(found_file.stat().st_size / (1024 * 1024), 1)
                models.append({
                    "job_id": d.name,
                    "filename": found_file.name,
                    "size_mb": size_mb,
                    "format": found_file.suffix.replace(".", ""),
                    "url": f"/api/reconstruction/jobs/{d.name}/model/{found_file.name}",
                    "modified": found_file.stat().st_mtime,
                })
    return models


@router.get("/jobs/latest")
async def get_latest_reconstruction_job():
    """Get the most recent reconstruction job or check data directory for existing splats."""
    job = db.get_latest_job()
    if job:
        return job
    
    # Check DATA_ROOT for existing completed jobs
    supported_exts = {".ply", ".spz", ".ksplat", ".splat", ".glb", ".gltf", ".obj"}
    if DATA_ROOT.exists():
        job_dirs = sorted([d for d in DATA_ROOT.iterdir() if d.is_dir()], key=lambda d: d.stat().st_mtime, reverse=True)
        for d in job_dirs:
            export_dir = d / "export"
            if export_dir.exists():
                for f in export_dir.iterdir():
                    if f.is_file() and f.suffix.lower() in supported_exts:
                        return {
                            "job_id": d.name,
                            "status": "completed",
                            "progress": 100,
                            "step": "Model ready",
                            "log": f"3D model ({f.name}) ready.",
                            "scene_path": str(export_dir),
                            "splat_url": f"/api/reconstruction/jobs/{d.name}/model/{f.name}",
                        }
    raise HTTPException(404, "No reconstruction jobs found")


@router.api_route("/jobs/{job_id}/model", methods=["GET", "HEAD"])
async def get_reconstruction_model_default(job_id: str):
    return _resolve_and_serve_model(job_id, None)


@router.api_route("/jobs/{job_id}/model/{filename:path}", methods=["GET", "HEAD"])
async def get_reconstruction_model(job_id: str, filename: str):
    return _resolve_and_serve_model(job_id, filename)


def _resolve_and_serve_model(job_id: str, filename: Optional[str] = None):
    """Serve the exported 3D Gaussian Splat (.ply, .spz, .splat) or mesh (.glb, .obj) for a reconstruction job."""
    job_dir = DATA_ROOT / job_id
    if not job_dir.exists():
        fallback_dir = ROOT / "data" / "reconstruction" / job_id
        if fallback_dir.exists():
            job_dir = fallback_dir

    export_dir = job_dir / "export"
    search_dirs = [export_dir, job_dir]

    # 1. If explicit filename requested, try finding it directly
    if filename:
        for sdir in search_dirs:
            target = sdir / filename
            if target.exists() and target.is_file():
                return _create_model_response(target)

    # 2. Check standard candidate names
    for sdir in search_dirs:
        for candidate_name in ["splat.ply", "scene.glb", "scene.spz", "scene.ksplat", "scene.splat", "scene.gltf", "scene.obj", "point_cloud.ply"]:
            candidate = sdir / candidate_name
            if candidate.exists():
                return _create_model_response(candidate)

    # 3. Check for any supported 3D file in export or job directory
    supported_exts = {".ply", ".spz", ".ksplat", ".splat", ".glb", ".gltf", ".obj"}
    for sdir in search_dirs:
        if sdir.exists():
            for f in sdir.iterdir():
                if f.is_file() and f.suffix.lower() in supported_exts:
                    return _create_model_response(f)

    raise HTTPException(404, f"3D model file not found for job {job_id}")


def _create_model_response(file_path: Path) -> FileResponse:
    ext = file_path.suffix.lower()
    media_types = {
        ".glb": "model/gltf-binary",
        ".gltf": "model/gltf+json",
        ".ply": "application/octet-stream",
        ".spz": "application/octet-stream",
        ".splat": "application/octet-stream",
        ".ksplat": "application/octet-stream",
        ".obj": "text/plain",
    }
    media_type = media_types.get(ext, "application/octet-stream")
    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=file_path.name,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Expose-Headers": "Content-Length, Content-Type, Accept-Ranges",
            "Accept-Ranges": "bytes",
        },
    )


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
