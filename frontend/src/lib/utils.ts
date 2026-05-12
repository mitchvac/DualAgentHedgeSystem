import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

export function formatPercentage(value: number): string {
  const sign = value >= 0 ? '+' : ''
  return `${sign}${value.toFixed(2)}%`
}

export function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function getStatusColor(status: string): string {
  switch (status?.toLowerCase()) {
    case 'active':
      return 'text-success'
    case 'closed':
      return 'text-muted-foreground'
    case 'killed':
      return 'text-danger'
    case 'armed':
      return 'text-warning'
    default:
      return 'text-muted-foreground'
  }
}

export function getStatusBg(status: string): string {
  switch (status?.toLowerCase()) {
    case 'active':
      return 'bg-success/15 text-success'
    case 'closed':
      return 'bg-muted text-muted-foreground'
    case 'killed':
      return 'bg-danger/15 text-danger'
    case 'armed':
      return 'bg-warning/15 text-warning'
    default:
      return 'bg-muted text-muted-foreground'
  }
}
