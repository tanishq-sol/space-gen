'use client'

import { useAppStore } from '@/lib/store'
import { 
  ArrowLeft, ArrowRight, X, Maximize2, Minimize2, 
  Sparkles, Layers, Download, Share2, Eye, CheckCircle2 
} from 'lucide-react'
import Link from 'next/link'
import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

export default function PresentationPage() {
  const { heroImage, beforeImage, variants, scene } = useAppStore()
  const [activeTab, setActiveTab] = useState<'compare' | 'variants'>('compare')
  const [selectedVariantIdx, setSelectedVariantIdx] = useState(0)
  const [isFullscreen, setIsFullscreen] = useState(false)

  // High quality default visuals
  const beforeImg = beforeImage || "https://images.unsplash.com/photo-1554995207-c18c203602cb?q=80&w=1600"
  const defaultVariants = [
    {
      style: 'Warm Minimalist',
      image: heroImage || "https://images.unsplash.com/photo-1618221195710-dd6b41faaea6?q=80&w=1600",
      description: 'Preserved concrete ceilings with organic bouclé curved seating and natural oak elements.'
    },
    {
      style: 'Quiet Luxury',
      image: "https://images.unsplash.com/photo-1600210492486-724fe5c67fb0?q=80&w=1600",
      description: 'Warm travertine surfaces, custom brushed bronze fixtures, and low-profile velvet seating.'
    },
    {
      style: 'Japandi Modern',
      image: "https://images.unsplash.com/photo-1595526114035-0d45ed16cfbf?q=80&w=1600",
      description: 'Slatted ash wood partitions, washi paper pendant lighting, and neutral linen palettes.'
    }
  ]

  const activeVariants = variants.length > 0 ? variants : defaultVariants
  const afterImg = activeVariants[selectedVariantIdx]?.image || heroImage || defaultVariants[0].image

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen?.()
      setIsFullscreen(true)
    } else {
      document.exitFullscreen?.()
      setIsFullscreen(false)
    }
  }

  useEffect(() => {
    const handleFsChange = () => {
      setIsFullscreen(!!document.fullscreenElement)
    }
    document.addEventListener('fullscreenchange', handleFsChange)
    return () => document.removeEventListener('fullscreenchange', handleFsChange)
  }, [])

  return (
    <div className="h-screen w-screen bg-[#05050A] text-text-primary overflow-hidden relative flex flex-col select-none">
      {/* Top Floating Nav */}
      <header className="absolute top-6 left-6 right-6 z-50 flex items-center justify-between pointer-events-none">
        <div className="pointer-events-auto flex items-center gap-3">
          <Link href="/">
            <motion.button 
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
              className="flex items-center gap-2 glass px-4 py-2 rounded-full text-xs font-medium hover:text-white transition-all shadow-panel"
            >
              <ArrowLeft size={14} /> Exit to Editor
            </motion.button>
          </Link>
          <div className="glass px-4 py-2 rounded-full text-xs font-medium flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
            <span>{scene?.room_type || 'Living Room Space'}</span>
          </div>
        </div>

        <div className="pointer-events-auto flex items-center gap-2">
          {/* Mode Switcher */}
          <div className="glass p-1 rounded-full flex items-center gap-1 shadow-panel">
            <button
              onClick={() => setActiveTab('compare')}
              className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                activeTab === 'compare' ? 'bg-accent text-white shadow-sm' : 'text-text-secondary hover:text-text-primary'
              }`}
            >
              Before & After
            </button>
            <button
              onClick={() => setActiveTab('variants')}
              className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                activeTab === 'variants' ? 'bg-accent text-white shadow-sm' : 'text-text-secondary hover:text-text-primary'
              }`}
            >
              Design Concepts ({activeVariants.length})
            </button>
          </div>

          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={toggleFullscreen}
            className="p-2.5 glass rounded-full text-text-secondary hover:text-text-primary transition-all shadow-panel"
            title="Toggle Fullscreen"
          >
            {isFullscreen ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
          </motion.button>
        </div>
      </header>

      {/* Main Presentation Viewport */}
      <main className="flex-1 w-full h-full relative flex items-center justify-center p-6 md:p-12 pt-20 pb-24">
        {activeTab === 'compare' ? (
          <motion.div 
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            className="w-full max-w-6xl h-full max-h-[82vh] relative rounded-2xl overflow-hidden border border-border/60 shadow-2xl glass"
          >
            <InteractiveCompareSlider 
              beforeImage={beforeImg} 
              afterImage={afterImg} 
              activeStyleName={activeVariants[selectedVariantIdx]?.style || 'AI Redesign'}
            />
          </motion.div>
        ) : (
          <motion.div 
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            className="w-full max-w-6xl h-full max-h-[82vh] grid grid-cols-1 md:grid-cols-3 gap-6 items-center"
          >
            {activeVariants.map((variant, idx) => (
              <motion.div
                key={variant.style}
                whileHover={{ y: -6, transition: { duration: 0.2 } }}
                onClick={() => {
                  setSelectedVariantIdx(idx)
                  setActiveTab('compare')
                }}
                className={`h-full max-h-[70vh] rounded-2xl overflow-hidden glass cursor-pointer border flex flex-col transition-all duration-300 ${
                  selectedVariantIdx === idx 
                    ? 'border-accent shadow-glow' 
                    : 'border-border/60 hover:border-border'
                }`}
              >
                <div className="relative flex-1 overflow-hidden">
                  <img 
                    src={variant.image} 
                    alt={variant.style}
                    className="w-full h-full object-cover transition-transform duration-500 hover:scale-105"
                  />
                  <div className="absolute top-3 right-3">
                    {selectedVariantIdx === idx && (
                      <div className="badge-accent flex items-center gap-1">
                        <CheckCircle2 size={10} /> Active
                      </div>
                    )}
                  </div>
                </div>
                <div className="p-5 bg-surface/90 border-t border-border/40">
                  <h3 className="font-semibold text-sm text-text-primary mb-1">{variant.style}</h3>
                  <p className="text-xs text-text-secondary line-clamp-2 leading-relaxed">{variant.description}</p>
                </div>
              </motion.div>
            ))}
          </motion.div>
        )}
      </main>

      {/* Bottom Floating Toolbar */}
      <footer className="absolute bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 pointer-events-auto">
        <div className="glass px-5 py-2.5 rounded-full flex items-center gap-4 shadow-panel text-xs text-text-secondary">
          <span className="font-medium text-text-primary">
            {activeVariants[selectedVariantIdx]?.style}
          </span>
          <div className="w-px h-4 bg-border" />
          <span>Architecture Preserved: <b className="text-emerald-400">100%</b></span>
          <div className="w-px h-4 bg-border" />
          <button 
            onClick={() => {
              const nextIdx = (selectedVariantIdx + 1) % activeVariants.length
              setSelectedVariantIdx(nextIdx)
            }}
            className="flex items-center gap-1 text-accent hover:text-accent-light transition-colors"
          >
            <span>Next Concept</span>
            <ArrowRight size={13} />
          </button>
        </div>
      </footer>
    </div>
  )
}

