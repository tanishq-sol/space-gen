'use client'

import { useAppStore } from '@/lib/store'
import { Box, Layers, BoxSelect, Trash2, Palette, ArrowRightLeft, Lightbulb, Flower2, ChevronRight } from 'lucide-react'
import { SceneObject } from '@/lib/types'
import { motion, AnimatePresence } from 'framer-motion'
import { useState } from 'react'

const CATEGORY_CONFIG: Record<string, { label: string; icon: React.ReactNode; color: string }> = {
  architecture: { label: 'Architecture', icon: <Box size={12} />, color: 'text-blue-400' },
  furniture: { label: 'Furniture', icon: <BoxSelect size={12} />, color: 'text-amber-400' },
  lighting: { label: 'Lighting', icon: <Lightbulb size={12} />, color: 'text-yellow-300' },
  decor: { label: 'Decor', icon: <Flower2 size={12} />, color: 'text-emerald-400' },
}

export function ScenePanel() {
  const { scene, selectedObjectId, setSelectedObjectId } = useAppStore()
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set(['furniture', 'architecture']))

  const categories: Record<string, SceneObject[]> = {
    architecture: scene?.objects.filter(o => o.type === 'architecture') || [],
    furniture: scene?.objects.filter(o => o.type === 'furniture') || [],
    lighting: scene?.objects.filter(o => o.type === 'lighting') || [],
    decor: scene?.objects.filter(o => o.type === 'decor') || [],
  }

  const selectedObject = scene?.objects.find(o => o.entity_id === selectedObjectId)
  const totalObjects = scene?.objects?.length || 0

  const toggleCategory = (cat: string) => {
    setExpandedCategories(prev => {
      const next = new Set(prev)
      if (next.has(cat)) next.delete(cat)
      else next.add(cat)
      return next
    })
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-border flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="w-6 h-6 rounded-lg bg-surface-elevated flex items-center justify-center border border-border">
            <Layers size={12} className="text-text-secondary" />
          </div>
          <div>
            <h2 className="font-semibold text-sm leading-tight">Scene Graph</h2>
            <p className="text-[10px] text-text-muted leading-tight">{totalObjects} objects detected</p>
          </div>
        </div>
        {scene?.room_type && (
          <span className="badge-accent">{scene.room_type}</span>
        )}
      </div>

      {/* Object tree */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {Object.entries(categories).map(([type, objects]) => {
          if (objects.length === 0) return null
          const config = CATEGORY_CONFIG[type]
          const isExpanded = expandedCategories.has(type)
          
          return (
            <div key={type}>
              {/* Category header */}
              <button
                onClick={() => toggleCategory(type)}
                className="w-full flex items-center gap-2 px-2 py-1.5 text-xs font-semibold text-text-muted uppercase tracking-wider hover:text-text-secondary transition-colors rounded-md hover:bg-surface-elevated/50"
              >
                <ChevronRight 
                  size={12} 
                  className={`transition-transform duration-200 ${isExpanded ? 'rotate-90' : ''}`} 
                />
                <span className={config.color}>{config.icon}</span>
                <span>{config.label}</span>
                <span className="ml-auto text-[10px] font-mono text-text-muted bg-surface-elevated px-1.5 py-0.5 rounded">
                  {objects.length}
                </span>
              </button>

              {/* Objects in category */}
              <AnimatePresence>
                {isExpanded && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden ml-4 space-y-0.5"
                  >
                    {objects.map((obj) => (
                      <motion.button
                        key={obj.entity_id}
                        whileHover={{ x: 2 }}
                        onClick={() => setSelectedObjectId(obj.entity_id)}
                        className={`w-full flex items-center gap-2 px-2.5 py-1.5 text-sm rounded-lg transition-all duration-150 ${
                          selectedObjectId === obj.entity_id 
                            ? 'bg-accent/15 text-accent-light border border-accent/25 shadow-sm shadow-accent/10' 
                            : 'hover:bg-surface-elevated text-text-primary border border-transparent'
                        }`}
                      >
                        <span className={`text-xs ${config.color}`}>{config.icon}</span>
                        <span className="truncate text-xs">{obj.name || obj.category}</span>
                        {obj.material?.color && (
                          <div 
                            className="ml-auto w-3 h-3 rounded-full border border-border/60 shrink-0 shadow-sm" 
                            style={{ backgroundColor: obj.material.color }}
                          />
                        )}
                        {obj.confidence < 0.8 && (
                          <span className="text-[9px] text-warning">⚠</span>
                        )}
                      </motion.button>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )
        })}

        {totalObjects === 0 && (
          <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
            <div className="w-12 h-12 rounded-xl bg-surface-elevated flex items-center justify-center mb-3 border border-border">
              <Layers size={20} className="text-text-muted" />
            </div>
            <p className="text-sm text-text-secondary font-medium">No scene loaded</p>
            <p className="text-xs text-text-muted mt-1">Upload a video to start</p>
          </div>
        )}
      </div>

      {/* Selected object details */}
      <AnimatePresence>
        {selectedObject && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="border-t border-border shrink-0 overflow-hidden"
          >
            <ObjectDetails object={selectedObject} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function ObjectDetails({ object }: { object: SceneObject }) {
  return (
    <div className="p-4 space-y-3">
      {/* Name + type */}
      <div className="flex items-center justify-between">
        <h3 className="font-medium text-sm truncate">{object.name || object.category}</h3>
        <span className="badge-accent">{object.category}</span>
      </div>

      {/* Confidence bar */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-[11px]">
          <span className="text-text-muted">AI Confidence</span>
          <span className={`font-mono font-medium ${object.confidence >= 0.9 ? 'text-success' : object.confidence >= 0.7 ? 'text-warning' : 'text-error'}`}>
            {Math.round(object.confidence * 100)}%
          </span>
        </div>
        <div className="w-full h-1 bg-surface-elevated rounded-full overflow-hidden">
          <div 
            className={`h-full rounded-full transition-all ${
              object.confidence >= 0.9 ? 'bg-success' : object.confidence >= 0.7 ? 'bg-warning' : 'bg-error'
            }`}
            style={{ width: `${object.confidence * 100}%` }}
          />
        </div>
      </div>

      {/* Properties */}
      <div className="space-y-1.5 text-[11px]">
        <PropertyRow label="Material" value={object.material?.type || 'Unknown'} />
        <PropertyRow label="Color" value={object.material?.color || 'Unknown'}>
          {object.material?.color && (
            <div 
              className="w-3 h-3 rounded border border-border/60" 
              style={{ backgroundColor: object.material.color }}
            />
          )}
        </PropertyRow>
        <PropertyRow label="Finish" value={object.material?.finish || '—'} />
        {object.dimensions && (
          <PropertyRow 
            label="Size" 
            value={`${object.dimensions.width_m}×${object.dimensions.depth_m || object.dimensions.width_m}×${object.dimensions.height_m}m`} 
          />
        )}
      </div>

      {/* Action buttons */}
      {object.editable && (
        <div className="grid grid-cols-2 gap-1.5 pt-1">
          <button className="btn-secondary text-xs py-1.5 text-[11px]">
            <ArrowRightLeft size={11} /> Replace
          </button>
          <button className="btn-secondary text-xs py-1.5 text-[11px]">
            <Palette size={11} /> Restyle
          </button>
          <button className="col-span-2 btn-danger text-xs py-1.5 text-[11px]">
            <Trash2 size={11} /> Remove
          </button>
        </div>
      )}
    </div>
  )
}

function PropertyRow({ label, value, children }: { label: string; value: string; children?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-0.5">
      <span className="text-text-muted">{label}</span>
      <div className="flex items-center gap-1.5">
        {children}
        <span className="text-text-secondary font-medium">{value}</span>
      </div>
    </div>
  )
}
