"""Local video ingestion and Gaussian Splatting training jobs.

The API intentionally keeps job state in memory for the hackathon. The worker
uses the checked-in frame processor and Nerfstudio CLI, so it is easy to run
locally with an NVIDIA GPU while still giving the UI useful progress updates.
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

router = APIRouter(prefix="/api/reconstruction", tags=["reconstruction"])
ROOT = Path(__file__).resolve().parents[2]
# Use a space-free path on Windows to prevent COLMAP and FFmpeg CLI path parsing issues
DATA_ROOT = Path("D:/spacegen_data/reconstruction")
try:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
except Exception:
    DATA_ROOT = ROOT / "data" / "reconstruction"

JOBS: dict[str, dict[str, Any]] = {}


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
    if job_id in JOBS:
        JOBS[job_id].update(values)


def _run(command: list[str], cwd: Path, job_id: str, step: str) -> None:
    """Run a local CLI command and stream the last line into job state."""
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


def _worker(job_id: str, video_path: Path, job_dir: Path) -> None:
    try:
        _update(job_id, status="running", progress=12, step="Extracting keyframes", log="Extracting high-density keyframes for COLMAP…")
        frames = job_dir / "frames"
        script = ROOT / "scripts" / "process_video.py"
        _run([sys.executable, str(script), str(video_path), str(frames), "--fps", "3", "--min-frames", "36", "--quality-threshold", "40"], ROOT, job_id, "Extracting keyframes")

        ns_process = _find_tool("ns-process-data")
        ns_train = _find_tool("ns-train")
        ns_export = _find_tool("ns-export")
        if not (ns_process and ns_train):
            _update(job_id, status="ready_for_training", progress=38,
                    step="Frames ready — install Nerfstudio to train",
                    log="Keyframes are ready. Install Nerfstudio, then restart the job from the terminal.",
                    frames_dir=str(frames))
            return

        processed = job_dir / "processed"
        output = job_dir / "output"
        _update(job_id, progress=45, step="Estimating camera poses", log="Running COLMAP feature extraction and bundle adjustment…")
        _run([ns_process, "images", "--data", str(frames), "--output-dir", str(processed), "--camera-type", "perspective"], ROOT, job_id, "Estimating camera poses")
        
        _update(job_id, progress=58, step="Training Gaussian Splatting", log="Training high-resolution splatfacto on GPU (15,000 steps)…")
        _run([
            ns_train, "splatfacto",
            "--data", str(processed),
            "--output-dir", str(output),
            "--max-num-iterations", "15000",
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
async def create_reconstruction_job(video: UploadFile = File(...)):
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
    JOBS[job_id] = {"job_id": job_id, "status": "queued", "progress": 4,
                    "step": "Queued", "log": "Video uploaded — waiting for the local worker…"}
    asyncio.create_task(asyncio.to_thread(_worker, job_id, video_path, job_dir))
    return JOBS[job_id]


from fastapi.responses import FileResponse


@router.get("/jobs/latest")
async def get_latest_reconstruction_job():
    """Get the most recent reconstruction job or check data directory for existing splats."""
    if JOBS:
        # Return most recently added job
        latest_job = list(JOBS.values())[-1]
        return latest_job
    
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


@router.get("/jobs/{job_id}/model")
async def get_reconstruction_model(job_id: str):
    """Serve the exported 3D Gaussian Splat PLY model for a reconstruction job."""
    job_dir = DATA_ROOT / job_id
    if not job_dir.exists():
        # Fallback to local ROOT / data / reconstruction if any
        fallback_dir = ROOT / "data" / "reconstruction" / job_id
        if fallback_dir.exists():
            job_dir = fallback_dir

    export_dir = job_dir / "export"
    for filename in ["splat.ply", "point_cloud.ply", "scene.spz"]:
        candidate = export_dir / filename
        if candidate.exists():
            return FileResponse(
                path=candidate,
                media_type="application/octet-stream",
                filename=filename,
                headers={"Access-Control-Allow-Origin": "*"},
            )
    
    # Check any .ply file in job directory
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
    if job_id not in JOBS:
        # Check disk
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
    return JOBS[job_id]
