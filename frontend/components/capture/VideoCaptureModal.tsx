'use client'

import { useEffect, useRef, useState } from 'react'
import { AlertCircle, CheckCircle2, Clapperboard, Cpu, Film, Loader2, Sparkles, Upload, X } from 'lucide-react'
import { api } from '@/lib/api'
import { ReconstructionJob } from '@/lib/types'
import { useAppStore } from '@/lib/store'

const steps = ['Upload video', 'Extract keyframes', 'Estimate camera poses', 'Train Gaussian Splatting', 'Scene ready']

export function VideoCaptureModal({ onClose }: { onClose: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [job, setJob] = useState<ReconstructionJob | null>(null)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState('')
  const { setSplatUrl } = useAppStore()

  useEffect(() => {
    if (!job || ['completed', 'failed', 'ready_for_training'].includes(job.status)) return
    const timer = window.setInterval(async () => {
      try {
        const updated = await api.getReconstructionJob(job.job_id)
        setJob(updated)
        if (updated.status === 'completed') {
          setSplatUrl(api.getReconstructionModelUrl(updated.job_id))
        }
      } catch { /* keep the last visible state */ }
    }, 1500)
    return () => window.clearInterval(timer)
  }, [job, setSplatUrl])

  const chooseFile = (candidate?: File) => {
    if (!candidate) return
    if (!candidate.type.startsWith('video/')) { setError('Please choose a video file.'); return }
    setError(''); setFile(candidate)
  }

  const start = async () => {
    if (!file) return
    setError('')
    try { setJob(await api.createReconstructionJob(file)) }
    catch { setError('The local API is unavailable. Start FastAPI on port 8000 and try again.') }
  }

  const handleLoadSplat = () => {
    if (job) {
      setSplatUrl(api.getReconstructionModelUrl(job.job_id))
    }
    onClose()
  }

  const currentStep = job ? Math.min(steps.length - 1, Math.max(0, Math.floor((job.progress / 100) * steps.length))) : 0

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6 backdrop-blur-sm">
      <div className="w-full max-w-2xl overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <div className="flex items-center gap-3"><div className="rounded-lg bg-accent/15 p-2 text-accent"><Clapperboard size={18} /></div><div><h2 className="font-semibold">Create a 3D scene</h2><p className="text-xs text-text-secondary">Local Gaussian Splatting pipeline</p></div></div>
          <button onClick={onClose} className="rounded-lg p-2 text-text-secondary hover:bg-surface-elevated hover:text-text-primary"><X size={18} /></button>
        </div>

        <div className="p-6">
          {!job ? <>
            <div className="mb-5 grid grid-cols-3 gap-3 text-xs text-text-secondary">
              <div className="rounded-lg border border-border bg-surface-elevated/40 p-3"><Film size={16} className="mb-2 text-accent" /><b className="block text-text-primary">Walkthrough video</b>MP4, MOV or WebM</div>
              <div className="rounded-lg border border-border bg-surface-elevated/40 p-3"><Cpu size={16} className="mb-2 text-accent" /><b className="block text-text-primary">Runs locally</b>GPU stays on your machine</div>
              <div className="rounded-lg border border-border bg-surface-elevated/40 p-3"><CheckCircle2 size={16} className="mb-2 text-accent" /><b className="block text-text-primary">Persistent scene</b>Keyframes + splat export</div>
            </div>
            <button type="button" onClick={() => inputRef.current?.click()} onDragOver={(e) => { e.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={(e) => { e.preventDefault(); setDragging(false); chooseFile(e.dataTransfer.files[0]) }} className={`flex w-full flex-col items-center justify-center rounded-xl border border-dashed px-6 py-12 transition-colors ${dragging ? 'border-accent bg-accent/10' : 'border-border hover:border-accent/60 hover:bg-surface-elevated/40'}`}>
              <Upload size={25} className="mb-3 text-accent" /><span className="font-medium">{file ? file.name : 'Drop a room video here'}</span><span className="mt-1 text-xs text-text-secondary">or click to browse · recommended 1080p · 20–90 seconds</span>
            </button>
            <input ref={inputRef} type="file" accept="video/*" className="hidden" onChange={(e) => chooseFile(e.target.files?.[0])} />
            {error && <p className="mt-3 flex items-center gap-2 text-xs text-red-400"><AlertCircle size={14} />{error}</p>}
            <div className="mt-5 flex items-center justify-between"><p className="max-w-md text-xs leading-5 text-text-secondary">Move slowly around the room and keep each wall in view. The local worker extracts sharp frames, estimates poses with COLMAP, then trains Nerfstudio splatfacto.</p><button onClick={start} disabled={!file} className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"><Cpu size={15} /> Start reconstruction</button></div>
          </> : <>
            <div className="mb-6 flex items-center justify-between"><div><p className="text-xs uppercase tracking-wider text-accent">Job {job.job_id}</p><h3 className="mt-1 text-lg font-semibold">{job.step}</h3></div><span className="font-mono text-2xl text-text-primary">{job.progress}%</span></div>
            <div className="mb-7 h-2 overflow-hidden rounded-full bg-surface-elevated"><div className="h-full rounded-full bg-accent transition-all duration-500" style={{ width: `${job.progress}%` }} /></div>
            <div className="space-y-3">{steps.map((step, index) => <div key={step} className="flex items-center gap-3 text-sm"><div className={`flex h-6 w-6 items-center justify-center rounded-full ${index < currentStep || job.status === 'completed' ? 'bg-emerald-500/15 text-emerald-400' : index === currentStep ? 'bg-accent/15 text-accent' : 'bg-surface-elevated text-text-secondary'}`}>{index < currentStep || job.status === 'completed' ? <CheckCircle2 size={14} /> : index === currentStep && job.status !== 'ready_for_training' && job.status !== 'failed' ? <Loader2 size={14} className="animate-spin" /> : index + 1}</div><span className={index <= currentStep ? 'text-text-primary' : 'text-text-secondary'}>{step}</span></div>)}</div>
            <div className="mt-6 rounded-lg border border-border bg-black/20 p-3 font-mono text-[11px] text-text-secondary">{job.log || 'Preparing local worker…'}</div>
            {job.status === 'ready_for_training' && <div className="mt-4 rounded-lg border border-amber-500/20 bg-amber-500/10 p-3 text-xs leading-5 text-amber-200">Frames are ready. Install Nerfstudio and COLMAP locally, then run <code>ns-train splatfacto</code> with the frames directory shown in the job response.</div>}
            {job.status === 'failed' && <p className="mt-4 text-xs text-red-400">The worker stopped. Check the backend terminal for the full command output.</p>}
            {job.status === 'completed' && (
              <div className="mt-6 flex gap-3">
                <button onClick={handleLoadSplat} className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-500 shadow-lg shadow-emerald-900/30">
                  <Sparkles size={16} /> View 3D Splat in Scene
                </button>
                <button onClick={onClose} className="rounded-lg border border-border px-5 py-2.5 text-sm hover:bg-surface-elevated">
                  Close
                </button>
              </div>
            )}
            {(job.status === 'ready_for_training' || job.status === 'failed') && <button onClick={onClose} className="mt-6 w-full rounded-lg border border-border py-2 text-sm hover:bg-surface-elevated">Close</button>}
          </>}
        </div>
      </div>
    </div>
  )
}
