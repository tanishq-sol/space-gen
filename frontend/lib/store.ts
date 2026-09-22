import { create } from 'zustand'
import { SceneGraph, ChatMessage, ObjectTransform, FurnitureItem, MeshManifest } from './types'

export interface AppState {
  scene: SceneGraph | null
  selectedObjectId: string | null
  chatMessages: ChatMessage[]
  isLoading: boolean
  heroImage: string | null
  variants: Array<{ style: string; image: string; description: string }>
  referenceImage: string | null
  referenceAnalysis: any | null
  presentationMode: boolean
  beforeImage: string | null
  afterImage: string | null
  splatUrl: string | null
  showSplat: boolean
  showBoxes: boolean

  // Mesh & Object Editing State
  viewMode: 'splat' | 'mesh'
  gizmoMode: 'translate' | 'rotate' | 'scale'
  objectTransforms: Record<string, ObjectTransform>
  objectReplacements: Record<string, { modelUrl: string; name: string }>
  isConvertingMesh: boolean
  convertProgress: number | null
  meshManifest: MeshManifest | null
  furnitureCatalog: FurnitureItem[]
  showReplacementModal: boolean

  setScene: (scene: SceneGraph | null) => void
  setSelectedObjectId: (id: string | null) => void
  addChatMessage: (msg: ChatMessage) => void
  setIsLoading: (loading: boolean) => void
  setHeroImage: (image: string | null) => void
  setVariants: (variants: Array<{ style: string; image: string; description: string }>) => void
  setReferenceImage: (img: string | null) => void
  setReferenceAnalysis: (analysis: any) => void
  setPresentationMode: (mode: boolean) => void
  setBeforeImage: (img: string | null) => void
  setAfterImage: (img: string | null) => void
  setSplatUrl: (url: string | null) => void
  setShowSplat: (show: boolean) => void
  setShowBoxes: (show: boolean) => void

  // Mesh & Object Editing Setters
  setViewMode: (mode: 'splat' | 'mesh') => void
  setGizmoMode: (mode: 'translate' | 'rotate' | 'scale') => void
  updateObjectTransform: (id: string, transform: Partial<ObjectTransform>) => void
  resetObjectTransform: (id: string) => void
  replaceObject: (id: string, modelUrl: string, name: string) => void
  deleteObject: (id: string) => void
  setIsConvertingMesh: (val: boolean) => void
  setConvertProgress: (val: number | null) => void
  setMeshManifest: (manifest: MeshManifest | null) => void
  setFurnitureCatalog: (catalog: FurnitureItem[]) => void
  setShowReplacementModal: (show: boolean) => void
}

export const useAppStore = create<AppState>((set) => ({
  scene: null,
  selectedObjectId: null,
  chatMessages: [
    { role: 'assistant', content: 'Hello! I am your AI Copilot. How would you like to redesign this space?', timestamp: Date.now() }
  ],
  isLoading: false,
  heroImage: null,
  variants: [],
  referenceImage: null,
  referenceAnalysis: null,
  presentationMode: false,
  beforeImage: null,
  afterImage: null,
  splatUrl: null,
  showSplat: true,
  showBoxes: true,

  // Default mesh & transform editing state
  viewMode: 'splat',
  gizmoMode: 'translate',
  objectTransforms: {},
  objectReplacements: {},
  isConvertingMesh: false,
  convertProgress: null,
  meshManifest: null,
  furnitureCatalog: [],
  showReplacementModal: false,

  setScene: (scene) => set({ scene }),
  setSelectedObjectId: (id) => set({ selectedObjectId: id }),
  addChatMessage: (msg) => set((state) => ({ chatMessages: [...state.chatMessages, msg] })),
  setIsLoading: (isLoading) => set({ isLoading }),
  setHeroImage: (heroImage) => set({ heroImage }),
  setVariants: (variants) => set({ variants }),
  setReferenceImage: (referenceImage) => set({ referenceImage }),
  setReferenceAnalysis: (referenceAnalysis) => set({ referenceAnalysis }),
  setPresentationMode: (presentationMode) => set({ presentationMode }),
  setBeforeImage: (beforeImage) => set({ beforeImage }),
  setAfterImage: (afterImage) => set({ afterImage }),
  setSplatUrl: (splatUrl) => set({ splatUrl, showSplat: true }),
  setShowSplat: (showSplat) => set({ showSplat }),
  setShowBoxes: (showBoxes) => set({ showBoxes }),

  setViewMode: (viewMode) => set({ viewMode }),
  setGizmoMode: (gizmoMode) => set({ gizmoMode }),
  updateObjectTransform: (id, trans) => set((state) => ({
    objectTransforms: {
      ...state.objectTransforms,
      [id]: {
        position: trans.position || state.objectTransforms[id]?.position || [0, 0, 0],
        rotation: trans.rotation || state.objectTransforms[id]?.rotation || [0, 0, 0],
        scale: trans.scale || state.objectTransforms[id]?.scale || [1, 1, 1],
      }
    }
  })),
  resetObjectTransform: (id) => set((state) => {
    const next = { ...state.objectTransforms }
    delete next[id]
    return { objectTransforms: next }
  }),
  replaceObject: (id, modelUrl, name) => set((state) => ({
    objectReplacements: {
      ...state.objectReplacements,
      [id]: { modelUrl, name }
    }
  })),
  deleteObject: (id) => set((state) => {
    if (!state.scene) return {}
    return {
      selectedObjectId: state.selectedObjectId === id ? null : state.selectedObjectId,
      scene: {
        ...state.scene,
        objects: state.scene.objects.map(obj => obj.entity_id === id ? { ...obj, is_visible: false } : obj)
      }
    }
  }),
  setIsConvertingMesh: (isConvertingMesh) => set({ isConvertingMesh }),
  setConvertProgress: (convertProgress) => set({ convertProgress }),
  setMeshManifest: (meshManifest) => set({ meshManifest }),
  setFurnitureCatalog: (furnitureCatalog) => set({ furnitureCatalog }),
  setShowReplacementModal: (showReplacementModal) => set({ showReplacementModal }),
}))

