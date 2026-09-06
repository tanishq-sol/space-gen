'use client'

import { useEffect, useRef, useCallback } from 'react'
import { useThree } from '@react-three/fiber'
import * as THREE from 'three'
import { api } from '@/lib/api'

/**
 * Gold-standard Open-Source 3D Gaussian Splat & Model Viewer.
 * 
 * Powered by:
 * - @mkkellogg/gaussian-splats-3d (The #1 open-source Three.js 3DGS engine)
 * - Three.js PLYLoader (for point-cloud & mesh PLYs like ammonite)
 * - Three.js GLTFLoader (for .glb / .gltf 3D assets)
 * - @sparkjsdev/spark (for compressed .spz)
 * 
 * Quality Settings:
 * - Full 32-bit Float Covariances for crystal-clear splat edges
 * - GPU-accelerated Radix Sort for smooth 60+ FPS
 * - Anti-aliased Gaussian kernels
 * - Spherical Harmonics (Degree 2) for dynamic specular reflections
 * - Instant in-memory format detection (.ply 3DGS vs point cloud vs mesh vs .glb)
 */
export function SparkSplatViewer({
  url,
  onProgress,
  onLoaded,
  onError,
  visible = true,
  quality = 'max',
}: {
  url: string
  onProgress?: (percent: number) => void
  onLoaded?: (splatCount: number) => void
  onError?: (error: Error) => void
  visible?: boolean
  quality?: 'max' | 'balanced' | 'performance'
}) {
  const { gl, scene, camera } = useThree()
  const currentUrlRef = useRef<string | null>(null)
  const activeDropInRef = useRef<any>(null)
  const activeSparkRef = useRef<any>(null)
  const activeMeshRef = useRef<THREE.Object3D | null>(null)
  const activeBlobUrlRef = useRef<string | null>(null)
  const isLoadingRef = useRef(false)

  // Use refs for callbacks and quality so state changes (progress, fps) do not re-trigger loadScene
  const onProgressRef = useRef(onProgress)
  onProgressRef.current = onProgress
  const onLoadedRef = useRef(onLoaded)
  onLoadedRef.current = onLoaded
  const onErrorRef = useRef(onError)
  onErrorRef.current = onError
  const qualityRef = useRef(quality)
  qualityRef.current = quality

  const cleanup = useCallback(() => {
    if (activeBlobUrlRef.current) {
      try {
        URL.revokeObjectURL(activeBlobUrlRef.current)
      } catch { /* ignore */ }
      activeBlobUrlRef.current = null
    }

    if (activeDropInRef.current) {
      try {
        scene.remove(activeDropInRef.current)
        activeDropInRef.current.dispose?.()
      } catch { /* ignore */ }
      activeDropInRef.current = null
    }

    if (activeSparkRef.current) {
      try {
        scene.remove(activeSparkRef.current)
        activeSparkRef.current.dispose?.()
      } catch { /* ignore */ }
      activeSparkRef.current = null
    }

    if (activeMeshRef.current) {
      try {
        scene.remove(activeMeshRef.current)
        activeMeshRef.current.traverse?.((child: any) => {
          if (child.geometry) child.geometry.dispose()
          if (child.material) {
            if (Array.isArray(child.material)) child.material.forEach((m: any) => m.dispose())
            else child.material.dispose()
          }
        })
      } catch { /* ignore */ }
      activeMeshRef.current = null
    }

    currentUrlRef.current = null
    isLoadingRef.current = false
  }, [scene])

  // Dynamically update quality on DropIn without reloading the scene
  useEffect(() => {
    qualityRef.current = quality
    if (activeDropInRef.current) {
      try {
        const shDeg = quality === 'max' ? 2 : quality === 'balanced' ? 1 : 0
        activeDropInRef.current.setActiveSphericalHarmonicsDegrees?.(shDeg)
      } catch { /* ignore */ }
    }
  }, [quality])

  useEffect(() => {
    if (!url) return
    const normalizedUrl = api.normalizeModelUrl(url) || url
    if (normalizedUrl === currentUrlRef.current) return

    cleanup()
    isLoadingRef.current = true
    currentUrlRef.current = normalizedUrl

    let cancelled = false

    async function loadScene() {
      try {
        onProgressRef.current?.(20)

        // Download / read the model into memory
        const response = await fetch(normalizedUrl)
        if (!response.ok) {
          throw new Error(`Failed to download model (HTTP ${response.status}: ${response.statusText})`)
        }
        const buffer = await response.arrayBuffer()
        if (cancelled) return
        onProgressRef.current?.(50)

        // Inspect header & magic bytes directly from in-memory buffer
        const lowerUrl = normalizedUrl.toLowerCase()
        const uint8 = new Uint8Array(buffer.slice(0, 16))
        const magic4 = new TextDecoder().decode(buffer.slice(0, 4))
        const headerText = new TextDecoder().decode(buffer.slice(0, 65536))

        // 1. Binary glTF (.glb) — Magic: 'glTF' (0x67 0x6c 0x54 0x46)
        const isGlb = (uint8[0] === 0x67 && uint8[1] === 0x6c && uint8[2] === 0x54 && uint8[3] === 0x46) || lowerUrl.endsWith('.glb')

        // 2. JSON glTF (.gltf)
        const isGltf = (headerText.trim().startsWith('{') && headerText.includes('"asset"')) || lowerUrl.endsWith('.gltf')

        // 3. Wavefront OBJ (.obj)
        const isObj = lowerUrl.endsWith('.obj') || (!isGlb && !isGltf && headerText.startsWith('#') && (headerText.includes('v ') || headerText.includes('vn ')))

        // 4. Compressed SPZ Gaussian Splat
        const isSpz = magic4.startsWith('SPZ') || (uint8[0] === 0x1f && uint8[1] === 0x8b) || lowerUrl.endsWith('.spz')

        // 5. KSPLAT / SPLAT
        const isKsplat = lowerUrl.endsWith('.ksplat')
        const isSplat = lowerUrl.endsWith('.splat')

        /* ========================================================== */
        /* 1. GLB / GLTF 3D MESH (Three.js GLTFLoader)                */
        /* ========================================================== */
        if (isGlb || isGltf) {
          const { GLTFLoader } = await import('three/examples/jsm/loaders/GLTFLoader.js')
          if (cancelled) return

          const loader = new GLTFLoader()
          let gltf: any
          if (isGlb) {
            gltf = await loader.parseAsync(buffer, '')
          } else {
            const text = new TextDecoder().decode(buffer)
            gltf = await loader.parseAsync(text, '')
          }
          if (cancelled) return

          const model = gltf.scene

          // Pivot wrapper centering: guarantees object is exactly centered at (0, 0, 0)
          const box = new THREE.Box3().setFromObject(model)
          const center = box.getCenter(new THREE.Vector3())
          const size = new THREE.Vector3()
          box.getSize(size)
          const maxDim = Math.max(size.x, size.y, size.z)

          model.position.set(-center.x, -center.y, -center.z)
          const wrapper = new THREE.Group()
          wrapper.add(model)

          if (maxDim > 0) {
            const targetSize = 4.0
            const scale = targetSize / maxDim
            wrapper.scale.set(scale, scale, scale)
          }

          // Ensure double-sided materials so inverted normals never appear invisible
          let vertexCount = 0
          model.traverse((child: any) => {
            if (child.isMesh) {
              vertexCount += child.geometry?.attributes?.position?.count || 1
              if (child.material) {
                if (Array.isArray(child.material)) child.material.forEach((m: any) => { m.side = THREE.DoubleSide })
                else child.material.side = THREE.DoubleSide
              }
            }
          })

          scene.add(wrapper)
          activeMeshRef.current = wrapper

          onProgressRef.current?.(100)
          onLoadedRef.current?.(Math.max(1, vertexCount))
          isLoadingRef.current = false
          return
        }

        /* ========================================================== */
        /* 2. WAVEFRONT OBJ 3D MESH (Three.js OBJLoader)              */
        /* ========================================================== */
        if (isObj) {
          const { OBJLoader } = await import('three/examples/jsm/loaders/OBJLoader.js')
          if (cancelled) return

          const loader = new OBJLoader()
          const text = new TextDecoder().decode(buffer)
          const model = loader.parse(text)
          if (cancelled) return

          // Pivot wrapper centering: guarantees object is exactly centered at (0, 0, 0)
          const box = new THREE.Box3().setFromObject(model)
          const center = box.getCenter(new THREE.Vector3())
          const size = new THREE.Vector3()
          box.getSize(size)
          const maxDim = Math.max(size.x, size.y, size.z)

          model.position.set(-center.x, -center.y, -center.z)
          const wrapper = new THREE.Group()
          wrapper.add(model)

          if (maxDim > 0) {
            const targetSize = 4.0
            const scale = targetSize / maxDim
            wrapper.scale.set(scale, scale, scale)
          }

          let vertexCount = 0
          model.traverse((child: any) => {
            if (child.isMesh) {
              vertexCount += child.geometry?.attributes?.position?.count || 1
              child.material = new THREE.MeshStandardMaterial({
                color: 0x93c5fd,
                roughness: 0.35,
                metalness: 0.2,
                side: THREE.DoubleSide,
              })
            }
          })

          scene.add(wrapper)
          activeMeshRef.current = wrapper

          onProgressRef.current?.(100)
          onLoadedRef.current?.(Math.max(1, vertexCount))
          isLoadingRef.current = false
          return
        }

        /* ========================================================== */
        /* 3. COMPRESSED SPZ (Spark Engine)                           */
        /* ========================================================== */
        if (isSpz) {
          const Spark = await import('@sparkjsdev/spark')
          if (cancelled) return

          const spark = new Spark.SparkRenderer({
            renderer: gl,
            enableLod: true,
            lodSplatScale: qualityRef.current === 'max' ? 2.0 : 1.0,
            sortRadial: true,
          })

          if (cancelled) { spark.dispose(); return }

          scene.add(spark)
          activeSparkRef.current = spark

          const blob = new Blob([buffer], { type: 'application/octet-stream' })
          const blobUrl = URL.createObjectURL(blob)
          activeBlobUrlRef.current = blobUrl

          const splat = new Spark.SplatMesh({
            url: blobUrl,
            lod: qualityRef.current === 'max' ? 'quality' : true,
            onLoad: (mesh: any) => {
              if (!cancelled) {
                const count = mesh.packedSplats?.numSplats || 0
                onProgressRef.current?.(100)
                onLoadedRef.current?.(count)
                isLoadingRef.current = false
              }
            },
          })

          scene.add(splat)
          await splat.initialized
          return
        }

        /* ========================================================== */
        /* 4. KSPLAT / SPLAT: Direct @mkkellogg Splat Loader          */
        /* ========================================================== */
        if (isKsplat || isSplat) {
          const GaussianSplats3D = await import('@mkkellogg/gaussian-splats-3d')
          if (cancelled) return

          const dropIn = new GaussianSplats3D.DropInViewer({
            gpuAcceleratedSort: true,
            halfPrecisionCovariancesOnGPU: qualityRef.current !== 'max',
            sharedMemoryForWorkers: true,
            integerBasedSort: true,
            dynamicScene: true,
            antialiased: true,
            sphericalHarmonicsDegree: qualityRef.current === 'max' ? 2 : qualityRef.current === 'balanced' ? 1 : 0,
          })

          if (cancelled) { dropIn.dispose(); return }
          scene.add(dropIn)
          activeDropInRef.current = dropIn

          const blob = new Blob([buffer], { type: 'application/octet-stream' })
          const blobUrl = URL.createObjectURL(blob)
          activeBlobUrlRef.current = blobUrl

          await dropIn.addSplatScene(blobUrl, {
            splatAlphaRemovalThreshold: 5,
            showLoadingUI: false,
            progressiveLoad: true,
            format: isKsplat ? GaussianSplats3D.SceneFormat.KSplat : GaussianSplats3D.SceneFormat.Splat,
            onProgress: (percent: number) => {
              if (!cancelled) onProgressRef.current?.(Math.min(99, Math.round(percent)))
            },
          })

          if (!cancelled) {
            const count = dropIn.viewer?.splatMesh?.getSplatCount?.() || 0
            onProgressRef.current?.(100)
            onLoadedRef.current?.(count)
            isLoadingRef.current = false
          }
          return
        }

        /* ========================================================== */
        /* 5. PLY FILES: Smart Dual-Engine Inspector                  */
        /* (Auto-differentiates 3D Gaussian Splats vs Point Clouds)   */
        /* ========================================================== */
        const isGaussianSplat = (
          /property\s+(float|double)\s+(f_dc_0|opacity|scale_0|rot_0)/i.test(headerText) ||
          /playcanvas/i.test(headerText)
        )

        /* ---- Branch A: True 3D Gaussian Splatting ---- */
        if (isGaussianSplat) {
          const GaussianSplats3D = await import('@mkkellogg/gaussian-splats-3d')
          if (cancelled) return

          const dropIn = new GaussianSplats3D.DropInViewer({
            gpuAcceleratedSort: true,
            halfPrecisionCovariancesOnGPU: qualityRef.current !== 'max',
            sharedMemoryForWorkers: true,
            integerBasedSort: true,
            dynamicScene: true,
            antialiased: true,
            sphericalHarmonicsDegree: qualityRef.current === 'max' ? 2 : qualityRef.current === 'balanced' ? 1 : 0,
          })

          if (cancelled) { dropIn.dispose(); return }
          scene.add(dropIn)
          activeDropInRef.current = dropIn

          onProgressRef.current?.(80)

          try {
            // Direct in-memory parse: 0 worker blob URL fetch issues, lightning fast
            const shDegree = qualityRef.current === 'max' ? 2 : qualityRef.current === 'balanced' ? 1 : 0
            const splatBuffer = GaussianSplats3D.PlyParser.parseToUncompressedSplatBuffer(buffer, shDegree)
            if (cancelled) { dropIn.dispose(); return }

            await dropIn.viewer.addSplatBuffers([splatBuffer], [], true, false, false, false)
          } catch (parseErr) {
            console.warn('[SparkSplatViewer] Direct SplatBuffer parse fallback, trying addSplatScene:', parseErr)
            if (cancelled) return
            await dropIn.addSplatScene(normalizedUrl, {
              splatAlphaRemovalThreshold: 5,
              showLoadingUI: false,
              progressiveLoad: false,
              format: GaussianSplats3D.SceneFormat.Ply,
            })
          }

          if (!cancelled) {
            const count = dropIn.viewer?.splatMesh?.getSplatCount?.() || 0
            onProgressRef.current?.(100)
            onLoadedRef.current?.(count)
            isLoadingRef.current = false
          }
          return
        }

        /* ---- Branch B: Colored Point Cloud / Mesh (e.g. ammonite, Stanford PLY) ---- */
        const { PLYLoader } = await import('three/examples/jsm/loaders/PLYLoader.js')
        if (cancelled) return

        const loader = new PLYLoader()
        const geometry = loader.parse(buffer)
        geometry.computeVertexNormals()
        geometry.center() // Auto-center in camera viewport

        // Auto-scale to comfortable scene size if model is huge or tiny
        geometry.computeBoundingBox()
        const boundingBox = geometry.boundingBox
        if (boundingBox) {
          const size = new THREE.Vector3()
          boundingBox.getSize(size)
          const maxDim = Math.max(size.x, size.y, size.z)
          if (maxDim > 20) {
            const scale = 5 / maxDim
            geometry.scale(scale, scale, scale)
          } else if (maxDim < 0.1 && maxDim > 0) {
            const scale = 2 / maxDim
            geometry.scale(scale, scale, scale)
          }
        }

        let object3D: THREE.Object3D
        const hasFaces = !!(geometry.index || geometry.attributes.normal)
        const hasColors = !!geometry.attributes.color

        // If it has faces, render as standard PBR mesh; otherwise render as high-density point cloud
        if (hasFaces && (geometry.index || !hasColors)) {
          const material = new THREE.MeshStandardMaterial({
            vertexColors: hasColors,
            color: hasColors ? 0xffffff : 0x818cf8,
            roughness: 0.35,
            metalness: 0.15,
            side: THREE.DoubleSide,
          })
          object3D = new THREE.Mesh(geometry, material)
        } else {
          const material = new THREE.PointsMaterial({
            size: 0.03,
            vertexColors: hasColors,
            color: hasColors ? 0xffffff : 0x818cf8,
            sizeAttenuation: true,
          })
          object3D = new THREE.Points(geometry, material)
        }

        if (cancelled) { geometry.dispose(); return }

        scene.add(object3D)
        activeMeshRef.current = object3D

        const pointCount = geometry.attributes.position?.count || 0
        onProgressRef.current?.(100)
        onLoadedRef.current?.(pointCount)
        isLoadingRef.current = false

      } catch (err: any) {
        if (!cancelled) {
          console.error('[OpenSourceSplatViewer] Load error:', err)
          onErrorRef.current?.(err instanceof Error ? err : new Error(String(err)))
          isLoadingRef.current = false
        }
      }
    }

    loadScene()

    return () => {
      cancelled = true
      cleanup()
    }
  }, [url, gl, scene, cleanup])

  // Sync visibility
  useEffect(() => {
    if (activeDropInRef.current) activeDropInRef.current.visible = visible
    if (activeMeshRef.current) activeMeshRef.current.visible = visible
    if (activeSparkRef.current) activeSparkRef.current.visible = visible
  }, [visible])

  return null
}
