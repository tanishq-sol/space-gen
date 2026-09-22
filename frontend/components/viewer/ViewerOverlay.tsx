'use client'

import { motion, AnimatePresence } from 'framer-motion'
import { 
  Loader2, Sparkles, Layers, Camera, Keyboard, 
  Footprints, Navigation, Eye, Gauge, ChevronUp,
  AlertTriangle, X, Box, Wand2, Download, Check
} from 'lucide-react'
import { useState } from 'react'
import { useAppStore } from '@/lib/store'
import { api } from '@/lib/api'
import { CameraMode } from './CameraController'
import { QualityTier } from './QualityManager'

interface ViewerOverlayProps {
  // Loading state
  loadProgress: number | null
  splatCount: number | null
  loadError: string | null
  onDismissError: () => void

  // Controls state
  splatUrl: string | null
  showSplat: boolean
  showBoxes: boolean
  onToggleSplat: () => void
  onToggleBoxes: () => void

  // Camera
  cameraMode: CameraMode
  onCameraMode: (mode: CameraMode) => void

  // Quality
  quality: QualityTier
  fps: number
  onQualityChange: (q: QualityTier) => void

  // Actions
  onScreenshot: () => void

  // Shortcuts
  showShortcuts: boolean
  onToggleShortcuts: () => void
}

