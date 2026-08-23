'use client'

import { ScenePanel } from '@/components/panels/ScenePanel'
import { ChatPanel } from '@/components/panels/ChatPanel'
import { SceneViewer } from '@/components/viewer/SceneViewer'
import { EditorLayout } from '@/components/layout/EditorLayout'
import { useEffect } from 'react'
import { useAppStore } from '@/lib/store'
import { api } from '@/lib/api'

export default function EditorPage() {
  const { setScene, scene, selectedObjectId, setSelectedObjectId, setSplatUrl } = useAppStore()

  useEffect(() => {
    // Load initial scene
    api.getScene('mock-scene-1').then(data => {
      setScene(data as any)
    })

    // Check if there is an existing/latest completed Gaussian Splat
    api.getLatestReconstructionJob().then(job => {
      if (job && job.status === 'completed') {
        setSplatUrl(api.getReconstructionModelUrl(job.job_id))
      }
    })
  }, [setScene, setSplatUrl])

  return (
    <EditorLayout>
      {/* Left Panel - 280px */}
      <div className="w-[280px] border-r border-border bg-surface flex flex-col shrink-0">
        <ScenePanel />
      </div>

      {/* Center - 3D Viewer */}
      <div className="flex-1 bg-background relative overflow-hidden">
        <SceneViewer 
          objects={scene?.objects || []} 
          selectedId={selectedObjectId} 
          onSelectObject={setSelectedObjectId} 
        />
      </div>

      {/* Right Panel - 380px */}
      <div className="w-[380px] border-l border-border bg-surface flex flex-col shrink-0">
        <ChatPanel />
      </div>
    </EditorLayout>
  )
}
