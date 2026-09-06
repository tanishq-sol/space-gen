'use client'

import { SparkSplatViewer } from './SparkSplatViewer'

/**
 * Backwards-compatible wrapper for GaussianSplatMesh using Spark under the hood.
 */
export function GaussianSplatMesh(props: {
  url: string
  onProgress?: (percent: number) => void
  onLoaded?: (splatCount: number) => void
  onError?: (error: Error) => void
  visible?: boolean
  quality?: 'max' | 'balanced' | 'performance'
}) {
  return <SparkSplatViewer {...props} />
}

export { SparkSplatViewer }
