import { create } from 'zustand';

/** UI-only state for the review panel and overlay; scene data lives in the Pascal store. */
interface ReviewUiState {
  panelOpen: boolean;
  overlayOn: boolean;
  selectedId: string | null;
  setPanelOpen: (open: boolean) => void;
  setOverlayOn: (on: boolean) => void;
  select: (id: string | null) => void;
}

export const useReviewUi = create<ReviewUiState>((set) => ({
  panelOpen: false,
  overlayOn: true,
  selectedId: null,
  setPanelOpen: (panelOpen) => set({ panelOpen }),
  setOverlayOn: (overlayOn) => set({ overlayOn }),
  select: (selectedId) => set({ selectedId }),
}));
