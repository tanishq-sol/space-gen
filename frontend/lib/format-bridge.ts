/**
 * SpaceGen Format Detection & Engine Routing
 * 
 * Detects 3D file formats from buffer contents and URL extensions,
 * then routes to the appropriate rendering engine.
 * 
 * @license MIT — see THIRD_PARTY_LICENSES.md
 */

export type RenderEngine = 'spatial' | 'legacy' | 'mesh'

export type SpatialFileType = 'sog' | 'ply-3dgs' | 'splat' | 'ksplat'
export type MeshFileType = 'glb' | 'gltf' | 'obj'

export interface FormatDetectionResult {
  engine: RenderEngine
  spatialType?: SpatialFileType
  meshType?: MeshFileType
  isPointCloud?: boolean
}

/**
 * Detect the file format from the first bytes of a buffer and the URL.
 * Returns which rendering engine to use and the specific file type.
 */
export function detectFormat(buffer: ArrayBuffer, url: string): FormatDetectionResult {
  const lowerUrl = url.toLowerCase()
  const uint8 = new Uint8Array(buffer.slice(0, 64))
  const magic4 = safeDecodeText(buffer.slice(0, 4))
  const headerText = safeDecodeText(buffer.slice(0, Math.min(65536, buffer.byteLength)))

  // 1. Binary glTF (.glb) — Magic: 'glTF' (0x67 0x6c 0x54 0x46)
  if (
    (uint8[0] === 0x67 && uint8[1] === 0x6c && uint8[2] === 0x54 && uint8[3] === 0x46) ||
    lowerUrl.endsWith('.glb')
  ) {
    return { engine: 'mesh', meshType: 'glb' }
  }

  // 2. JSON glTF (.gltf)
  if (
    (headerText.trim().startsWith('{') && headerText.includes('"asset"')) ||
    lowerUrl.endsWith('.gltf')
  ) {
    return { engine: 'mesh', meshType: 'gltf' }
  }

  // 3. Wavefront OBJ (.obj)
  if (
    lowerUrl.endsWith('.obj') ||
    (!magic4.startsWith('glTF') && headerText.startsWith('#') && (headerText.includes('v ') || headerText.includes('vn ')))
  ) {
    return { engine: 'mesh', meshType: 'obj' }
  }

  // 4. SOG format (native high-performance spatial format)
  if (lowerUrl.endsWith('.sog') || lowerUrl.includes('.sog')) {
    return { engine: 'spatial', spatialType: 'sog' }
  }

  // 5. KSPLAT format
  if (lowerUrl.endsWith('.ksplat') || lowerUrl.includes('.ksplat')) {
    return { engine: 'legacy', spatialType: 'ksplat' }
  }

  // 6. PLY format — check if it's a 3DGS PLY or a regular mesh/point cloud PLY
  if (magic4.startsWith('ply') || lowerUrl.endsWith('.ply') || lowerUrl.includes('.ply')) {
    const is3DGS = detect3DGSPly(headerText)
    if (is3DGS) {
      return { engine: 'spatial', spatialType: 'ply-3dgs' }
    }
    // Point cloud or mesh PLY — use legacy renderer
    return { engine: 'legacy', isPointCloud: true }
  }

  // 7. Raw .splat format (32-byte records per gaussian)
  if (
    lowerUrl.endsWith('.splat') ||
    lowerUrl.includes('.splat') ||
    (buffer.byteLength > 0 && buffer.byteLength % 32 === 0)
  ) {
    // Try spatial engine first — it supports .splat via parseSplatData
    return { engine: 'spatial', spatialType: 'splat' }
  }

  // 8. Compressed SPZ
  if (
    magic4.startsWith('SPZ') ||
    (uint8[0] === 0x1f && uint8[1] === 0x8b) ||
    lowerUrl.endsWith('.spz') || lowerUrl.includes('.spz')
  ) {
    return { engine: 'legacy' }
  }

  // Default: try spatial engine
  return { engine: 'spatial', spatialType: 'splat' }
}

/**
 * Check if a PLY file contains 3D Gaussian Splatting data
 * by looking for specific properties in the header.
 */
function detect3DGSPly(headerText: string): boolean {
  const headerEnd = headerText.indexOf('end_header')
  if (headerEnd === -1) return false
  const header = headerText.substring(0, headerEnd)
  // 3DGS PLY files contain spherical harmonic coefficients or covariance properties
  return (
    header.includes('f_dc_0') ||
    header.includes('rot_0') ||
    header.includes('scale_0') ||
    (header.includes('opacity') && header.includes('scale'))
  )
}

function safeDecodeText(buffer: ArrayBuffer): string {
  try {
    return new TextDecoder().decode(buffer)
  } catch {
    return ''
  }
}
