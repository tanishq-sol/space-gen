import { create } from 'zustand'
import { SceneGraph, ChatMessage } from './types'

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
}))
