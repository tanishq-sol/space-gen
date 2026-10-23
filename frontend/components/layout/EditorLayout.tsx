'use client'

import { useAppStore } from '@/lib/store'
import { Undo2, Redo2, Box, Ellipsis, PanelLeft, PanelRight, ChevronDown, Play, Download, Save } from 'lucide-react'
import Link from 'next/link'
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { VideoCaptureModal } from '@/components/capture/VideoCaptureModal'
import { useScene } from '@pascal-app/core'
import { useStore } from 'zustand'
import { undoSceneAction, redoSceneAction } from '@/lib/pascal/sceneBridge'
import { NavModeSegment, SceneKindSegment, ViewModeSegment } from '@/components/viewer/NavigationOverlay'

export interface EditorMoreItem {
  label: string
  onSelect: () => void
  /** Renders a toggle: the button reports aria-pressed. */
  pressed?: boolean
  disabled?: boolean
}

export interface EditorSaveState {
  label: string
  isError?: boolean
  onSave: () => void
  disabled?: boolean
}

interface EditorLayoutProps {
  /** The viewport (and any modal layers). Fills the whole window. */
  children: React.ReactNode
  scenePanel: React.ReactNode
  askPanel: React.ReactNode
  onShare?: () => void
  /** Falls back to the scene's room type. */
  projectName?: string
  save?: EditorSaveState
  /** Secondary actions that live in the More menu, in addition to Present and Export. */
  moreItems?: EditorMoreItem[]
  /** A save or load error shown under the toolbar. */
  error?: string
  /** Where the wordmark goes (the project list). */
  homeHref?: string
}

const PANEL_KEYS = { left: 'ellips.panel.scene', right: 'ellips.panel.ask' } as const

/** Collapsed state is a per-browser convenience; storage can be missing or blocked. */
const collapsedListeners = new Set<() => void>()
/** Mirrors the stored value so the toggle still works for this page view when storage is blocked. */
const collapsedMemory = new Map<string, boolean>()

function readCollapsed(key: string): boolean {
  const remembered = collapsedMemory.get(key)
  if (remembered !== undefined) return remembered
  try {
    return window.localStorage.getItem(key) === 'collapsed'
  } catch {
    return false
  }
}

function writeCollapsed(key: string, collapsed: boolean) {
  collapsedMemory.set(key, collapsed)
  try {
    window.localStorage.setItem(key, collapsed ? 'collapsed' : 'open')
  } catch {
    /* storage unavailable: nothing is remembered across visits */
  }
  collapsedListeners.forEach((notify) => notify())
}

const subscribeCollapsed = (notify: () => void) => {
  collapsedListeners.add(notify)
  return () => { collapsedListeners.delete(notify) }
}

/** Server and first client render say "open", then the stored choice applies without a mismatch. */
function useCollapsed(key: string): boolean {
  return useSyncExternalStore(subscribeCollapsed, () => readCollapsed(key), () => false)
}

const MENU_ITEM =
  'flex h-9 w-full items-center gap-2 rounded-control px-2 text-left text-[13px] text-ink hover:bg-ink/5 disabled:pointer-events-none disabled:opacity-40 max-lg:h-11'

