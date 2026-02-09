import { type ReactNode } from 'react'

interface SectionProps {
    children: ReactNode
    className?: string
}

interface SectionHeaderProps {
    children: ReactNode
    className?: string
}

interface SectionTitleProps {
    children: ReactNode
    as?: 'h2' | 'h3' | 'h4'
    className?: string
}

interface SectionContentProps {
    children: ReactNode
    className?: string
}

export function Section({ children, className = '' }: SectionProps) {
    return (
        <section className={`mb-12 ${className}`}>
            {children}
        </section>
    )
}

export function SectionHeader({ children, className = '' }: SectionHeaderProps) {
    return (
        <div className={`mb-4 pb-3 border-b border-border ${className}`}>
            {children}
        </div>
    )
}

export function SectionTitle({ children, as = 'h3', className = '' }: SectionTitleProps) {
    const Component = as
    const baseClasses = as === 'h2' ? 'text-2xl' : as === 'h3' ? 'text-xl' : 'text-lg'

    return (
        <Component className={`font-semibold ${baseClasses} ${className}`}>
            {children}
        </Component>
    )
}

export function SectionContent({ children, className = '' }: SectionContentProps) {
    return (
        <div className={className}>
            {children}
        </div>
    )
}

Section.Header = SectionHeader
Section.Title = SectionTitle
Section.Content = SectionContent
