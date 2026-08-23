import * as THREE from 'three'

interface ParsedPLY {
  geometry: THREE.BufferGeometry
  pointCount: number
  bounds: {
    min: THREE.Vector3
    max: THREE.Vector3
    center: THREE.Vector3
    size: THREE.Vector3
  }
}

/**
 * Ultra-fast binary PLY parser for 3D Gaussian Splats.
 * Uses zero-copy preallocated typed arrays and native XHR streaming for instant loading.
 */
export function loadGaussianSplatPLY(
  url: string,
  onProgress?: (percent: number) => void
): Promise<ParsedPLY> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('GET', url, true)
    xhr.responseType = 'arraybuffer'

    xhr.onprogress = (e) => {
      if (e.lengthComputable && e.total > 0) {
        const percent = Math.min(99, Math.round((e.loaded / e.total) * 100))
        onProgress?.(percent)
      }
    }

    xhr.onerror = () => reject(new Error('Network error loading Gaussian Splat model'))

    xhr.onload = () => {
      if (xhr.status !== 200) {
        reject(new Error(`Failed to load splat model: HTTP ${xhr.status}`))
        return
      }

      onProgress?.(100)

      try {
        const arrayBuffer = xhr.response as ArrayBuffer
        const textDecoder = new TextDecoder('ascii')
        const headerBytes = new Uint8Array(arrayBuffer, 0, Math.min(8192, arrayBuffer.byteLength))
        const headerText = textDecoder.decode(headerBytes)
        const headerEndMarker = 'end_header\n'
        const headerEndIndex = headerText.indexOf(headerEndMarker)

        if (headerEndIndex === -1) {
          throw new Error('Invalid PLY file: end_header not found')
        }

        const fullHeader = headerText.slice(0, headerEndIndex + headerEndMarker.length)
        const lines = fullHeader.split('\n').map((l) => l.trim()).filter(Boolean)

        let vertexCount = 0
        const properties: Array<{ name: string; type: string; byteSize: number }> = []

        const typeSizes: Record<string, number> = {
          float: 4,
          float32: 4,
          double: 8,
          float64: 8,
          int: 4,
          int32: 4,
          uint: 4,
          uint32: 4,
          short: 2,
          int16: 2,
          ushort: 2,
          uint16: 2,
          uchar: 1,
          uint8: 1,
          char: 1,
          int8: 1,
        }

        for (const line of lines) {
          if (line.startsWith('element vertex')) {
            const parts = line.split(' ')
            vertexCount = parseInt(parts[2], 10)
          } else if (line.startsWith('property')) {
            const parts = line.split(' ')
            const type = parts[1].toLowerCase()
            const name = parts[2].toLowerCase()
            properties.push({
              name,
              type,
              byteSize: typeSizes[type] || 4,
            })
          }
        }

        if (vertexCount <= 0) {
          throw new Error('No vertices found in PLY header')
        }

        // Calculate byte stride and offsets
        let stride = 0
        const offsets: Record<string, { offset: number; type: string }> = {}
        for (const prop of properties) {
          offsets[prop.name] = { offset: stride, type: prop.type }
          stride += prop.byteSize
        }

        const dataOffset = headerEndIndex + headerEndMarker.length
        const dataView = new DataView(arrayBuffer, dataOffset)

        const isGaussianSplat = 'f_dc_0' in offsets
        const hasRGB = 'red' in offsets && 'green' in offsets && 'blue' in offsets
        const hasOpacity = 'opacity' in offsets
        const opacityOffset = hasOpacity ? offsets['opacity'].offset : -1

        const xOffset = offsets['x']?.offset ?? 0
        const yOffset = offsets['y']?.offset ?? 4
        const zOffset = offsets['z']?.offset ?? 8

        const f_dc_0_Offset = offsets['f_dc_0']?.offset ?? -1
        const f_dc_1_Offset = offsets['f_dc_1']?.offset ?? -1
        const f_dc_2_Offset = offsets['f_dc_2']?.offset ?? -1

        const redOffset = offsets['red']?.offset ?? -1
        const greenOffset = offsets['green']?.offset ?? -1
        const blueOffset = offsets['blue']?.offset ?? -1

        const SH_C0 = 0.28209479177387814

        // Preallocate typed Float32 arrays for instantaneous parsing
        const positions = new Float32Array(vertexCount * 3)
        const colors = new Float32Array(vertexCount * 3)
        const opacities = new Float32Array(vertexCount)

        let validCount = 0
        const maxBytes = dataView.byteLength

        for (let i = 0; i < vertexCount; i++) {
          const bytePos = i * stride
          if (bytePos + stride > maxBytes) break

          let pointOpacity = 1.0
          if (hasOpacity) {
            const rawOpacity = dataView.getFloat32(bytePos + opacityOffset, true)
            pointOpacity = 1.0 / (1.0 + Math.exp(-rawOpacity))
            if (pointOpacity < 0.02) {
              continue // Skip invisible points
            }
          }

          // Nerfstudio Z-up to Three.js Y-up [x, z, -y]
          const x = dataView.getFloat32(bytePos + xOffset, true)
          const y = dataView.getFloat32(bytePos + yOffset, true)
          const z = dataView.getFloat32(bytePos + zOffset, true)

          const pIdx = validCount * 3
          positions[pIdx] = x
          positions[pIdx + 1] = z
          positions[pIdx + 2] = -y

          // Colors
          let r = 1.0, g = 1.0, b = 1.0
          if (isGaussianSplat) {
            const f0 = dataView.getFloat32(bytePos + f_dc_0_Offset, true)
            const f1 = dataView.getFloat32(bytePos + f_dc_1_Offset, true)
            const f2 = dataView.getFloat32(bytePos + f_dc_2_Offset, true)
            r = Math.min(1.0, Math.max(0.0, 0.5 + SH_C0 * f0))
            g = Math.min(1.0, Math.max(0.0, 0.5 + SH_C0 * f1))
            b = Math.min(1.0, Math.max(0.0, 0.5 + SH_C0 * f2))
          } else if (hasRGB) {
            r = dataView.getUint8(bytePos + redOffset) / 255.0
            g = dataView.getUint8(bytePos + greenOffset) / 255.0
            b = dataView.getUint8(bytePos + blueOffset) / 255.0
          }

          colors[pIdx] = r
          colors[pIdx + 1] = g
          colors[pIdx + 2] = b

          opacities[validCount] = pointOpacity
          validCount++
        }

        // Subarray views to exact valid count
        const finalPositions = positions.subarray(0, validCount * 3)
        const finalColors = colors.subarray(0, validCount * 3)
        const finalOpacities = opacities.subarray(0, validCount)

        const geometry = new THREE.BufferGeometry()
        geometry.setAttribute('position', new THREE.BufferAttribute(finalPositions, 3))
        geometry.setAttribute('color', new THREE.BufferAttribute(finalColors, 3))
        geometry.setAttribute('opacity', new THREE.BufferAttribute(finalOpacities, 1))
        geometry.computeBoundingBox()
        geometry.center()

        const bbox = geometry.boundingBox || new THREE.Box3()
        const size = new THREE.Vector3()
        const center = new THREE.Vector3()
        bbox.getSize(size)
        bbox.getCenter(center)

        resolve({
          geometry,
          pointCount: validCount,
          bounds: {
            min: bbox.min,
            max: bbox.max,
            center,
            size,
          },
        })
      } catch (err) {
        reject(err)
      }
    }

    xhr.send()
  })
}
