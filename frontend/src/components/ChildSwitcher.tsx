import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useChildren } from '@/lib/children'
import { useProfile } from '@/lib/profile'

export default function ChildSwitcher() {
  const { children, activeChild, activeChildId, setActiveChildId } = useChildren()
  const { activeRole } = useProfile()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    if (open) document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open])

  // Only show for parents
  if (activeRole === 'teacher') return null

  // 0 children — prompt to add a child
  if (children.length === 0) {
    return (
      <button
        onClick={() => navigate('/children')}
        className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg transition-colors"
        style={{ backgroundColor: 'rgba(255,255,255,0.1)' }}
      >
        <svg className="w-4 h-4" style={{ color: 'rgba(255,255,255,0.7)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
        </svg>
        <span className="text-xs font-medium" style={{ color: 'rgba(255,255,255,0.85)' }}>
          Add child
        </span>
      </button>
    )
  }

  // 1 child — static label
  if (children.length === 1 && activeChild) {
    return (
      <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg" style={{ backgroundColor: 'rgba(255,255,255,0.1)' }}>
        <span
          className="w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold"
          style={{ backgroundColor: 'rgba(255,255,255,0.2)', color: '#FFFFFF' }}
        >
          {activeChild.name[0].toUpperCase()}
        </span>
        <span className="text-xs font-medium" style={{ color: 'rgba(255,255,255,0.85)' }}>
          {activeChild.name}
        </span>
      </div>
    )
  }

  // 2+ children — dropdown
  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg transition-colors cursor-pointer"
        style={{ backgroundColor: open ? 'rgba(255,255,255,0.18)' : 'rgba(255,255,255,0.1)' }}
        onMouseEnter={(e) => { if (!open) e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.15)' }}
        onMouseLeave={(e) => { if (!open) e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.1)' }}
      >
        {activeChild && (
          <span
            className="w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold"
            style={{ backgroundColor: 'rgba(255,255,255,0.2)', color: '#FFFFFF' }}
          >
            {activeChild.name[0].toUpperCase()}
          </span>
        )}
        <span className="text-xs font-medium max-w-[80px] truncate" style={{ color: 'rgba(255,255,255,0.85)' }}>
          {activeChild?.name || 'Select child'}
        </span>
        <svg
          className="w-3 h-3 transition-transform"
          style={{ color: 'rgba(255,255,255,0.5)', transform: open ? 'rotate(180deg)' : 'rotate(0deg)' }}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
        </svg>
      </button>

      {open && (
        <div
          className="absolute top-full left-0 mt-1.5 min-w-[180px] rounded-xl border shadow-lg z-50 py-1 animate-in fade-in slide-in-from-top-1 duration-150"
          style={{ backgroundColor: '#FFFFFF', borderColor: 'rgba(0,0,0,0.08)' }}
        >
          {children.map((child) => (
            <button
              key={child.id}
              onClick={() => {
                setActiveChildId(child.id)
                setOpen(false)
              }}
              className="w-full flex items-center gap-2.5 px-3 py-2 text-left transition-colors hover:bg-gray-50"
            >
              <span
                className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0"
                style={{
                  backgroundColor: child.id === activeChildId ? '#1E1B4B' : '#F1F5F9',
                  color: child.id === activeChildId ? '#FFFFFF' : '#64748B',
                }}
              >
                {child.name[0].toUpperCase()}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-gray-900 truncate">{child.name}</p>
                <p className="text-[10px] text-gray-500">{child.grade}</p>
              </div>
              {child.id === activeChildId && (
                <svg className="w-4 h-4 text-emerald-500 shrink-0" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z" clipRule="evenodd" />
                </svg>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
