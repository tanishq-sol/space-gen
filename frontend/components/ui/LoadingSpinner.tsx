import { Loader2 } from 'lucide-react'

export function LoadingSpinner({ size = 24 }: { size?: number }) {
  return <Loader2 size={size} className="animate-spin text-accent" />
}
