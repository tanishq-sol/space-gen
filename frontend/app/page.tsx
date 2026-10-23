'use client';

import React, { useEffect } from 'react';
import dynamic from 'next/dynamic';
import { ScenePanel } from '@/components/panels/ScenePanel';
import { ChatPanel } from '@/components/panels/ChatPanel';
import { EditorLayout } from '@/components/layout/EditorLayout';
import { useSpaceGenStore } from '@/lib/store';

const SceneViewer = dynamic(
  () => import('@/components/viewer/SceneViewer'),
  {
    ssr: false,
    loading: () => (
      <div className="w-full h-full flex items-center justify-center bg-background text-text-muted">
        <div className="flex flex-col items-center gap-3">
          <div className="w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin" />
          <span className="text-xs">Loading the room…</span>
        </div>
      </div>
    ),
  }
);

export default function EditorPage() {
  const { selectedObjectId, setSelectedObjectId, clearActiveModel } = useSpaceGenStore();

  useEffect(() => {
    // Start clean on page reload
    clearActiveModel();
  }, [clearActiveModel]);

  return (
    <EditorLayout scenePanel={<ScenePanel />} askPanel={<ChatPanel />}>
      <SceneViewer
        selectedId={selectedObjectId}
        onSelectObject={setSelectedObjectId}
      />
    </EditorLayout>
  );
}
