export interface Material {
  type: string
  color: string
  finish: string
  texture?: string
}

export interface Position {
  x: number
  y: number
  z: number
}

export interface Dimensions {
  width_m: number
  depth_m?: number
  height_m: number
}

export interface SceneObject {
  entity_id: string
  type: 'architecture' | 'furniture' | 'lighting' | 'decor'
  category: string
  subcategory?: string
  name?: string
  position?: Position
  dimensions?: Dimensions
  material?: Material
  style?: string
  confidence: number
  editable: boolean
  is_visible: boolean
  replaced_by?: string
}

export interface SceneGraph {
  scene_id: string
  room_type: string
  style: string
  dimensions?: Dimensions
  lighting?: Record<string, any>
  objects: SceneObject[]
  relationships: Array<{ subject: string; relation: string; object: string }>
}

export interface ChatMessage {
  id?: string
  role: 'user' | 'assistant'
  content: string
  image?: string  // base64 or url
  timestamp: number
}

export interface ReconstructionJob {
  job_id: string
  status: 'queued' | 'running' | 'ready_for_training' | 'completed' | 'failed'
  progress: number
  step: string
  log?: string
  frames_dir?: string
  scene_path?: string
  splat_url?: string
}
