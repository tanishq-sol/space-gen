import type { Metadata, Viewport } from 'next'
import { Hanken_Grotesk, JetBrains_Mono } from 'next/font/google'
import './globals.css'

const hanken = Hanken_Grotesk({
  subsets: ['latin'],
  weight: ['600'],
  variable: '--font-display',
  display: 'swap',
})

const jbMono = JetBrains_Mono({ 
  subsets: ['latin'], 
  variable: '--',
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'Ellips',
  description: 'Transform real spaces into interactive 3D digital twins. AI-powered design copilot for architects and interior designers.',
  keywords: ['3D reconstruction', 'interior design', 'AI', 'gaussian splatting', 'architecture', 'digital twin'],
  authors: [{ name: 'Ellips' }],
  openGraph: {
    title: 'Ellips',
    description: 'Walk in with a phone. Walk out with a design.',
    type: 'website',
  },
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#F5F7FA',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${hanken.variable} ${jbMono.variable} font-sans h-screen w-screen overflow-hidden bg-background text-text-primary flex flex-col`}>
        {children}
      </body>
    </html>
  )
}
