'use client'

import { useAppStore } from '@/lib/store'
import { Box, Layers, BoxSelect, Trash2, Palette } from 'lucide-react'
import { SceneObject } from '@/lib/types'

export function ScenePanel() {
  const { scene, selectedObjectId, setSelectedObjectId } = useAppStore()

  const categories = {
    'Architecture': scene?.objects.filter(o => o.type === 'architecture') || [],
    'Furniture': scene?.objects.filter(o => o.type === 'furniture') || [],
    'Lighting': scene?.objects.filter(o => o.type === 'lighting') || [],
    'Decor': scene?.objects.filter(o => o.type === 'decor') || [],
  }

  const selectedObject = scene?.objects.find(o => o.entity_id === selectedObjectId)

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="p-4 border-b border-border flex items-center gap-2 shrink-0">
        <Layers size={18} className="text-text-secondary" />
        <h2 className="font-semibold text-sm">Scene Objects</h2>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-4">
        {Object.entries(categories).map(([cat, objects]) => {
          if (objects.length === 0) return null
          
          return (
            <div key={cat} className="space-y-1">
              <div className="text-xs font-semibold text-text-secondary uppercase tracking-wider px-2 py-1">
                {cat}
              </div>
              <div className="space-y-0.5">
                {objects.map((obj) => (
                  <button
                    key={obj.entity_id}
                    onClick={() => setSelectedObjectId(obj.entity_id)}
                    className={`w-full flex items-center gap-2 px-2 py-1.5 text-sm rounded-md transition-colors ${
                      selectedObjectId === obj.entity_id 
                        ? 'bg-accent/20 text-accent border border-accent/30' 
                        : 'hover:bg-surface-elevated text-text-primary border border-transparent'
                    }`}
                  >
                    <Box size={14} className={selectedObjectId === obj.entity_id ? 'text-accent' : 'text-text-secondary'} />
                    <span className="truncate">{obj.name || obj.category}</span>
                    {obj.material?.color && (
                      <div 
                        className="ml-auto w-3 h-3 rounded-full border border-border shrink-0" 
                        style={{ backgroundColor: obj.material.color }}
                      />
                    )}
                  </button>
                ))}
              </div>
            </div>
          )
        })}
      </div>

      {selectedObject && (
        <div className="border-t border-border bg-surface shrink-0">
          <ObjectDetails object={selectedObject} />
        </div>
      )}
    </div>
  )
}

function ObjectDetails({ object }: { object: SceneObject }) {
  return (
    <div className="p-4 space-y-4">
      <div>
        <div className="flex items-center justify-between mb-1">
          <h3 className="font-medium text-sm truncate">{object.name || object.category}</h3>
          <span className="text-[10px] uppercase bg-surface-elevated px-1.5 py-0.5 rounded text-text-secondary border border-border">
            {object.category}
          </span>
        </div>
        {object.confidence < 1 && (
          <div className="text-xs text-text-secondary">
            AI Confidence: {Math.round(object.confidence * 100)}%
          </div>
        )}
      </div>

      <div className="space-y-2 text-xs">
        <div className="flex justify-between border-b border-border/50 pb-1">
          <span className="text-text-secondary">Material</span>
          <span>{object.material?.type || 'Unknown'}</span>
        </div>
        <div className="flex justify-between border-b border-border/50 pb-1">
          <span className="text-text-secondary">Color</span>
          <div className="flex items-center gap-1">
            <div 
              className="w-2.5 h-2.5 rounded-sm border border-border" 
              style={{ backgroundColor: object.material?.color || 'transparent' }}
            />
            {object.material?.color || 'Unknown'}
          </div>
        </div>
        {object.dimensions && (
          <div className="flex justify-between border-b border-border/50 pb-1">
            <span className="text-text-secondary">Size (W×D×H)</span>
            <span className="font-mono text-[10px]">
              {object.dimensions.width_m}m × {object.dimensions.depth_m || object.dimensions.width_m}m × {object.dimensions.height_m}m
            </span>
          </div>
        )}
      </div>

      {object.editable && (
        <div className="grid grid-cols-2 gap-2 pt-2">
          <button className="flex items-center justify-center gap-1.5 py-1.5 bg-surface-elevated hover:bg-border rounded text-xs transition-colors">
            <BoxSelect size={12} /> Replace
          </button>
          <button className="flex items-center justify-center gap-1.5 py-1.5 bg-surface-elevated hover:bg-border rounded text-xs transition-colors">
            <Palette size={12} /> Restyle
          </button>
          <button className="col-span-2 flex items-center justify-center gap-1.5 py-1.5 border border-red-900/50 hover:bg-red-900/20 text-red-400 rounded text-xs transition-colors">
            <Trash2 size={12} /> Remove Object
          </button>
        </div>
      )}
    </div>
  )
}
