import { type ReactNode } from 'react'

interface PageHeaderProps {
    children: ReactNode
    className?: string
}

interface PageHeaderTitleProps {
    children: ReactNode
    as?: 'h1' | 'h2'
    className?: string
}

interface PageHeaderSubtitleProps {
    children: ReactNode
    className?: string
}

interface PageHeaderActionsProps {
    children: ReactNode
    className?: string
}

export function PageHeader({ children, className = '' }: PageHeaderProps) {
    return (
        <div className={`mb-8 ${className}`}>
            {children}
        </div>
    )
}

export function PageHeaderTitle({ children, as = 'h1', className = '' }: PageHeaderTitleProps) {
    const Component = as
    const baseClasses = as === 'h1' ? 'text-3xl md:text-4xl mb-2' : 'text-2xl md:text-3xl mb-2'

    return (
        <Component className={`font-semibold ${baseClasses} ${className}`}>
            {children}
        </Component>
    )
}

export function PageHeaderSubtitle({ children, className = '' }: PageHeaderSubtitleProps) {
    return (
        <p className={`text-muted-foreground text-base md:text-lg ${className}`}>
            {children}
        </p>
    )
}

export function PageHeaderActions({ children, className = '' }: PageHeaderActionsProps) {
    return (
        <div className={`mt-4 flex flex-col sm:flex-row gap-3 ${className}`}>
            {children}
        </div>
    )
}

PageHeader.Title = PageHeaderTitle
PageHeader.Subtitle = PageHeaderSubtitle
PageHeader.Actions = PageHeaderActions
