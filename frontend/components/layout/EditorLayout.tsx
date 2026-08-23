'use client'

import { useAppStore } from '@/lib/store'
import { Undo, Redo, Share2, Download, Play, Video } from 'lucide-react'
import Link from 'next/link'
import { useState } from 'react'
import { VideoCaptureModal } from '@/components/capture/VideoCaptureModal'

export function EditorLayout({ children }: { children: React.ReactNode }) {
  const { scene } = useAppStore()
  const [captureOpen, setCaptureOpen] = useState(false)
  
  return (
    <div className="flex flex-col h-full w-full bg-background overflow-hidden">
      {/* Top Header */}
      <header className="h-14 border-b border-border bg-surface px-4 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-4">
          <div className="font-bold text-accent text-lg flex items-center gap-2">
            <span className="text-xl">✨</span> SpaceGen
          </div>
          <div className="h-4 w-px bg-border"></div>
          <div className="text-sm font-medium">{scene?.room_type || 'Living Room Project'}</div>
          <button onClick={() => setCaptureOpen(true)} className="flex items-center gap-2 rounded-md border border-accent/30 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent transition hover:bg-accent/20"><Video size={14} /> Import capture</button>
        </div>
        
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1 border-r border-border pr-3">
            <button className="p-2 hover:bg-surface-elevated rounded text-text-secondary hover:text-text-primary transition-colors">
              <Undo size={18} />
            </button>
            <button className="p-2 hover:bg-surface-elevated rounded text-text-secondary hover:text-text-primary transition-colors">
              <Redo size={18} />
            </button>
          </div>
          <Link href="/present">
            <button className="flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-surface-elevated rounded transition-colors text-text-secondary">
              <Play size={16} /> Present
            </button>
          </Link>
          <button className="flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-surface-elevated rounded transition-colors">
            <Share2 size={16} /> Share
          </button>
          <button className="flex items-center gap-2 px-3 py-1.5 text-sm bg-accent hover:bg-indigo-600 text-white rounded transition-colors">
            <Download size={16} /> Export
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 flex overflow-hidden">
        {children}
      </main>

      {/* Bottom Status Bar */}
      <footer className="h-8 border-t border-border bg-surface px-4 flex items-center justify-between shrink-0 text-xs text-text-secondary">
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1"><div className="w-2 h-2 rounded-full bg-success"></div> Ready</span>
          <span>Objects: {scene?.objects?.length || 0}</span>
          <span>Style: {scene?.style || 'None'}</span>
        </div>
        <div>
          SpaceGen v0.1.0 MVP
        </div>
      </footer>
      {captureOpen && <VideoCaptureModal onClose={() => setCaptureOpen(false)} />}
    </div>
  )
}
