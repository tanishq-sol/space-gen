import { ReconstructionJob } from './types'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export const api = {
  async getScene(sceneId: string) {
    // Mock response for hackathon
    return {
      scene_id: sceneId,
      room_type: 'Living Room',
      style: 'Modern',
      objects: [
        {
          entity_id: 'obj_1',
          type: 'furniture',
          category: 'Sofa',
          name: 'Modern Sectional Sofa',
          position: { x: 0, y: 0.5, z: 0 },
          dimensions: { width_m: 2.5, height_m: 0.8, depth_m: 1.2 },
          material: { type: 'Fabric', color: '#888888', finish: 'Matte' },
          confidence: 0.95,
          editable: true,
          is_visible: true
        },
        {
          entity_id: 'obj_2',
          type: 'furniture',
          category: 'Table',
          name: 'Coffee Table',
          position: { x: 0, y: 0.25, z: 1.5 },
          dimensions: { width_m: 1.2, height_m: 0.4, depth_m: 0.6 },
          material: { type: 'Wood', color: '#8b5a2b', finish: 'Polished' },
          confidence: 0.9,
          editable: true,
          is_visible: true
        },
        {
          entity_id: 'obj_3',
          type: 'architecture',
          category: 'Wall',
          name: 'Back Wall',
          position: { x: 0, y: 1.5, z: -2 },
          dimensions: { width_m: 6, height_m: 3, depth_m: 0.1 },
          material: { type: 'Paint', color: '#e5e5e5', finish: 'Matte' },
          confidence: 0.99,
          editable: false,
          is_visible: true
        }
      ],
      relationships: []
    }
    // const res = await fetch(`${API_BASE}/api/scenes/${sceneId}`)
    // return res.json()
  },

  async createReconstructionJob(file: File) {
    const formData = new FormData()
    formData.append('video', file)
    const res = await fetch(`${API_BASE}/api/reconstruction/jobs`, { method: 'POST', body: formData })
    if (!res.ok) throw new Error(await res.text())
    return res.json()
  },

  async getReconstructionJob(jobId: string) {
    const res = await fetch(`${API_BASE}/api/reconstruction/jobs/${jobId}`)
    if (!res.ok) throw new Error('Could not read reconstruction status')
    return res.json()
  },

  async getLatestReconstructionJob(): Promise<ReconstructionJob | null> {
    try {
      const res = await fetch(`${API_BASE}/api/reconstruction/jobs/latest`)
      if (!res.ok) return null
      return res.json()
    } catch {
      return null
    }
  },

  getReconstructionModelUrl(jobId: string): string {
    return `${API_BASE}/api/reconstruction/jobs/${jobId}/model`
  },
  
  async chat(message: string, sceneId: string, history: any[] = [], referenceImage?: string) {
    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, scene_id: sceneId, history, reference_image: referenceImage })
      })
      if (!res.ok) throw new Error('API Error')
      return res.json()
    } catch (e) {
      // Mock fallback
      await new Promise(r => setTimeout(r, 1000))
      return { response: "I can help you redesign this space! Try asking me to make it more minimalist or change the sofa color." }
    }
  },
  
  async generateImage(sceneId: string, editInstruction: string, baseImage?: string, referenceImage?: string) {
    try {
      const res = await fetch(`${API_BASE}/api/generate-image`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scene_id: sceneId, edit_instruction: editInstruction, base_image: baseImage, reference_image: referenceImage })
      })
      if (!res.ok) throw new Error('API Error')
      return res.json()
    } catch (e) {
      await new Promise(r => setTimeout(r, 2000))
      return { image_url: "https://images.unsplash.com/photo-1586023492125-27b2c045efd7" }
    }
  },
  
  async analyzeReference(file: File) {
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await fetch(`${API_BASE}/api/analyze-reference`, {
        method: 'POST',
        body: formData
      })
      return res.json()
    } catch (e) {
      await new Promise(r => setTimeout(r, 1000))
      return { category: 'Chair', style: 'Mid-century Modern', color: '#ff0000', material: 'Leather' }
    }
  },
  
  async generateVariants(sceneId: string, styles: string[], baseImage?: string) {
    try {
      const res = await fetch(`${API_BASE}/api/generate-variants`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scene_id: sceneId, styles, base_image: baseImage })
      })
      return res.json()
    } catch (e) {
      await new Promise(r => setTimeout(r, 1500))
      return [
        { style: 'Minimalist', image: 'https://images.unsplash.com/photo-1598928506311-c55dd1b31120', description: 'Clean lines, neutral palette' },
        { style: 'Industrial', image: 'https://images.unsplash.com/photo-1555041469-a586c61ea9bc', description: 'Raw materials, edgy feel' },
        { style: 'Bohemian', image: 'https://images.unsplash.com/photo-1522708323590-d24dbb6b0267', description: 'Eclectic, warm, textured' }
      ]
    }
  }
}
