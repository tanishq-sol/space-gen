'use client'

import { useState, useRef, useEffect } from 'react'
import { Sparkles, Send, Image as ImageIcon, Loader2, Upload, X } from 'lucide-react'
import { useAppStore } from '@/lib/store'
import { api } from '@/lib/api'
import { ChatMessage as ChatMessageType } from '@/lib/types'
import { motion, AnimatePresence } from 'framer-motion'

export function ChatPanel() {
  const { chatMessages, addChatMessage, scene, isLoading, setIsLoading, setHeroImage } = useAppStore()
  const [input, setInput] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [chatMessages, isLoading])

  const handleSend = async () => {
    if (!input.trim() || isLoading) return
    
    const userMsg = input.trim()
    setInput('')
    
    addChatMessage({ role: 'user', content: userMsg, timestamp: Date.now() })
    setIsLoading(true)

    try {
      const isGenerative = /\b(generate|make|create|replace|change|swap|show|design|restyle|visuali[sz]e)\b/i.test(userMsg)
      
      if (isGenerative) {
        const result = await api.generateImage(scene?.scene_id || 'default', userMsg)
        setHeroImage(result.image_url)
        addChatMessage({
          role: 'assistant',
          content: `Here's my visualization of your request. The room architecture has been preserved while applying the changes.`,
          image: result.image_url,
          timestamp: Date.now()
        })
      } else {
        const response = await api.chat(userMsg, scene?.scene_id || 'default', chatMessages)
        addChatMessage({
          role: 'assistant',
          content: response.response,
          timestamp: Date.now()
        })
      }
    } catch (e) {
      addChatMessage({
        role: 'assistant',
        content: 'I encountered an error processing your request. Please try again.',
        timestamp: Date.now()
      })
    } finally {
      setIsLoading(false)
    }
  }

  const quickActions = [
    'Make it more luxurious',
    'Show Scandinavian style',
    'Replace the sofa',
    'Generate 3 variants',
  ]

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-border flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="w-6 h-6 rounded-lg bg-gradient-brand flex items-center justify-center">
            <Sparkles size={12} className="text-white" />
          </div>
          <div>
            <h2 className="font-semibold text-sm leading-tight">Design Copilot</h2>
            <p className="text-[10px] text-text-muted leading-tight">Powered by Gemini</p>
          </div>
        </div>
        <span className="badge-accent">AI</span>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {chatMessages.length <= 1 && !isLoading && (
          <motion.div 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-3 pt-4"
          >
            <p className="text-xs text-text-muted text-center">Quick actions</p>
            <div className="grid grid-cols-2 gap-2">
              {quickActions.map((action) => (
                <button
                  key={action}
                  onClick={() => { setInput(action); inputRef.current?.focus() }}
                  className="px-3 py-2 text-xs text-left rounded-lg border border-border hover:border-accent/30 hover:bg-accent/5 text-text-secondary hover:text-text-primary transition-all duration-200"
                >
                  {action}
                </button>
              ))}
            </div>
          </motion.div>
        )}

        <AnimatePresence mode="popLayout">
          {chatMessages.map((msg, i) => (
            <motion.div
              key={`msg-${i}`}
              initial={{ opacity: 0, y: 10, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ duration: 0.2 }}
            >
              <ChatMessage message={msg} />
            </motion.div>
          ))}
        </AnimatePresence>

        {/* Typing indicator */}
        <AnimatePresence>
          {isLoading && (
            <motion.div 
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="flex gap-3 max-w-[90%]"
            >
              <div className="w-6 h-6 rounded-lg bg-gradient-brand flex items-center justify-center shrink-0">
                <Sparkles size={10} className="text-white" />
              </div>
              <div className="glass-elevated px-4 py-2.5 rounded-2xl rounded-tl-sm">
                <div className="flex items-center gap-1.5">
                  <div className="w-1.5 h-1.5 rounded-full bg-accent animate-bounce" style={{ animationDelay: '0ms' }} />
                  <div className="w-1.5 h-1.5 rounded-full bg-accent animate-bounce" style={{ animationDelay: '150ms' }} />
                  <div className="w-1.5 h-1.5 rounded-full bg-accent animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="p-4 border-t border-border shrink-0">
        <div className="relative flex items-center">
          <button 
            className="absolute left-3 text-text-muted hover:text-accent transition-colors"
            title="Upload reference image"
          >
            <ImageIcon size={16} />
          </button>
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            placeholder="Describe your design changes..."
            className="w-full bg-surface-elevated border border-border rounded-xl py-2.5 pl-10 pr-12 text-sm focus:outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/20 transition-all placeholder:text-text-muted"
          />
          <motion.button 
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="absolute right-2 p-1.5 bg-accent hover:bg-accent-dark disabled:bg-surface-elevated disabled:text-text-muted text-white rounded-lg transition-colors"
          >
            <Send size={13} />
          </motion.button>
        </div>
      </div>
    </div>
  )
}

function ChatMessage({ message }: { message: ChatMessageType }) {
  const isUser = message.role === 'user'
  
  return (
    <div className={`flex gap-3 max-w-[95%] ${isUser ? 'ml-auto flex-row-reverse' : ''}`}>
      {!isUser && (
        <div className="w-6 h-6 rounded-lg bg-gradient-brand flex items-center justify-center shrink-0 mt-0.5">
          <Sparkles size={10} className="text-white" />
        </div>
      )}
      <div className={`flex flex-col gap-2 ${isUser ? 'items-end' : 'items-start'}`}>
        <div 
          className={`px-3.5 py-2 rounded-2xl text-sm leading-relaxed ${
            isUser 
              ? 'bg-accent text-white rounded-tr-sm shadow-sm shadow-accent/20' 
              : 'glass-elevated rounded-tl-sm'
          }`}
        >
          {message.content}
        </div>
        {message.image && (
          <motion.div 
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="rounded-xl overflow-hidden border border-border max-w-[300px] shadow-card group"
          >
            <img 
              src={message.image} 
              alt="Generated visualization" 
              className="w-full h-auto object-cover transition-transform duration-300 group-hover:scale-[1.02]" 
            />
          </motion.div>
        )}
      </div>
    </div>
  )
}
