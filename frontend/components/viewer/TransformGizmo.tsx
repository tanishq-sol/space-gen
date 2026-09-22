'use client'

import React, { useEffect, useRef } from 'react'
import { TransformControls } from '@react-three/drei'
import * as THREE from 'three'
import { useAppStore } from '@/lib/store'

interface TransformGizmoProps {
  targetRef: React.RefObject<THREE.Object3D>
  onDragChange?: (isDragging: boolean) => void
}

export function TransformGizmo({ targetRef, onDragChange }: TransformGizmoProps) {
  const transformRef = useRef<any>(null)
  const {
    selectedObjectId,
    gizmoMode,
    setGizmoMode,
    setSelectedObjectId,
    updateObjectTransform,
    deleteObject,
  } = useAppStore()

  // Keyboard hotkeys: W (translate), E (rotate), R (scale), Esc (deselect), Delete (remove)
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (!selectedObjectId) return
      // Ignore when user is typing in chat/input
      const target = e.target as HTMLElement
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') return

      const key = e.key.toLowerCase()
      if (key === 'w') {
        e.preventDefault()
        setGizmoMode('translate')
      } else if (key === 'e') {
        e.preventDefault()
        setGizmoMode('rotate')
      } else if (key === 'r') {
        e.preventDefault()
        setGizmoMode('scale')
      } else if (key === 'escape') {
        e.preventDefault()
        setSelectedObjectId(null)
      } else if (key === 'delete' || key === 'backspace') {
        e.preventDefault()
        deleteObject(selectedObjectId)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [selectedObjectId, setGizmoMode, setSelectedObjectId, deleteObject])

  // Attach controls to target ref
  useEffect(() => {
    if (!transformRef.current || !targetRef.current) return
    const controls = transformRef.current

    function handleDraggingChange(event: any) {
      onDragChange?.(event.value)
    }

    function handleChange() {
      if (!targetRef.current || !selectedObjectId) return
      const pos = targetRef.current.position
      const rot = targetRef.current.rotation
      const sc = targetRef.current.scale

      updateObjectTransform(selectedObjectId, {
        position: [pos.x, pos.y, pos.z],
        rotation: [rot.x, rot.y, rot.z],
        scale: [sc.x, sc.y, sc.z],
      })
    }

    controls.addEventListener('dragging-changed', handleDraggingChange)
    controls.addEventListener('change', handleChange)

    return () => {
      controls.removeEventListener('dragging-changed', handleDraggingChange)
      controls.removeEventListener('change', handleChange)
    }
  }, [targetRef, selectedObjectId, updateObjectTransform, onDragChange])

  if (!selectedObjectId || !targetRef.current) return null

  return (
    <TransformControls
      ref={transformRef}
      object={targetRef.current}
      mode={gizmoMode}
      size={0.85}
      space="local"
    />
  )
}
