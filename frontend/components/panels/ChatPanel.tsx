'use client'

import { useState, useRef, useEffect } from 'react'
import { Sparkles, Send, Image as ImageIcon, Loader2 } from 'lucide-react'
import { useAppStore } from '@/lib/store'
import { api } from '@/lib/api'
import { ChatMessage as ChatMessageType } from '@/lib/types'

export function ChatPanel() {
  const { chatMessages, addChatMessage, scene, isLoading, setIsLoading, setHeroImage } = useAppStore()
  const [input, setInput] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)

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
    
    const newMessage: ChatMessageType = {
      role: 'user',
      content: userMsg,
      timestamp: Date.now()
    }
    
    addChatMessage(newMessage)
    setIsLoading(true)

    try {
      if (userMsg.toLowerCase().includes('generate') || userMsg.toLowerCase().includes('make')) {
        // Image generation flow
        const result = await api.generateImage(scene?.scene_id || 'test', userMsg)
        
        setHeroImage(result.image_url)
        
        addChatMessage({
          role: 'assistant',
          content: 'Here is a preview of your requested change. How does this look?',
          image: result.image_url,
          timestamp: Date.now()
        })
      } else {
        // Normal chat flow
        const response = await api.chat(userMsg, scene?.scene_id || 'test', chatMessages)
        addChatMessage({
          role: 'assistant',
          content: response.response,
          timestamp: Date.now()
        })
      }
    } catch (e) {
      addChatMessage({
        role: 'assistant',
        content: 'Sorry, I encountered an error processing your request.',
        timestamp: Date.now()
      })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-full bg-surface">
      <div className="p-4 border-b border-border flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <Sparkles size={18} className="text-accent" />
          <h2 className="font-semibold text-sm">AI Copilot</h2>
        </div>
        <span className="text-[10px] uppercase bg-accent/20 text-accent px-1.5 py-0.5 rounded border border-accent/30 font-semibold">
          Beta
        </span>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {chatMessages.map((msg, i) => (
          <ChatMessage key={i} message={msg} />
        ))}
        {isLoading && (
          <div className="flex gap-3 max-w-[90%]">
            <div className="w-6 h-6 rounded-full bg-accent/20 flex items-center justify-center shrink-0">
              <Sparkles size={12} className="text-accent" />
            </div>
            <div className="bg-surface-elevated text-text-primary px-3 py-2 rounded-2xl rounded-tl-sm text-sm border border-border">
              <Loader2 size={16} className="animate-spin text-accent" />
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="p-4 border-t border-border shrink-0 bg-surface">
        <div className="relative flex items-center">
          <button className="absolute left-3 text-text-secondary hover:text-text-primary transition-colors">
            <ImageIcon size={18} />
          </button>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            placeholder="Ask me to redesign or change objects..."
            className="w-full bg-surface-elevated border border-border rounded-full py-2.5 pl-10 pr-12 text-sm focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent transition-all placeholder:text-text-secondary"
          />
          <button 
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="absolute right-2 p-1.5 bg-accent hover:bg-indigo-600 disabled:bg-surface-elevated disabled:text-text-secondary text-white rounded-full transition-colors"
          >
            <Send size={14} />
          </button>
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
        <div className="w-6 h-6 rounded-full bg-accent/20 flex items-center justify-center shrink-0 mt-1">
          <Sparkles size={12} className="text-accent" />
        </div>
      )}
      <div className={`flex flex-col gap-2 ${isUser ? 'items-end' : 'items-start'}`}>
        <div 
          className={`px-3 py-2 rounded-2xl text-sm ${
            isUser 
              ? 'bg-accent text-white rounded-tr-sm' 
              : 'bg-surface-elevated text-text-primary rounded-tl-sm border border-border'
          }`}
        >
          {message.content}
        </div>
        {message.image && (
          <div className="rounded-lg overflow-hidden border border-border max-w-[280px] shadow-sm">
            <img src={message.image} alt="Generated result" className="w-full h-auto object-cover hover:scale-105 transition-transform cursor-pointer" />
          </div>
        )}
      </div>
    </div>
  )
}