export function EditorLayout({ children, scenePanel, askPanel, onShare, projectName, save, moreItems = [], error, homeHref }: EditorLayoutProps) {
  const { scene } = useAppStore()
  // Subscribe to the zundo temporal store itself so the buttons track history, not node changes.
  const canUndo = useStore(useScene.temporal, (state) => state.pastStates.length > 0)
  const canRedo = useStore(useScene.temporal, (state) => state.futureStates.length > 0)
  const [captureOpen, setCaptureOpen] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)
  const moreRef = useRef<HTMLDivElement>(null)
  const leftOpen = !useCollapsed(PANEL_KEYS.left)
  const rightOpen = !useCollapsed(PANEL_KEYS.right)
  const [sheetOpen, setSheetOpen] = useState(true)
  const [tab, setTab] = useState<'ask' | 'scene'>('ask')

  const togglePanel = useCallback((side: 'left' | 'right') => {
    const key = PANEL_KEYS[side]
    writeCollapsed(key, !readCollapsed(key))
  }, [])

  // Global keyboard shortcuts for Undo (Ctrl+Z) and Redo (Ctrl+Y / Ctrl+Shift+Z)
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT' || target.isContentEditable)) {
        return
      }
      if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === 'z') {
        e.preventDefault()
        if (e.shiftKey) {
          redoSceneAction()
        } else {
          undoSceneAction()
        }
      } else if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === 'y') {
        e.preventDefault()
        redoSceneAction()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  useEffect(() => {
    if (!moreOpen) return
    const close = (e: PointerEvent) => {
      if (!moreRef.current?.contains(e.target as Node)) setMoreOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMoreOpen(false)
    }
    document.addEventListener('pointerdown', close)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', close)
      document.removeEventListener('keydown', onKey)
    }
  }, [moreOpen])

  const pick = (action: () => void) => () => {
    setMoreOpen(false)
    action()
  }
  const name = projectName || scene?.room_type || 'Untitled Project'
  const saveLabel = save?.label

  // Insets tell the viewer overlays where the floating panels end, so they never sit underneath them.
  const insets = [
    leftOpen ? 'lg:[--left-inset:268px] xl:[--left-inset:320px]' : 'lg:[--left-inset:64px]',
    rightOpen ? 'lg:[--right-inset:300px] xl:[--right-inset:356px]' : 'lg:[--right-inset:64px]',
  ].join(' ')
  const sheetVar = sheetOpen ? '[--sheet-h:42dvh]' : '[--sheet-h:84px]'

  return (
    <div className={`relative h-full w-full overflow-hidden bg-background [--left-inset:12px] [--right-inset:12px] lg:[--sheet-h:0px] ${sheetVar} ${insets}`}>
      {/* The scan fills the whole window; everything else floats above it. */}
      <main className="absolute inset-0">{children}</main>

      {/* Toolbar: regular glass */}
      <header className="glass absolute inset-x-2 top-2 z-40 grid h-14 grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-2 rounded-panel px-2 lg:inset-x-3 lg:top-3 lg:h-12 lg:grid-cols-[1fr_auto_1fr] lg:gap-3 lg:pl-3.5">
        <div className="flex min-w-0 items-center gap-2">
          {homeHref ? (
            <Link href={homeHref} className="hidden text-[15px] font-semibold tracking-tight text-navy lg:inline">Ellips</Link>
          ) : (
            <span className="hidden text-[15px] font-semibold tracking-tight text-navy lg:inline">Ellips</span>
          )}
          <div className="hidden h-[18px] w-px bg-hairline lg:block" aria-hidden />
          <div className="flex h-8 min-w-0 items-center gap-1 rounded-control px-2 text-[13px] font-semibold text-ink max-lg:h-11">
            <span className="truncate">{name}</span>
            <ChevronDown size={14} className="shrink-0 text-slate" aria-hidden />
          </div>
          {save && (
            <span
              aria-live="polite"
              className={`whitespace-nowrap text-[11px] ${save.isError ? 'font-semibold text-error' : 'text-slate'} ${saveLabel === 'Saved' ? 'max-lg:hidden' : ''}`}
            >
              {saveLabel}
            </span>
          )}
          <button
            type="button"
            aria-label="Import / Scenes"
            title="Import / Scenes"
            onClick={() => setCaptureOpen(true)}
            className="hidden h-8 items-center gap-1.5 rounded-control px-2 text-[13px] font-medium text-slate transition-colors hover:bg-ink/5 hover:text-ink lg:inline-flex"
          >
            <Box size={16} aria-hidden />
            <span className="max-xl:hidden">Import / Scenes</span>
          </button>
        </div>

        <div className="flex items-center gap-2">
          <NavModeSegment />
          <div className="hidden lg:block"><ViewModeSegment /></div>
        </div>

        <div className="flex items-center justify-end gap-1 lg:gap-2">
          <button type="button" title="Undo (Ctrl+Z)" aria-label="Undo" onClick={undoSceneAction} disabled={!canUndo} className="icon-btn max-lg:hidden">
            <Undo2 size={16} aria-hidden />
          </button>
          <button type="button" title="Redo (Ctrl+Y)" aria-label="Redo" onClick={redoSceneAction} disabled={!canRedo} className="icon-btn max-lg:hidden">
            <Redo2 size={16} aria-hidden />
          </button>
          {save && (
            <button
              type="button"
              onClick={save.onSave}
              disabled={save.disabled}
              className="hidden h-8 items-center rounded-control px-3 text-[13px] font-medium text-slate transition-colors hover:bg-ink/5 hover:text-ink disabled:pointer-events-none disabled:opacity-50 lg:inline-flex"
            >
              Save
            </button>
          )}

          <div ref={moreRef} className="relative">
            <button
              type="button"
              aria-label="More actions"
              aria-haspopup="true"
              aria-expanded={moreOpen}
              onClick={() => setMoreOpen((open) => !open)}
              className="icon-btn"
            >
              <Ellipsis size={16} aria-hidden />
            </button>
            {moreOpen && (
              <div role="group" aria-label="More actions" className="absolute right-0 top-full z-40 mt-2 w-64 rounded-panel border border-hairline bg-paper p-1.5 shadow-float">
                {/* Compact only: what the narrow toolbar leaves out */}
                <div className="lg:hidden">
                  <div className="flex flex-col items-start gap-1.5 px-2 pb-2 pt-1">
                    <span className="text-[11px] font-semibold text-slate">Show</span>
                    <ViewModeSegment testId="view-mode-menu" />
                  </div>
                  <button type="button" className={MENU_ITEM} onClick={pick(() => setCaptureOpen(true))}>
                    <Box size={16} aria-hidden className="text-slate" />
                    Import or scenes
                  </button>
                  <button type="button" className={MENU_ITEM} disabled={!canUndo} onClick={pick(undoSceneAction)}>
                    <Undo2 size={16} aria-hidden className="text-slate" />
                    Undo
                  </button>
                  <button type="button" className={MENU_ITEM} disabled={!canRedo} onClick={pick(redoSceneAction)}>
                    <Redo2 size={16} aria-hidden className="text-slate" />
                    Redo
                  </button>
                  {save && (
                    <button type="button" className={MENU_ITEM} disabled={save.disabled} onClick={pick(save.onSave)}>
                      <Save size={16} aria-hidden className="text-slate" />
                      Save now
                    </button>
                  )}
                  <div className="my-1 h-px bg-hairline" aria-hidden />
                </div>
                {homeHref && (
                  <Link href={homeHref} className={MENU_ITEM} onClick={() => setMoreOpen(false)}>
                    All projects
                  </Link>
                )}
                {moreItems.map((item) => (
                  <button
                    key={item.label}
                    type="button"
                    aria-pressed={item.pressed}
                    disabled={item.disabled}
                    onClick={pick(item.onSelect)}
                    className={`${MENU_ITEM} ${item.pressed ? 'bg-ink/[0.07] font-semibold' : ''}`}
                  >
                    {item.label}
                  </button>
                ))}
                {/* Client presentations are share links; /present only redirects to the project list. */}
                {onShare ? (
                  <button type="button" className={MENU_ITEM} onClick={pick(onShare)}>
                    <Play size={16} aria-hidden className="text-slate" />
                    Present
                  </button>
                ) : (
                  <Link href="/present" className={MENU_ITEM} onClick={() => setMoreOpen(false)}>
                    <Play size={16} aria-hidden className="text-slate" />
                    Present
                  </Link>
                )}
                <button type="button" className={MENU_ITEM} disabled title="Export is not available yet">
                  <Download size={16} aria-hidden className="text-slate" />
                  Export
                </button>
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={onShare}
            disabled={!onShare}
            className="btn-primary max-lg:h-11 max-lg:px-4"
          >
            Share
          </button>
        </div>
      </header>

      {error && (
        <p role="alert" className="glass absolute left-1/2 top-[68px] z-30 max-w-[calc(100%-16px)] -translate-x-1/2 rounded-control px-3 py-1.5 text-[13px] text-error lg:top-[72px]">
          {error}
        </p>
      )}

      {/* Panels: floating glass at lg and up, one bottom sheet with Ask / Scene tabs below that */}
      <div
        className={`sheet-glass absolute inset-x-2 bottom-2 z-30 flex flex-col overflow-hidden rounded-sheet lg:contents ${sheetOpen ? 'h-[42dvh]' : 'h-[84px]'}`}
      >
        <button
          type="button"
          aria-label={sheetOpen ? 'Collapse panels' : 'Expand panels'}
          aria-expanded={sheetOpen}
          onClick={() => setSheetOpen((open) => !open)}
          className="flex h-6 w-full shrink-0 items-center justify-center lg:hidden"
        >
          <span className="h-[5px] w-9 rounded-full bg-[#9AA7BC]" aria-hidden />
        </button>
        <div className="flex shrink-0 justify-center px-3 pb-1.5 lg:hidden">
          <div role="group" aria-label="Panel" className="seg">
            <button type="button" aria-pressed={tab === 'ask'} onClick={() => { setTab('ask'); setSheetOpen(true) }} className="seg-item">Ask</button>
            <button type="button" aria-pressed={tab === 'scene'} onClick={() => { setTab('scene'); setSheetOpen(true) }} className="seg-item">Scene</button>
          </div>
        </div>

        <aside
          aria-label="Scene"
          className={`${tab === 'scene' ? 'flex' : 'hidden'} min-h-0 flex-1 flex-col overflow-hidden lg:absolute lg:left-3 lg:top-[72px] lg:z-30 lg:max-h-[calc(100%-176px)] lg:w-[244px] lg:flex-none lg:rounded-panel lg:glass xl:w-[296px] ${leftOpen ? 'lg:flex' : 'lg:hidden'}`}
        >
          <div className="flex shrink-0 items-center justify-between gap-2 px-4 pb-1 pt-1 lg:pt-3">
            <SceneKindSegment />
            <button type="button" aria-label="Collapse Scene panel" title="Collapse Scene panel" onClick={() => togglePanel('left')} className="icon-btn -mr-2 max-lg:hidden">
              <PanelLeft size={16} aria-hidden />
            </button>
          </div>
          <div className="flex min-h-0 flex-1 flex-col">{scenePanel}</div>
        </aside>

        <aside
          aria-label="Ask"
          className={`${tab === 'ask' ? 'flex' : 'hidden'} min-h-0 flex-1 flex-col overflow-hidden lg:absolute lg:right-3 lg:top-[72px] lg:z-30 lg:max-h-[calc(100%-176px)] lg:w-[276px] lg:flex-none lg:rounded-panel lg:glass xl:w-[332px] ${rightOpen ? 'lg:flex' : 'lg:hidden'}`}
        >
          <button type="button" aria-label="Collapse Ask panel" title="Collapse Ask panel" onClick={() => togglePanel('right')} className="icon-btn absolute right-2 top-2 z-10 max-lg:hidden">
            <PanelRight size={16} aria-hidden />
          </button>
          <div className="flex min-h-0 flex-1 flex-col [&>*]:!h-auto [&>*]:min-h-0 [&>*]:flex-1">{askPanel}</div>
        </aside>
      </div>

      {/* Collapsed panels leave a single toggle so the scan shows through */}
      {!leftOpen && (
        <button type="button" aria-label="Show Scene panel" title="Show Scene panel" onClick={() => togglePanel('left')} className="glass icon-btn absolute left-3 top-[72px] z-30 max-lg:hidden">
          <PanelLeft size={16} aria-hidden />
        </button>
      )}
      {!rightOpen && (
        <button type="button" aria-label="Show Ask panel" title="Show Ask panel" onClick={() => togglePanel('right')} className="glass icon-btn absolute right-3 top-[72px] z-30 max-lg:hidden">
          <PanelRight size={16} aria-hidden />
        </button>
      )}

      {captureOpen && <VideoCaptureModal onClose={() => setCaptureOpen(false)} />}
    </div>
  )
}
