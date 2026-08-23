'use client'

import { Canvas } from '@react-three/fiber'
import { OrbitControls, Grid } from '@react-three/drei'
import { SceneObject } from '@/lib/types'
import { useState, useRef } from 'react'
import * as THREE from 'three'
import { useAppStore } from '@/lib/store'
import { GaussianSplatMesh } from './GaussianSplatMesh'
import { Eye, EyeOff, Layers, Loader2, RotateCcw, Sparkles } from 'lucide-react'

function SceneObjectMesh({ object, selected, onClick }: { object: SceneObject, selected: boolean, onClick: () => void }) {
  const meshRef = useRef<THREE.Mesh>(null)

  const pos = object.position || { x: 0, y: 0, z: 0 }
  const dim = object.dimensions || { width_m: 1, height_m: 1, depth_m: 1 }
  const color = object.material?.color || '#cccccc'

  return (
    <mesh
      ref={meshRef}
      position={[pos.x, pos.y, pos.z]}
      onClick={(e) => { e.stopPropagation(); onClick() }}
      castShadow
      receiveShadow
    >
      <boxGeometry args={[dim.width_m, dim.height_m, dim.depth_m || dim.width_m]} />
      <meshStandardMaterial 
        color={color} 
        emissive={selected ? '#6366F1' : '#000000'}
        emissiveIntensity={selected ? 0.3 : 0}
        transparent
        opacity={object.is_visible ? 0.85 : 0.2}
      />
      {selected && (
        <lineSegments>
          <edgesGeometry args={[new THREE.BoxGeometry(dim.width_m + 0.05, dim.height_m + 0.05, (dim.depth_m || dim.width_m) + 0.05)]} />
          <lineBasicMaterial color="#6366F1" />
        </lineSegments>
      )}
    </mesh>
  )
}

export function SceneViewer({ objects, selectedId, onSelectObject }: { objects: SceneObject[], selectedId: string | null, onSelectObject: (id: string | null) => void }) {
  const { splatUrl, showSplat, setShowSplat, showBoxes, setShowBoxes } = useAppStore()
  const [loadProgress, setLoadProgress] = useState<number | null>(null)
  const [pointCount, setPointCount] = useState<number | null>(null)
  const [pointSize, setPointSize] = useState(0.035)

  return (
    <div className="w-full h-full relative" onClick={() => onSelectObject(null)}>
      <Canvas camera={{ position: [0, 2, 5], fov: 50 }} shadows>
        <color attach="background" args={['#0A0A0A']} />
        <ambientLight intensity={0.8} />
        <directionalLight position={[5, 10, 5]} intensity={1.2} castShadow />
        
        <Grid 
          infiniteGrid 
          fadeDistance={25} 
          sectionColor="#333333" 
          cellColor="#222222" 
          position={[0, -1, 0]}
        />
        
        <OrbitControls makeDefault minPolarAngle={0} maxPolarAngle={Math.PI / 2 + 0.1} />
        
        {/* Render 3D Gaussian Splatting Scene */}
        {splatUrl && showSplat && (
          <GaussianSplatMesh
            url={splatUrl}
            pointSize={pointSize}
            onProgress={(p) => {
              setLoadProgress(p < 100 ? p : null)
            }}
            onLoaded={(count) => {
              setPointCount(count)
              setLoadProgress(null)
            }}
          />
        )}

        {/* Segmented Bounding Box Objects */}
        {showBoxes && (
          <group position={[0, 0, 0]}>
            {objects.map(obj => (
              <SceneObjectMesh 
                key={obj.entity_id} 
                object={obj} 
                selected={obj.entity_id === selectedId}
                onClick={() => onSelectObject(obj.entity_id)} 
              />
            ))}
          </group>
        )}
      </Canvas>

      {/* Loading Banner */}
      {loadProgress !== null && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 flex items-center gap-3 px-4 py-2 bg-surface-elevated/90 backdrop-blur-md rounded-full border border-border shadow-xl text-xs">
          <Loader2 size={14} className="animate-spin text-accent" />
          <span>Loading 3D Gaussian Splat... <b>{loadProgress}%</b></span>
        </div>
      )}

      {/* Active Splat Status Tag */}
      {splatUrl && pointCount !== null && (
        <div className="absolute top-4 left-4 flex items-center gap-2 px-3 py-1.5 bg-surface-elevated/80 backdrop-blur-md rounded-lg border border-border text-[11px] text-text-secondary">
          <div className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
          <span>Gaussian Splat Active · <b>{pointCount.toLocaleString()}</b> points</span>
        </div>
      )}

      {/* Overlay controls */}
      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-2 p-1.5 bg-surface-elevated/85 backdrop-blur-md rounded-xl border border-border shadow-2xl">
        {splatUrl && (
          <button
            onClick={(e) => { e.stopPropagation(); setShowSplat(!showSplat) }}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              showSplat ? 'bg-accent text-white shadow-sm shadow-accent/40' : 'bg-surface hover:bg-surface-elevated text-text-secondary'
            }`}
          >
            <Sparkles size={13} />
            <span>3D Splat</span>
          </button>
        )}

        <button
          onClick={(e) => { e.stopPropagation(); setShowBoxes(!showBoxes) }}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
            showBoxes ? 'bg-surface-elevated text-text-primary border border-border' : 'text-text-secondary hover:bg-surface'
          }`}
        >
          <Layers size={13} />
          <span>Boxes</span>
        </button>

        {splatUrl && showSplat && (
          <div className="flex items-center gap-1.5 px-2 border-l border-border text-xs text-text-secondary">
            <span>Size:</span>
            <input
              type="range"
              min="0.01"
              max="0.08"
              step="0.005"
              value={pointSize}
              onChange={(e) => setPointSize(parseFloat(e.target.value))}
              className="w-16 accent-accent h-1 cursor-pointer"
            />
          </div>
        )}
      </div>
    </div>
  )
}
