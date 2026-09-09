# SpaceGen AI

**The AI-native spatial design platform that turns real physical environments into persistent, conversationally editable digital twins.**

> Capture → Reconstruct → Understand → Select → Ask → Generate → Validate → Explore → Compare → Present

## Architecture

```
frontend/    → Next.js 15 + React Three Fiber (3D editor + design UI)
backend/     → FastAPI + Gemini AI (intelligence layer + API)
scripts/     → Video processing + reconstruction helpers
```

## Quick Start — local hackathon setup

### 1. Backend API

```bash
cd backend
python -m venv venv
venv\Scripts\activate       # Windows
pip install -r requirements.txt
cp .env.example .env        # Add your GEMINI_API_KEY
uvicorn main:app --reload --port 8000
```

### 2. Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

### 3. Enable local Gaussian Splatting training

The editor now has an **Import capture** button in the top bar. Upload a slow walkthrough video and the API will:

```text
video → quality-scored keyframes → COLMAP camera poses → Nerfstudio splatfacto → exported Gaussian Splat
```

For the complete local path, install the reconstruction tools in the same environment as the backend:

```bash
pip install nerfstudio
```

Install COLMAP separately and make sure `colmap`, `ns-process-data`, `ns-train`, and `ns-export` are on PATH. An NVIDIA GPU with 12 GB+ VRAM is recommended. The default hackathon run trains 30,000 iterations and writes artifacts under `data/reconstruction/<job-id>/`.

If Nerfstudio is not installed, the upload still runs the OpenCV keyframe extraction and reports `Frames ready — install Nerfstudio to train`; this is useful for frontend/API work without a GPU.

You can also run the frame extractor directly:

```bash
python scripts/process_video.py room.mp4 data/frames/ --fps 2
```

### 4. Capture guidance

- 1080p or higher, 20–90 seconds, 30 fps is a good default.
- Move slowly, keep the camera level, and overlap adjacent views.
- Avoid moving people, reflections, very dark rooms, and rapid pans.
- Walk around the room perimeter and include each wall, windows, and doors.

### 5. Pre-requisites

- Python 3.12+
- Node.js 20+
- Gemini API key ([Get one here](https://aistudio.google.com/apikey)) for the AI design features
- OpenCV + NumPy (installed by `backend/requirements.txt`) for video ingestion

