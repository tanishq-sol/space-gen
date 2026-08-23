'use client'

import { useEffect, useState, useRef, useMemo } from 'react'
import * as THREE from 'three'
import { loadGaussianSplatPLY } from '@/lib/splatLoader'

interface GaussianSplatMeshProps {
  url: string
  pointSize?: number
  onLoaded?: (pointCount: number) => void
  onProgress?: (progress: number) => void
}

export function GaussianSplatMesh({
  url,
  pointSize = 0.045,
  onLoaded,
  onProgress,
}: GaussianSplatMeshProps) {
  const [geometry, setGeometry] = useState<THREE.BufferGeometry | null>(null)
  const pointsRef = useRef<THREE.Points>(null)

  const material = useMemo(() => {
    return new THREE.ShaderMaterial({
      uniforms: {
        uSize: { value: pointSize * 100.0 },
      },
      vertexShader: `
        attribute float opacity;
        varying vec3 vColor;
        varying float vOpacity;
        uniform float uSize;

        void main() {
          vColor = color;
          vOpacity = opacity;
          vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
          gl_Position = projectionMatrix * mvPosition;
          // Perspective size attenuation
          gl_PointSize = (uSize / -mvPosition.z) * 1.5;
          gl_PointSize = clamp(gl_PointSize, 1.0, 64.0);
        }
      `,
      fragmentShader: `
        varying vec3 vColor;
        varying float vOpacity;

        void main() {
          // Circular Gaussian splat falloff
          vec2 coord = gl_PointCoord - vec2(0.5);
          float distSq = dot(coord, coord);
          if (distSq > 0.25) discard;

          // Smooth Gaussian bell-curve falloff
          float alpha = exp(-distSq * 6.0) * vOpacity;
          gl_FragColor = vec4(vColor, alpha);
        }
      `,
      transparent: true,
      depthWrite: false,
      depthTest: true,
      blending: THREE.NormalBlending,
      vertexColors: true,
    })
  }, [pointSize])

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const result = await loadGaussianSplatPLY(url, (p) => {
          if (!cancelled) onProgress?.(p)
        })
        if (!cancelled) {
          setGeometry(result.geometry)
          onLoaded?.(result.pointCount)
        }
      } catch (err) {
        console.error('Error loading Gaussian Splat:', err)
      }
    }

    load()

    return () => {
      cancelled = true
    }
  }, [url, onLoaded, onProgress])

  useEffect(() => {
    if (material.uniforms.uSize) {
      material.uniforms.uSize.value = pointSize * 100.0
    }
  }, [pointSize, material])

  if (!geometry) return null

  return (
    <points ref={pointsRef} geometry={geometry} material={material} />
  )
}
