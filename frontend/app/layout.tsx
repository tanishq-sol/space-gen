import type { Metadata, Viewport } from 'next'
import { Inter, JetBrains_Mono } from 'next/font/google'
import './globals.css'

const inter = Inter({ 
  subsets: ['latin'], 
  variable: '--font-inter',
  display: 'swap',
})

const jbMono = JetBrains_Mono({ 
  subsets: ['latin'], 
  variable: '--font-mono',
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'SpaceGen AI — Spatial Design Intelligence',
  description: 'Transform real spaces into interactive 3D digital twins. AI-powered design copilot for architects and interior designers.',
  keywords: ['3D reconstruction', 'interior design', 'AI', 'gaussian splatting', 'architecture', 'digital twin'],
  authors: [{ name: 'SpaceGen AI' }],
  openGraph: {
    title: 'SpaceGen AI — Spatial Design Intelligence',
    description: 'Walk in with a phone. Walk out with a design.',
    type: 'website',
  },
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#06060C',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body className={`${inter.variable} ${jbMono.variable} font-sans h-screen w-screen overflow-hidden bg-background text-text-primary flex flex-col`}>
        {children}
      </body>
    </html>
  )
}
