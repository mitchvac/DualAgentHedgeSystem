import { useState, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

interface TooltipProps {
  children: ReactNode
  content: string
  position?: 'top' | 'bottom' | 'left' | 'right'
  className?: string
  delay?: number
}

export default function Tooltip({
  children,
  content,
  position = 'top',
  className,
  delay = 400,
}: TooltipProps) {
  const [show, setShow] = useState(false)
  const [timer, setTimer] = useState<ReturnType<typeof setTimeout> | null>(null)

  const handleEnter = () => {
    const t = setTimeout(() => setShow(true), delay)
    setTimer(t)
  }

  const handleLeave = () => {
    if (timer) clearTimeout(timer)
    setShow(false)
  }

  const posClasses = {
    top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
    bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
    left: 'right-full top-1/2 -translate-y-1/2 mr-2',
    right: 'left-full top-1/2 -translate-y-1/2 ml-2',
  }

  const arrowClasses = {
    top: 'top-full left-1/2 -translate-x-1/2 border-l-transparent border-r-transparent border-b-0 border-t-gray-800',
    bottom: 'bottom-full left-1/2 -translate-x-1/2 border-l-transparent border-r-transparent border-t-0 border-b-gray-800',
    left: 'left-full top-1/2 -translate-y-1/2 border-t-transparent border-b-transparent border-r-0 border-l-gray-800',
    right: 'right-full top-1/2 -translate-y-1/2 border-t-transparent border-b-transparent border-l-0 border-r-gray-800',
  }

  return (
    <div
      className={cn('relative inline-flex', className)}
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
      onFocus={handleEnter}
      onBlur={handleLeave}
    >
      {children}
      {show && (
        <div
          className={cn(
            'absolute z-50 px-3 py-2 text-xs text-white bg-gray-800 rounded-lg shadow-lg whitespace-nowrap pointer-events-none',
            'border border-gray-700/50',
            posClasses[position]
          )}
        >
          {content}
          <span
            className={cn(
              'absolute w-0 h-0 border-4',
              arrowClasses[position]
            )}
          />
        </div>
      )}
    </div>
  )
}
