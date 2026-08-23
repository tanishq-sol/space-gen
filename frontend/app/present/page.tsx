'use client'

import { useAppStore } from '@/lib/store'
import { ArrowLeft, ArrowRight, X } from 'lucide-react'
import Link from 'next/link'
import { useState, useRef, useEffect } from 'react'

export default function PresentationPage() {
  const { heroImage, variants, scene } = useAppStore()
  
  // Example hardcoded images for hackathon demo
  const beforeImg = "https://images.unsplash.com/photo-1554995207-c18c203602cb"
  const afterImg = heroImage || "https://images.unsplash.com/photo-1586023492125-27b2c045efd7"

  return (
    <div className="h-screen w-screen bg-black text-white overflow-hidden relative flex flex-col">
      <div className="absolute top-6 left-6 z-50">
        <Link href="/">
          <button className="flex items-center gap-2 bg-black/50 hover:bg-black/80 backdrop-blur-md px-4 py-2 rounded-full border border-white/10 transition-all text-sm font-medium">
            <X size={16} /> Exit Presentation
          </button>
        </Link>
      </div>

      <div className="absolute bottom-8 left-1/2 -translate-x-1/2 z-50 bg-black/50 backdrop-blur-md px-6 py-3 rounded-full border border-white/10 flex items-center gap-6">
        <button className="hover:text-accent transition-colors"><ArrowLeft size={20} /></button>
        <span className="text-sm font-medium tracking-wider uppercase text-white/70">Before & After</span>
        <button className="hover:text-accent transition-colors"><ArrowRight size={20} /></button>
      </div>

      <div className="flex-1 w-full h-full relative flex items-center justify-center p-12">
        <div className="w-full max-w-6xl aspect-video relative rounded-2xl overflow-hidden border border-white/10 shadow-2xl">
          <ImageSlider beforeImage={beforeImg} afterImage={afterImg} />
        </div>
      </div>
    </div>
  )
}

function ImageSlider({ beforeImage, afterImage }: { beforeImage: string, afterImage: string }) {
  const [sliderPosition, setSliderPosition] = useState(50)
  const [isDragging, setIsDragging] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  const handleMove = (clientX: number) => {
    if (!containerRef.current) return
    const rect = containerRef.current.getBoundingClientRect()
    const x = Math.max(0, Math.min(clientX - rect.left, rect.width))
    const percent = (x / rect.width) * 100
    setSliderPosition(percent)
  }

  const handleMouseMove = (e: MouseEvent) => {
    if (!isDragging) return
    handleMove(e.clientX)
  }

  const handleTouchMove = (e: TouchEvent) => {
    if (!isDragging) return
    handleMove(e.touches[0].clientX)
  }

  useEffect(() => {
    if (isDragging) {
      window.addEventListener('mousemove', handleMouseMove)
      window.addEventListener('mouseup', () => setIsDragging(false))
      window.addEventListener('touchmove', handleTouchMove)
      window.addEventListener('touchend', () => setIsDragging(false))
    }
    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', () => setIsDragging(false))
      window.removeEventListener('touchmove', handleTouchMove)
      window.removeEventListener('touchend', () => setIsDragging(false))
    }
  }, [isDragging])

  return (
    <div 
      ref={containerRef}
      className="w-full h-full relative cursor-ew-resize select-none"
      onMouseDown={(e) => {
        setIsDragging(true)
        handleMove(e.clientX)
      }}
      onTouchStart={(e) => {
        setIsDragging(true)
        handleMove(e.touches[0].clientX)
      }}
    >
      {/* Before Image (Background) */}
      <img src={beforeImage} alt="Before" className="absolute inset-0 w-full h-full object-cover pointer-events-none" />
      
      {/* After Image (Clipped) */}
      <div 
        className="absolute inset-0 overflow-hidden pointer-events-none"
        style={{ clipPath: `inset(0 ${100 - sliderPosition}% 0 0)` }}
      >
        <img src={afterImage} alt="After" className="absolute inset-0 w-full h-full object-cover max-w-none" style={{ width: '100%', height: '100%' }} />
      </div>

      {/* Slider Line */}
      <div 
        className="absolute top-0 bottom-0 w-1 bg-white shadow-[0_0_10px_rgba(0,0,0,0.5)] pointer-events-none z-10 -ml-[2px]"
        style={{ left: `${sliderPosition}%` }}
      >
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-8 h-8 bg-white rounded-full shadow-lg flex items-center justify-center">
          <div className="flex gap-1">
            <div className="w-0.5 h-3 bg-gray-400 rounded-full"></div>
            <div className="w-0.5 h-3 bg-gray-400 rounded-full"></div>
          </div>
        </div>
      </div>

      {/* Labels */}
      <div className="absolute top-6 left-6 bg-black/50 backdrop-blur-md px-3 py-1 rounded text-white text-xs font-semibold tracking-wider pointer-events-none">BEFORE</div>
      <div className="absolute top-6 right-6 bg-black/50 backdrop-blur-md px-3 py-1 rounded text-white text-xs font-semibold tracking-wider pointer-events-none">AFTER</div>
    </div>
  )
}