export function ViewerOverlay(props: ViewerOverlayProps) {
  const {
    loadProgress, splatCount, loadError, onDismissError,
    splatUrl, showSplat, showBoxes, onToggleSplat, onToggleBoxes,
    cameraMode, onCameraMode,
    quality, fps, onQualityChange,
    onScreenshot,
    showShortcuts, onToggleShortcuts,
  } = props

  const {
    viewMode,
    setViewMode,
    isConvertingMesh,
    setIsConvertingMesh,
    convertProgress,
    setConvertProgress,
    meshManifest,
    setMeshManifest,
    objectTransforms,
    objectReplacements,
  } = useAppStore()

  const [isExporting, setIsExporting] = useState(false)

  const handleConvertToMesh = async () => {
    const match = splatUrl?.match(/jobs\/([^\/]+)/)
    const jobId = match ? match[1] : '44a1897d1ca1'
    setIsConvertingMesh(true)
    setConvertProgress(25)
    try {
      const res = await api.convertToMesh(jobId)
      setConvertProgress(90)
      if (res.manifest) {
        setMeshManifest(res.manifest)
      }
      setViewMode('mesh')
    } catch (e: any) {
      console.error('Mesh conversion failed:', e)
      alert(`Mesh conversion error: ${e.message}`)
    } finally {
      setIsConvertingMesh(false)
      setConvertProgress(null)
    }
  }

  const handleExportScene = async () => {
    const match = splatUrl?.match(/jobs\/([^\/]+)/)
    const jobId = match ? match[1] : '44a1897d1ca1'
    setIsExporting(true)
    try {
      const res = await api.exportModifiedScene(jobId, objectTransforms, objectReplacements)
      if (res.url) {
        const a = document.createElement('a')
        a.href = res.url
        a.download = res.filename || 'modified_scene.glb'
        a.click()
      }
    } catch (e: any) {
      console.error('Export failed:', e)
      alert(`Scene export error: ${e.message}`)
    } finally {
      setIsExporting(false)
    }
  }

  const fpsColor = fps >= 50 ? 'text-emerald-400' : fps >= 30 ? 'text-yellow-400' : 'text-red-400'

  return (
    <>
      {/* ---- Top Center: Mode Switch & Mesh Actions ---- */}
      <div className="absolute top-4 left-1/2 -translate-x-1/2 flex items-center gap-2.5 z-20">
        {/* Dual Mode Switcher Pill */}
        <div className="flex items-center gap-1 p-1 glass rounded-2xl border border-border/60 shadow-xl backdrop-blur-xl">
          <button
            onClick={() => setViewMode('splat')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-all ${
              viewMode === 'splat'
                ? 'bg-accent text-white shadow-md shadow-accent/30'
                : 'text-text-secondary hover:text-text-primary hover:bg-surface-elevated'
            }`}
          >
            <Sparkles size={13} />
            <span>Splat View</span>
          </button>

          <button
            onClick={() => setViewMode('mesh')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-all ${
              viewMode === 'mesh'
                ? 'bg-accent text-white shadow-md shadow-accent/30'
                : 'text-text-secondary hover:text-text-primary hover:bg-surface-elevated'
            }`}
          >
            <Box size={13} />
            <span>Solid Mesh</span>
          </button>
        </div>

        {/* 1-Click Convert to Mesh Action Button */}
        {viewMode === 'splat' && (
          <button
            onClick={handleConvertToMesh}
            disabled={isConvertingMesh}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-medium bg-gradient-to-r from-amber-500/20 to-orange-500/20 hover:from-amber-500/30 hover:to-orange-500/30 border border-amber-500/40 text-amber-300 backdrop-blur-xl transition-all shadow-lg active:scale-95 disabled:opacity-50"
          >
            {isConvertingMesh ? (
              <>
                <Loader2 size={13} className="animate-spin text-amber-400" />
                <span>Converting Mesh...</span>
              </>
            ) : (
              <>
                <Wand2 size={13} className="text-amber-400" />
                <span>Convert to Solid Mesh</span>
              </>
            )}
          </button>
        )}

        {/* Export Modified Scene (.glb) Action Button */}
        {viewMode === 'mesh' && (
          <button
            onClick={handleExportScene}
            disabled={isExporting}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-medium bg-gradient-to-r from-emerald-500/20 to-teal-500/20 hover:from-emerald-500/30 hover:to-teal-500/30 border border-emerald-500/40 text-emerald-300 backdrop-blur-xl transition-all shadow-lg active:scale-95 disabled:opacity-50"
          >
            {isExporting ? (
              <>
                <Loader2 size={13} className="animate-spin text-emerald-400" />
                <span>Exporting Scene...</span>
              </>
            ) : (
              <>
                <Download size={13} className="text-emerald-400" />
                <span>Export Scene (.glb)</span>
              </>
            )}
          </button>
        )}
      </div>

      {/* ---- Mesh Conversion Active Progress Banner ---- */}
      <AnimatePresence>
        {isConvertingMesh && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="absolute top-16 left-1/2 -translate-x-1/2 z-20"
          >
            <div className="flex items-center gap-3 px-5 py-2.5 glass rounded-full shadow-2xl border border-amber-500/30">
              <Loader2 size={14} className="animate-spin text-amber-400" />
              <span className="text-xs font-medium text-amber-200">Reconstructing Watertight Solid Mesh...</span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ---- Loading progress ---- */}
      <AnimatePresence>
        {loadProgress !== null && (
          <motion.div 
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="absolute top-16 left-1/2 -translate-x-1/2 z-10"
          >
            <div className="flex items-center gap-3 px-5 py-2.5 glass rounded-full shadow-2xl">
              <Loader2 size={14} className="animate-spin text-accent" />
              <span className="text-xs font-medium">Loading 3D Scene</span>
              <div className="w-24 h-1.5 bg-surface-elevated rounded-full overflow-hidden">
                <motion.div 
                  className="h-full bg-gradient-brand rounded-full"
                  initial={{ width: '0%' }}
                  animate={{ width: `${loadProgress}%` }}
                  transition={{ ease: 'easeOut' }}
                />
              </div>
              <span className="text-xs font-mono text-text-secondary">{loadProgress}%</span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ---- Load error ---- */}
      <AnimatePresence>
        {loadError && (
          <motion.div 
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="absolute top-4 left-1/2 -translate-x-1/2 z-10"
          >
            <div className="flex items-center gap-2 px-4 py-2 bg-error/10 backdrop-blur-xl rounded-full border border-error/30 text-xs text-error">
              <AlertTriangle size={14} />
              <span>Failed to load scene</span>
              <button onClick={onDismissError} className="hover:text-error/60 transition-colors">
                <X size={14} />
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ---- Top-left status badge ---- */}
      {splatUrl && splatCount !== null && !loadProgress && (
        <div className="absolute top-4 left-4 flex items-center gap-2 px-3 py-1.5 glass rounded-lg text-[11px] text-text-secondary z-10">
          <div className="h-2 w-2 rounded-full bg-emerald-400 shadow-sm shadow-emerald-400/50 animate-pulse" />
          <span>
            {splatUrl.toLowerCase().includes('.obj') || splatUrl.toLowerCase().includes('.glb') || splatUrl.toLowerCase().includes('.gltf')
              ? '3D Mesh'
              : 'Gaussian Splat'} · <b className="text-text-primary">{splatCount.toLocaleString()}</b> {splatUrl.toLowerCase().includes('.obj') || splatUrl.toLowerCase().includes('.glb') ? 'vertices' : 'splats'}
          </span>
        </div>
      )}

      {/* ---- Top-right FPS + Quality ---- */}
      {splatCount !== null && (
        <div className="absolute top-4 right-4 flex items-center gap-2 z-10">
          <div className="flex items-center gap-2 px-3 py-1.5 glass rounded-lg text-[11px]">
            <Gauge size={12} className="text-text-muted" />
            <span className={`font-mono font-bold ${fpsColor}`}>{fps}</span>
            <span className="text-text-muted">FPS</span>
          </div>
          <select
            value={quality}
            onChange={(e) => onQualityChange(e.target.value as QualityTier)}
            className="px-2 py-1.5 glass rounded-lg text-[11px] text-text-secondary bg-transparent border-0 focus:outline-none cursor-pointer"
          >
            <option value="max" className="bg-surface">⭐ Maximum</option>
            <option value="balanced" className="bg-surface">⚡ Balanced</option>
            <option value="performance" className="bg-surface">🚀 Performance</option>
          </select>
        </div>
      )}

      {/* ---- Camera mode indicator (walk/fly) ---- */}
      <AnimatePresence>
        {cameraMode !== 'orbit' && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="absolute top-14 left-1/2 -translate-x-1/2 z-10"
          >
            <div className="flex items-center gap-2 px-4 py-2 glass rounded-full text-xs">
              {cameraMode === 'walk' ? (
                <Footprints size={14} className="text-accent" />
              ) : (
                <Navigation size={14} className="text-accent" />
              )}
              <span className="font-medium">
                {cameraMode === 'walk' ? 'Walk Mode' : 'Fly Mode'}
              </span>
              <span className="text-text-muted">
                WASD + Mouse · Scroll = Speed · ESC = Exit
              </span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ---- Bottom control bar ---- */}
      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-10">
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center gap-1.5 p-1.5 glass rounded-xl shadow-2xl"
        >
          {/* Splat toggle */}
          {splatUrl && (
            <ControlBtn
              active={showSplat}
              onClick={onToggleSplat}
              icon={<Sparkles size={13} />}
              label="Splat"
              shortcut="S"
            />
          )}

          {/* Boxes toggle */}
          <ControlBtn
            active={showBoxes}
            onClick={onToggleBoxes}
            icon={<Layers size={13} />}
            label="Objects"
            shortcut="B"
          />

          <Divider />

          {/* Camera modes */}
          <ControlBtn
            active={cameraMode === 'orbit'}
            onClick={() => onCameraMode('orbit')}
            icon={<Eye size={13} />}
            label="Orbit"
            shortcut="O"
          />
          <ControlBtn
            active={cameraMode === 'walk'}
            onClick={() => onCameraMode('walk')}
            icon={<Footprints size={13} />}
            label="Walk"
            shortcut="W"
          />
          <ControlBtn
            active={cameraMode === 'fly'}
            onClick={() => onCameraMode('fly')}
            icon={<Navigation size={13} />}
            label="Fly"
            shortcut="F"
          />

          <Divider />

          {/* Screenshot */}
          <ControlBtn
            active={false}
            onClick={onScreenshot}
            icon={<Camera size={13} />}
            label="Capture"
            shortcut="C"
          />

          {/* Shortcuts help */}
          <ControlBtn
            active={showShortcuts}
            onClick={onToggleShortcuts}
            icon={<Keyboard size={13} />}
            label=""
            shortcut="?"
          />
        </motion.div>
      </div>

      {/* ---- Keyboard shortcuts panel ---- */}
      <AnimatePresence>
        {showShortcuts && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            className="absolute bottom-20 left-1/2 -translate-x-1/2 z-20 p-4 glass rounded-xl shadow-2xl text-xs min-w-[240px]"
          >
            <div className="font-semibold text-text-primary mb-3">Keyboard Shortcuts</div>
            <div className="space-y-2 text-text-secondary">
              <ShortcutSection title="Display">
                <ShortcutRow keys="S" desc="Toggle Gaussian Splat" />
                <ShortcutRow keys="B" desc="Toggle bounding boxes" />
              </ShortcutSection>
              <ShortcutSection title="Camera">
                <ShortcutRow keys="O" desc="Orbit mode" />
                <ShortcutRow keys="W" desc="Walk mode (first-person)" />
                <ShortcutRow keys="F" desc="Fly mode (free camera)" />
                <ShortcutRow keys="ESC" desc="Exit walk/fly mode" />
              </ShortcutSection>
              <ShortcutSection title="Walk / Fly Controls">
                <ShortcutRow keys="WASD" desc="Move" />
                <ShortcutRow keys="Mouse" desc="Look around" />
                <ShortcutRow keys="Space" desc="Move up" />
                <ShortcutRow keys="Shift" desc="Move down" />
                <ShortcutRow keys="Scroll" desc="Adjust speed" />
              </ShortcutSection>
              <ShortcutSection title="3D Object Editing (Mesh Mode)">
                <ShortcutRow keys="Click" desc="Select object (e.g. Bed, Sofa)" />
                <ShortcutRow keys="W" desc="Translate / Move along X, Y, Z" />
                <ShortcutRow keys="E" desc="Rotate object" />
                <ShortcutRow keys="R" desc="Scale / Resize" />
                <ShortcutRow keys="ESC" desc="Deselect object" />
                <ShortcutRow keys="DEL" desc="Delete selected object" />
              </ShortcutSection>
              <ShortcutSection title="Actions">
                <ShortcutRow keys="C" desc="Capture screenshot" />
                <ShortcutRow keys="?" desc="Toggle shortcuts" />
              </ShortcutSection>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}

/* ---- Sub-components ---- */

function ControlBtn({ active, onClick, icon, label, shortcut }: {
  active: boolean; onClick: () => void; icon: React.ReactNode; label: string; shortcut: string
}) {
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onClick() }}
      title={label ? `${label} (${shortcut})` : shortcut}
      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 ${
        active 
          ? 'bg-accent/90 text-white shadow-sm shadow-accent/30' 
          : 'hover:bg-surface-hover text-text-secondary hover:text-text-primary'
      }`}
    >
      {icon}
      {label && <span>{label}</span>}
    </button>
  )
}

function Divider() {
  return <div className="w-px h-6 bg-border/50 mx-0.5" />
}

function ShortcutSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-text-muted font-semibold mb-1">{title}</div>
      <div className="space-y-1">{children}</div>
    </div>
  )
}

function ShortcutRow({ keys, desc }: { keys: string; desc: string }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span>{desc}</span>
      <kbd className="px-1.5 py-0.5 bg-surface-elevated rounded border border-border font-mono text-[10px] text-text-muted">{keys}</kbd>
    </div>
  )
}
