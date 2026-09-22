'use client'

import { Canvas, useThree, useFrame } from '@react-three/fiber'
import { Grid } from '@react-three/drei'
import { SceneObject } from '@/lib/types'
import { useState, useRef, useCallback, useEffect, useMemo } from 'react'
import * as THREE from 'three'
import { useAppStore } from '@/lib/store'
import { SplatEngine } from './SplatEngine'
import { SparkSplatViewer } from './SparkSplatViewer'
import { CameraController, CameraMode } from './CameraController'
import { useQualityManager } from './QualityManager'
import { ViewerOverlay } from './ViewerOverlay'
import { SolidMeshViewer } from './SolidMeshViewer'
import { ObjectActionBar } from './ObjectActionBar'
import { ObjectReplacementModal } from './ObjectReplacementModal'
import { api } from '@/lib/api'

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
  const { 
    splatUrl, 
    showSplat, 
    setShowSplat, 
    showBoxes, 
    setShowBoxes,
    viewMode,
    meshManifest,
    setMeshManifest,
    setFurnitureCatalog,
  } = useAppStore()
  
  // Splat loading states
  const [loadProgress, setLoadProgress] = useState<number | null>(null)
  const [splatCount, setSplatCount] = useState<number | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  
  // Engine routing: start with the spatial engine, fall back to legacy if needed
  const [useFallbackEngine, setUseFallbackEngine] = useState(false)
  const [spatialFps, setSpatialFps] = useState(0)

  // Selection, transform gizmo, and interaction states
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [isDraggingGizmo, setIsDraggingGizmo] = useState(false)
  const [showShortcuts, setShowShortcuts] = useState(false)
  const [cameraMode, setCameraMode] = useState<CameraMode>('orbit')
  const captureRef = useRef<(() => string | null) | null>(null)

  // Pre-load furniture catalog & mesh manifest
  useEffect(() => {
    api.getFurnitureCatalog().then((items) => {
      if (items && items.length > 0) {
        setFurnitureCatalog(items)
      }
    }).catch(e => console.warn('Could not load furniture catalog:', e))
  }, [setFurnitureCatalog])

  useEffect(() => {
    const match = splatUrl?.match(/jobs\/([^\/]+)/)
    const jobId = match ? match[1] : null
    if (jobId && !meshManifest) {
      api.getMeshManifest(jobId).then((m) => {
        if (m) setMeshManifest(m)
      }).catch(() => {})
    }
  }, [splatUrl, meshManifest, setMeshManifest])

  // Resolve master mesh URL for solid polygon mesh mode
  const masterMeshUrl = useMemo(() => {
    if (splatUrl && (splatUrl.endsWith('.glb') || splatUrl.endsWith('.gltf') || splatUrl.endsWith('.obj'))) {
      return api.normalizeModelUrl(splatUrl) || splatUrl
    }
    const match = splatUrl?.match(/jobs\/([^\/]+)/)
    const jobId = match ? match[1] : '44a1897d1ca1'
    if (meshManifest?.master_mesh) {
      return api.normalizeModelUrl(`/api/reconstruction/jobs/${jobId}/mesh/${meshManifest.master_mesh}`) || undefined
    }
    return api.normalizeModelUrl(`/api/reconstruction/jobs/${jobId}/mesh/scene_mesh.glb`) || undefined
  }, [splatUrl, meshManifest])

  // Merged objects list including semantic manifest items and guaranteed primary bed
  const allObjects: SceneObject[] = useMemo(() => {
    const existingIds = new Set(objects.map(o => o.entity_id))
    const list = [...objects]
    if (meshManifest?.objects) {
      for (const mObj of meshManifest.objects) {
        if (!existingIds.has(mObj.entity_id)) {
          list.push({
            entity_id: mObj.entity_id,
            name: mObj.name,
            category: mObj.category,
            type: 'furniture',
            position: mObj.position,
            dimensions: mObj.dimensions,
            confidence: 1.0,
            is_visible: true,
            editable: true,
          })
          existingIds.add(mObj.entity_id)
        }
      }
    }
    // Guarantee primary bed object exists so user can immediately move/rotate/scale/replace it
    if (!list.some(o => o.category?.toLowerCase() === 'bed' || o.name?.toLowerCase().includes('bed'))) {
      list.push({
        entity_id: 'bed_primary',
        name: 'King Size Bed',
        category: 'Bed',
        type: 'furniture',
        position: { x: 0, y: 0.45, z: 0 },
        dimensions: { width_m: 2.05, height_m: 0.95, depth_m: 2.15 },
        material: { type: 'Fabric', color: '#6366f1', finish: 'Matte' },
        confidence: 1.0,
        editable: true,
        is_visible: true,
      })
    }
    return list
  }, [objects, meshManifest])

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
          // If in walk mode or no object selected
          if (cameraMode !== 'orbit') setCameraMode('walk')
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
  }, [showBoxes, showSplat, splatUrl, setShowBoxes, setShowSplat, handleScreenshot, cameraMode])

  // Reset fallback engine when URL changes
  useEffect(() => {
    setUseFallbackEngine(false)
  }, [splatUrl])

  // Determine if the spatial engine should be active
  const useSpatialEngine = viewMode === 'splat' && splatUrl && !useFallbackEngine

  return (
    <div className="w-full h-full relative select-none">
      {/* 
        ENGINE 1: SpaceGen Spatial Engine (high-performance 3DGS renderer)
        Renders in its own WebGL2 canvas, sits on top of the R3F canvas.
        Only visible when in Splat View mode and the spatial engine is active.
      */}
      {useSpatialEngine && (
        <SplatEngine
          url={splatUrl!}
          visible={viewMode === 'splat' && showSplat}
          className="absolute inset-0 z-10"
          onProgress={(p) => setLoadProgress(p < 100 ? p : null)}
          onLoaded={(info) => {
            setSplatCount(info.splatCount || 0)
            setLoadProgress(null)
            setLoadError(null)
          }}
          onFpsUpdate={(f) => setSpatialFps(f)}
          onError={(err) => {
            if (err.message === 'FALLBACK_REQUIRED') {
              // Spatial engine cannot parse this format — switch to legacy renderer
              console.log('[SpaceGen] Spatial engine falling back to legacy renderer for:', splatUrl)
              setUseFallbackEngine(true)
              setLoadError(null)
              setLoadProgress(null)
            } else if (err.message.startsWith('MESH_FORMAT:')) {
              // This is a mesh file — it will be handled by the R3F viewer below
              setUseFallbackEngine(true)
            } else {
              setLoadError(err.message)
              setLoadProgress(null)
            }
          }}
        />
      )}

      {/* 
        ENGINE 2: R3F Canvas (Three.js)
        Handles: Solid Mesh mode, 6-DOF TransformControls, bounding boxes.
        Also serves as fallback for .splat files the spatial engine cannot parse.
        Hidden behind the spatial engine canvas when it is active.
      */}
      <Canvas 
        onPointerMissed={() => onSelectObject(null)}
        camera={{ position: [0, 1.8, 4.5], fov: 55 }} 
        shadows={false}
        style={{
          // Move behind the spatial engine when it's active and visible
          position: useSpatialEngine ? 'absolute' : 'relative',
          zIndex: useSpatialEngine ? 0 : 1,
          opacity: useSpatialEngine ? 0 : 1,
          pointerEvents: useSpatialEngine ? 'none' : 'auto',
        }}
        gl={{ 
          antialias: false,
          powerPreference: 'high-performance',
          preserveDrawingBuffer: true
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
        
        {/* Switchable camera controller with gizmo drag locking */}
        <CameraController 
          mode={cameraMode}
          onModeChange={setCameraMode}
          floorHeight={-1}
          eyeHeight={1.6}
          isDraggingGizmo={isDraggingGizmo}
        />

        <CanvasHelpers 
          onCapture={(fn) => { captureRef.current = fn }} 
          onFrame={trackFrame}
        />
        
        {/* Legacy Splat Renderer (fallback when spatial engine can't parse the format) */}
        {viewMode === 'splat' && splatUrl && useFallbackEngine && (
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

        {/* Mode 2: Solid Watertight Polygon Mesh + 6-DOF Interactive Objects */}
        {viewMode === 'mesh' && (
          <SolidMeshViewer
            meshUrl={masterMeshUrl}
            objects={allObjects}
            onSelectObject={onSelectObject}
            onDragChange={setIsDraggingGizmo}
          />
        )}

        {/* Semantic Bounding Boxes (Splat Mode) */}
        {viewMode === 'splat' && showBoxes && (
          <group>
            {allObjects.map(obj => (
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

      {/* Floating 6-DOF Action Bar for Selected Object */}
      <ObjectActionBar />

      {/* Object Replacement Modal (Catalog / Custom Upload / AI Generator) */}
      <ObjectReplacementModal />

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
        fps={useSpatialEngine ? spatialFps : fps}
        onQualityChange={setTier}
        onScreenshot={handleScreenshot}
        showShortcuts={showShortcuts}
        onToggleShortcuts={() => setShowShortcuts(!showShortcuts)}
      />
    </div>
  )
}
