import { type ReactNode } from 'react'

interface InputHelperProps {
    children: ReactNode
    className?: string
}

export function InputHelper({ children, className = '' }: InputHelperProps) {
    return (
        <p className={`text-xs text-muted-foreground mt-1.5 ${className}`}>
            {children}
        </p>
    )
}

interface InputErrorProps {
    children: ReactNode
    className?: string
}

export function InputError({ children, className = '' }: InputErrorProps) {
    return (
        <p className={`text-xs text-destructive mt-1.5 flex items-center gap-1 ${className}`}>
            <svg className="w-3.5 h-3.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            {children}
        </p>
    )
}
