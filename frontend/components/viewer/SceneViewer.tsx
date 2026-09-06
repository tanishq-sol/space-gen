'use client'

import { Canvas, useThree, useFrame } from '@react-three/fiber'
import { Grid } from '@react-three/drei'
import { SceneObject } from '@/lib/types'
import { useState, useRef, useCallback, useEffect } from 'react'
import * as THREE from 'three'
import { useAppStore } from '@/lib/store'
import { SparkSplatViewer } from './SparkSplatViewer'
import { CameraController, CameraMode } from './CameraController'
import { useQualityManager } from './QualityManager'
import { ViewerOverlay } from './ViewerOverlay'

/* ---------- Per-object bounding-box mesh ---------- */
function SceneObjectMesh({ 
  object, selected, hovered, onClick, onHover 
}: { 
  object: SceneObject
  selected: boolean
  hovered: boolean
  onClick: () => void
  onHover: (hovering: boolean) => void
}) {
  const pos = object.position || { x: 0, y: 0, z: 0 }
  const dim = object.dimensions || { width_m: 1, height_m: 1, depth_m: 1 }
  const isHighlighted = selected || hovered

  return (
    <group position={[pos.x, pos.y, pos.z]}>
      {/* Transparent fill */}
      <mesh
        onClick={(e) => { e.stopPropagation(); onClick() }}
        onPointerOver={(e) => { e.stopPropagation(); onHover(true) }}
        onPointerOut={() => onHover(false)}
      >
        <boxGeometry args={[dim.width_m, dim.height_m, dim.depth_m || dim.width_m]} />
        <meshStandardMaterial 
          color={selected ? '#6366F1' : hovered ? '#818CF8' : (object.material?.color || '#666')}
          transparent
          opacity={isHighlighted ? 0.2 : 0.05}
          depthWrite={false}
        />
      </mesh>

      {/* Wireframe edges */}
      {isHighlighted && (
        <lineSegments>
          <edgesGeometry args={[new THREE.BoxGeometry(dim.width_m, dim.height_m, dim.depth_m || dim.width_m)]} />
          <lineBasicMaterial color={selected ? '#6366F1' : '#818CF8'} linewidth={1} transparent opacity={0.8} />
        </lineSegments>
      )}
    </group>
  )
}

/* ---------- Screenshot & FPS tracker helper (inside Canvas) ---------- */
function CanvasHelpers({ 
  onCapture, 
  onFrame 
}: { 
  onCapture: (fn: () => string | null) => void
  onFrame: () => void 
}) {
  const { gl, scene, camera } = useThree()
  
  useEffect(() => {
    onCapture(() => {
      gl.render(scene, camera)
      return gl.domElement.toDataURL('image/png')
    })
  }, [gl, scene, camera, onCapture])

  useFrame(() => {
    onFrame()
  })

  return null
}

/* ---------- Main SceneViewer ---------- */
export function SceneViewer({ 
  objects, selectedId, onSelectObject 
}: { 
  objects: SceneObject[]
  selectedId: string | null
  onSelectObject: (id: string | null) => void 
}) {
  const { splatUrl, showSplat, setShowSplat, showBoxes, setShowBoxes } = useAppStore()
  
  // Splat loading states
  const [loadProgress, setLoadProgress] = useState<number | null>(null)
  const [splatCount, setSplatCount] = useState<number | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  
  // Selection and interaction states
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [showShortcuts, setShowShortcuts] = useState(false)
  const [cameraMode, setCameraMode] = useState<CameraMode>('orbit')
  const captureRef = useRef<(() => string | null) | null>(null)

  // Dynamic performance and quality management
  const { tier, setTier, fps, trackFrame } = useQualityManager()

  const handleScreenshot = useCallback(() => {
    if (captureRef.current) {
      const dataUrl = captureRef.current()
      if (dataUrl) {
        useAppStore.getState().setBeforeImage(dataUrl)
      }
    }
  }, [])

  // Global hotkeys
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      
      switch (e.key.toLowerCase()) {
        case 's':
          if (splatUrl) setShowSplat(!showSplat)
          break
        case 'b':
          setShowBoxes(!showBoxes)
          break
        case 'o':
          setCameraMode('orbit')
          break
        case 'w':
          setCameraMode('walk')
          break
        case 'f':
          setCameraMode('fly')
          break
        case 'c':
          handleScreenshot()
          break
        case '?':
          setShowShortcuts(prev => !prev)
          break
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [showBoxes, showSplat, splatUrl, setShowBoxes, setShowSplat, handleScreenshot])

  return (
    <div className="w-full h-full relative select-none" onClick={() => onSelectObject(null)}>
      <Canvas 
        camera={{ position: [0, 1.8, 4.5], fov: 55 }} 
        shadows={false}
        gl={{ 
          antialias: false, // Spark handles splats with optimal custom shaders
          powerPreference: 'high-performance',
          preserveDrawingBuffer: true // Required for instantaneous viewport screenshot capture
        }}
      >
        <color attach="background" args={['#06060C']} />
        <ambientLight intensity={0.7} />
        <directionalLight position={[5, 10, 5]} intensity={0.9} />
        <directionalLight position={[-3, 8, -4]} intensity={0.4} />
        
        <Grid 
          infiniteGrid 
          fadeDistance={30} 
          sectionColor="#1E1E32"
          cellColor="#121222"
          position={[0, -1, 0]}
          sectionSize={2}
          cellSize={0.5}
        />
        
        {/* Switchable camera controller (Orbit / Walk / Fly) */}
        <CameraController 
          mode={cameraMode}
          onModeChange={setCameraMode}
          floorHeight={-1}
          eyeHeight={1.6}
        />

        <CanvasHelpers 
          onCapture={(fn) => { captureRef.current = fn }} 
          onFrame={trackFrame}
        />
        
        {/* 3D Gaussian Splatting Scene via Spark */}
        {splatUrl && (
          <SparkSplatViewer
            url={splatUrl}
            visible={showSplat}
            quality={tier}
            onProgress={(p) => setLoadProgress(p < 100 ? p : null)}
            onLoaded={(count) => {
              setSplatCount(count)
              setLoadProgress(null)
              setLoadError(null)
            }}
            onError={(err) => {
              setLoadError(err.message)
              setLoadProgress(null)
            }}
          />
        )}

        {/* Semantic Bounding Boxes */}
        {showBoxes && (
          <group>
            {objects.map(obj => (
              <SceneObjectMesh 
                key={obj.entity_id} 
                object={obj} 
                selected={obj.entity_id === selectedId}
                hovered={obj.entity_id === hoveredId}
                onClick={() => onSelectObject(obj.entity_id)}
                onHover={(h) => setHoveredId(h ? obj.entity_id : null)}
              />
            ))}
          </group>
        )}
      </Canvas>

      {/* Complete UI Controls and Overlays */}
      <ViewerOverlay
        loadProgress={loadProgress}
        splatCount={splatCount}
        loadError={loadError}
        onDismissError={() => setLoadError(null)}
        splatUrl={splatUrl}
        showSplat={showSplat}
        showBoxes={showBoxes}
        onToggleSplat={() => setShowSplat(!showSplat)}
        onToggleBoxes={() => setShowBoxes(!showBoxes)}
        cameraMode={cameraMode}
        onCameraMode={setCameraMode}
        quality={tier}
        fps={fps}
        onQualityChange={setTier}
        onScreenshot={handleScreenshot}
        showShortcuts={showShortcuts}
        onToggleShortcuts={() => setShowShortcuts(!showShortcuts)}
      />
    </div>
  )
}
