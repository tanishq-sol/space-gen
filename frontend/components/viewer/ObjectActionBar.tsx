'use client'

import React from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { 
  Move, 
  RotateCw, 
  Maximize2, 
  RefreshCw, 
  Sparkles, 
  Trash2, 
  X,
  Layers
} from 'lucide-react'
import { useAppStore } from '@/lib/store'

export function ObjectActionBar() {
  const {
    scene,
    selectedObjectId,
    gizmoMode,
    objectReplacements,
    setGizmoMode,
    setSelectedObjectId,
    resetObjectTransform,
    deleteObject,
    setShowReplacementModal,
  } = useAppStore()

  if (!selectedObjectId) return null

  const selectedObj = scene?.objects?.find((o) => o.entity_id === selectedObjectId)
  const objName = objectReplacements[selectedObjectId]?.name || selectedObj?.name || selectedObj?.category || 'Object'
  const objCategory = selectedObj?.category || 'furniture'

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 30, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 20, scale: 0.95 }}
        className="absolute bottom-20 left-1/2 -translate-x-1/2 z-30 pointer-events-auto"
      >
        <div className="flex items-center gap-1.5 p-2 glass rounded-2xl border border-border shadow-2xl backdrop-blur-xl">
          {/* Object Badge */}
          <div className="flex items-center gap-2 pl-2 pr-3 py-1 border-r border-border/60 mr-1">
            <div className="h-2 w-2 rounded-full bg-accent animate-pulse" />
            <div className="flex flex-col">
              <span className="text-xs font-semibold text-text-primary capitalize leading-tight">{objName}</span>
              <span className="text-[10px] text-text-muted capitalize">{objCategory}</span>
            </div>
          </div>

          {/* Transform Modes: Translate (W), Rotate (E), Scale (R) */}
          <div className="flex items-center gap-1 bg-surface/60 p-0.5 rounded-xl border border-border/40">
            <button
              onClick={() => setGizmoMode('translate')}
              title="Translate (W) - Move along X, Y, Z axes"
              className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
                gizmoMode === 'translate'
                  ? 'bg-accent text-white shadow-md shadow-accent/30'
                  : 'text-text-secondary hover:text-text-primary hover:bg-surface-elevated'
              }`}
            >
              <Move size={13} />
              <span>Move</span>
              <span className="text-[9px] opacity-60 font-mono">W</span>
            </button>

            <button
              onClick={() => setGizmoMode('rotate')}
              title="Rotate (E) - Turn across all angles"
              className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
                gizmoMode === 'rotate'
                  ? 'bg-accent text-white shadow-md shadow-accent/30'
                  : 'text-text-secondary hover:text-text-primary hover:bg-surface-elevated'
              }`}
            >
              <RotateCw size={13} />
              <span>Rotate</span>
              <span className="text-[9px] opacity-60 font-mono">E</span>
            </button>

            <button
              onClick={() => setGizmoMode('scale')}
              title="Scale (R) - Resize object"
              className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
                gizmoMode === 'scale'
                  ? 'bg-accent text-white shadow-md shadow-accent/30'
                  : 'text-text-secondary hover:text-text-primary hover:bg-surface-elevated'
              }`}
            >
              <Maximize2 size={13} />
              <span>Scale</span>
              <span className="text-[9px] opacity-60 font-mono">R</span>
            </button>
          </div>

          {/* Action: Replace Object */}
          <button
            onClick={() => setShowReplacementModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium bg-gradient-to-r from-accent/90 to-purple-600/90 text-white shadow-lg shadow-accent/25 hover:brightness-110 active:scale-95 transition-all ml-1"
          >
            <Sparkles size={13} />
            <span>Replace Model</span>
          </button>

          {/* Action: Reset Transform */}
          <button
            onClick={() => resetObjectTransform(selectedObjectId)}
            title="Reset position and rotation to default"
            className="p-1.5 rounded-xl text-text-secondary hover:text-text-primary hover:bg-surface-elevated transition-colors"
          >
            <RefreshCw size={14} />
          </button>

          {/* Action: Delete Object */}
          <button
            onClick={() => deleteObject(selectedObjectId)}
            title="Delete this object (Del)"
            className="p-1.5 rounded-xl text-text-muted hover:text-error hover:bg-error/10 transition-colors"
          >
            <Trash2 size={14} />
          </button>

          {/* Action: Deselect */}
          <button
            onClick={() => setSelectedObjectId(null)}
            title="Deselect (Esc)"
            className="p-1.5 rounded-xl text-text-muted hover:text-text-primary hover:bg-surface-elevated transition-colors"
          >
            <X size={14} />
          </button>
        </div>
      </motion.div>
    </AnimatePresence>
  )
}
