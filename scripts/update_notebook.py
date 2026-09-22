import json
from pathlib import Path

nb_path = Path("SpaceGen_Colab_GPU_Backend.ipynb")
with open(nb_path, "r", encoding="utf-8") as f:
    nb = json.load(f)

cell1_source = """#@title Cell 1 — Install COLMAP + gsplat + Gaussian Splatting + Cloudflare Tunnel
import os, subprocess, sys

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['DISPLAY'] = ''

print('📦 [1/6] Installing system packages (COLMAP, FFmpeg)...')
!apt-get update -qq 2>&1 | tail -1
!apt-get install -y -qq colmap ffmpeg > /dev/null 2>&1
print('✅ COLMAP + FFmpeg installed')

print('📦 [2/6] Installing Python packages...')
!pip install -q plyfile tqdm pillow fastapi uvicorn python-multipart > /dev/null 2>&1
print('✅ FastAPI + PLY tools installed')

print('📦 [3/6] Installing gsplat (Fast CUDA Rasterizer & Compression Engine)...')
!pip install -q gsplat -f https://docs.gsplat.studio/whl/pt22cu121/ || pip install -q gsplat
print('✅ gsplat installed')

print('📦 [4/6] Cloning Gaussian Splatting repo...')
GS_DIR = '/content/gaussian-splatting'
if not os.path.exists(GS_DIR):
    !git clone --recursive https://github.com/camenduru/gaussian-splatting {GS_DIR} 2>&1 | tail -2 || git clone --recursive https://github.com/graphdeco-inria/gaussian-splatting {GS_DIR} 2>&1 | tail -2
else:
    print('   (already cloned)')
print('✅ Repo ready')

print('📦 [5/6] Installing Gaussian Splatting Python dependencies...')
!pip install -q lpips tensorboard > /dev/null 2>&1
!cd {GS_DIR} && pip install -q -e . 2>&1 | tail -2 || true
!pip install -q {GS_DIR}/submodules/diff-gaussian-rasterization 2>&1 | tail -1 || true
!pip install -q {GS_DIR}/submodules/simple-knn 2>&1 | tail -1 || true
print('✅ CUDA kernels compiled / ready')

print('📦 [6/6] Installing Cloudflare Tunnel...')
if not os.path.exists('/usr/local/bin/cloudflared'):
    !wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
    !dpkg -i cloudflared-linux-amd64.deb > /dev/null 2>&1
    !rm -f cloudflared-linux-amd64.deb
print('✅ Cloudflare installed')

print('\\n🎉 Environment ready! Now run Cell 2.')
"""

# Read existing cell 2 source
c2_old = "".join(nb["cells"][2]["source"])

# Enhance cell 2 with gsplat compression and models endpoint
enhancement_code = """
    # -----------------------------------------------------------------------
    # Step 4: gsplat compression & multi-format packaging
    # -----------------------------------------------------------------------
    print(' [4/4] Optimizing & compressing with gsplat...')
    update_job(job_id, progress=92, step='Optimizing splats', log='Compressing splat stream for 60-144 FPS web viewing…')
    
    src_ply = model_dir / 'point_cloud' / f'iteration_{iterations}' / 'point_cloud.ply'
    if not src_ply.exists():
        plys = list(model_dir.glob('**/*.ply'))
        if plys:
            src_ply = plys[-1]

    if src_ply.exists():
        shutil.copy2(str(src_ply), str(export_dir / 'splat.ply'))
        try:
            import torch, gsplat
            from plyfile import PlyData
            import numpy as np

            ply = PlyData.read(str(src_ply))
            v = ply['vertex']
            means = torch.from_numpy(np.stack([v['x'], v['y'], v['z']], axis=-1).astype(np.float32))
            scales = torch.exp(torch.from_numpy(np.stack([v['scale_0'], v['scale_1'], v['scale_2']], axis=-1).astype(np.float32)))
            quats = torch.from_numpy(np.stack([v['rot_0'], v['rot_1'], v['rot_2'], v['rot_3']], axis=-1).astype(np.float32))
            quats = quats / torch.clamp(torch.norm(quats, dim=-1, keepdim=True), min=1e-8)
            opacities = torch.sigmoid(torch.from_numpy(v['opacity'].astype(np.float32)))
            sh0 = torch.from_numpy(np.stack([v['f_dc_0'], v['f_dc_1'], v['f_dc_2']], axis=-1).astype(np.float32)).unsqueeze(1)
            sh_names = sorted([p.name for p in v.properties if p.name.startswith('f_rest_')], key=lambda x: int(x.split('_')[-1]))
            if sh_names:
                shN = torch.from_numpy(np.stack([v[name] for name in sh_names], axis=-1).astype(np.float32)).reshape(len(means), -1, 3)
            else:
                shN = torch.zeros((len(means), 0, 3), dtype=torch.float32)

            splat_bytes = gsplat.export_splats(means, scales, quats, opacities, sh0, shN, format='splat')
            (export_dir / 'scene.splat').write_bytes(splat_bytes)
            print(f'✅ gsplat scene.splat compressed ({len(splat_bytes)/(1024*1024):.2f} MB, {len(means):,} splats)')
        except Exception as e:
            print(f'gsplat export warning: {e}')
"""

# Replace old export step in Cell 2 if present
if "src_ply = model_dir / 'point_cloud'" in c2_old:
    # replace that section
    idx = c2_old.find("src_ply = model_dir / 'point_cloud'")
    # find end of block before update_job completed
    end_idx = c2_old.find("update_job(job_id, status='completed'", idx)
    if end_idx != -1:
        c2_new = c2_old[:idx] + enhancement_code.strip() + "\n    " + c2_old[end_idx:]
    else:
        c2_new = c2_old
else:
    c2_new = c2_old

# Also add /models endpoint to cell 2 if not present
if "@app.get('/api/reconstruction/models')" not in c2_new:
    models_endpoint = """
@app.get('/api/reconstruction/models')
async def list_models():
    results = []
    for jd in sorted(DATA_ROOT.iterdir(), key=lambda d: d.stat().st_mtime, reverse=True):
        if not jd.is_dir(): continue
        exp = jd / 'export'
        for cand in ['scene.splat', 'splat.ply']:
            f = exp / cand
            if f.exists():
                results.append({
                    'job_id': jd.name,
                    'filename': f.name,
                    'size_mb': round(f.stat().st_size / (1024*1024), 2),
                    'format': f.suffix.replace('.', ''),
                    'url': f'/api/reconstruction/jobs/{jd.name}/model/{f.name}',
                    'modified': f.stat().st_mtime
                })
                break
    return results
"""
    # Insert before @app.get('/health')
    h_idx = c2_new.find("@app.get('/health')")
    if h_idx != -1:
        c2_new = c2_new[:h_idx] + models_endpoint + "\n" + c2_new[h_idx:]

nb["cells"][1]["source"] = [line + "\n" for line in cell1_source.splitlines()]
nb["cells"][2]["source"] = [line + "\n" for line in c2_new.splitlines()]

with open(nb_path, "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1)

print("SpaceGen_Colab_GPU_Backend.ipynb updated successfully!")
