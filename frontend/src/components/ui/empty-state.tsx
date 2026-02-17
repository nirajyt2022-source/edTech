import { type ReactNode } from 'react'

interface EmptyStateProps {
    icon?: ReactNode
    title: string
    description?: string
    action?: ReactNode
    className?: string
}

export function EmptyState({ icon, title, description, action, className = '' }: EmptyStateProps) {
    return (
        <div className={`flex flex-col items-center justify-center text-center py-12 px-4 ${className}`}>
            {icon && (
                <div className="mb-5 w-16 h-16 rounded-2xl bg-primary/8 flex items-center justify-center text-muted-foreground/50">
                    {icon}
                </div>
            )}
            <h4 className="text-lg font-semibold font-serif text-foreground mb-2">
                {title}
            </h4>
            {description && (
                <p className="text-sm text-muted-foreground max-w-md mb-6">
                    {description}
                </p>
            )}
            {action && (
                <div>
                    {action}
                </div>
            )}
        </div>
    )
}
