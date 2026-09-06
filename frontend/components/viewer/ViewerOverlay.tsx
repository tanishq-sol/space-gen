'use client'

import { motion, AnimatePresence } from 'framer-motion'
import { 
  Loader2, Sparkles, Layers, Camera, Keyboard, 
  Footprints, Navigation, Eye, Gauge, ChevronUp,
  AlertTriangle, X
} from 'lucide-react'
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

  const fpsColor = fps >= 50 ? 'text-emerald-400' : fps >= 30 ? 'text-yellow-400' : 'text-red-400'

  return (
    <>
      {/* ---- Loading progress ---- */}
      <AnimatePresence>
        {loadProgress !== null && (
          <motion.div 
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="absolute top-4 left-1/2 -translate-x-1/2 z-10"
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
            Gaussian Splat · <b className="text-text-primary">{splatCount.toLocaleString()}</b> splats
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