function InteractiveCompareSlider({ 
  beforeImage, 
  afterImage,
  activeStyleName,
}: { 
  beforeImage: string
  afterImage: string
  activeStyleName: string
}) {
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

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isDragging) return
      handleMove(e.clientX)
    }
    const handleTouchMove = (e: TouchEvent) => {
      if (!isDragging) return
      handleMove(e.touches[0].clientX)
    }
    const stopDrag = () => setIsDragging(false)

    if (isDragging) {
      window.addEventListener('mousemove', handleMouseMove)
      window.addEventListener('mouseup', stopDrag)
      window.addEventListener('touchmove', handleTouchMove)
      window.addEventListener('touchend', stopDrag)
    }
    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', stopDrag)
      window.removeEventListener('touchmove', handleTouchMove)
      window.removeEventListener('touchend', stopDrag)
    }
  }, [isDragging])

  return (
    <div 
      ref={containerRef}
      className="w-full h-full relative cursor-ew-resize select-none overflow-hidden"
      onMouseDown={(e) => {
        setIsDragging(true)
        handleMove(e.clientX)
      }}
      onTouchStart={(e) => {
        setIsDragging(true)
        handleMove(e.touches[0].clientX)
      }}
    >
      {/* Before Image (Base Layer) */}
      <img 
        src={beforeImage} 
        alt="Original Room Capture" 
        className="absolute inset-0 w-full h-full object-cover pointer-events-none" 
      />
      
      {/* After Image (Clipped Overlay Layer) */}
      <div 
        className="absolute inset-0 overflow-hidden pointer-events-none"
        style={{ clipPath: `inset(0 ${100 - sliderPosition}% 0 0)` }}
      >
        <img 
          src={afterImage} 
          alt="AI Redesigned Space" 
          className="absolute inset-0 w-full h-full object-cover max-w-none pointer-events-none" 
        />
      </div>

      {/* Vertical Slider Divider Line */}
      <div 
        className="absolute top-0 bottom-0 w-0.5 bg-white shadow-[0_0_12px_rgba(0,0,0,0.8)] pointer-events-none z-20"
        style={{ left: `${sliderPosition}%` }}
      >
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-9 h-9 bg-white text-black rounded-full shadow-2xl flex items-center justify-center border border-black/10">
          <div className="flex items-center gap-0.5">
            <ArrowLeft size={10} className="text-black/70" />
            <ArrowRight size={10} className="text-black/70" />
          </div>
        </div>
      </div>

      {/* Floating Badges */}
      <div className="absolute top-6 left-6 glass px-3.5 py-1.5 rounded-full text-xs font-semibold tracking-wider pointer-events-none z-10 text-white/90">
        ORIGINAL CAPTURE
      </div>
      <div className="absolute top-6 right-6 glass px-3.5 py-1.5 rounded-full text-xs font-semibold tracking-wider pointer-events-none z-10 text-accent-light border-accent/40">
        {activeStyleName.toUpperCase()}
      </div>
    </div>
  )
}
