import React from 'react'
import { UploadCloud } from 'lucide-react'

export function ReferenceUpload() {
  return (
    <div className="w-full p-4 border-2 border-dashed border-border rounded-xl flex flex-col items-center justify-center text-center bg-surface hover:bg-surface-elevated transition-colors cursor-pointer">
      <UploadCloud size={24} className="text-text-secondary mb-2" />
      <h3 className="text-sm font-medium mb-1">Upload Reference</h3>
      <p className="text-xs text-text-secondary">Drag & drop or click to upload</p>
    </div>
  )
}
