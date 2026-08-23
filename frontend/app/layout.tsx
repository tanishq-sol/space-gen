import type { Metadata } from 'next'
import { Inter, JetBrains_Mono } from 'next/font/google'
import './globals.css'

const inter = Inter({ subsets: ['latin'], variable: '--font-inter' })
const jbMono = JetBrains_Mono({ subsets: ['latin'], variable: '--font-mono' })

export const metadata: Metadata = {
  title: 'SpaceGen AI',
  description: 'AI-powered 3D space generation',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.variable} ${jbMono.variable} font-sans h-screen w-screen overflow-hidden bg-background text-text-primary flex flex-col`}>
        {children}
      </body>
    </html>
  )
}
