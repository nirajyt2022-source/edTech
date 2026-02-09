import { cn } from '@/lib/utils'

interface SkeletonProps {
    className?: string
}

export function Skeleton({ className }: SkeletonProps) {
    return (
        <div className={cn('skeleton', className)} />
    )
}

interface SkeletonTextProps {
    className?: string
    size?: 'sm' | 'md' | 'lg'
    lines?: number
}

export function SkeletonText({ className, size = 'md', lines = 1 }: SkeletonTextProps) {
    const sizeClass = size === 'sm' ? 'skeleton-text-sm' : size === 'lg' ? 'skeleton-text-lg' : ''

    return (
        <>
            {Array.from({ length: lines }).map((_, i) => (
                <div key={i} className={cn('skeleton-text', sizeClass, className)} />
            ))}
        </>
    )
}

Skeleton.Text = SkeletonText
