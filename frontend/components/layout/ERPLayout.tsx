'use client'
import Sidebar from './Sidebar'

interface ERPLayoutProps {
  children: React.ReactNode
  title: string
  subtitle?: string
  actions?: React.ReactNode
}

export default function ERPLayout({ children, title, subtitle, actions }: ERPLayoutProps) {
  return (
    <div className="flex min-h-screen bg-[#0e0d0b]">
      <Sidebar />
      <div className="ml-[210px] flex-1 flex flex-col">
        {/* Top bar */}
        <div className="sticky top-0 z-40 border-b border-[#2a2318] bg-[#0e0d0b] px-7 h-[60px] flex items-center justify-between">
          <div>
            <div className="serif text-[22px] font-semibold text-[#e8d89a]">{title}</div>
            {subtitle && <div className="text-[10px] text-[#5a4a2a] tracking-widest uppercase">{subtitle}</div>}
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1.5 text-[10px] text-[#4cc96f]">
              <div className="w-1.5 h-1.5 rounded-full bg-[#4cc96f]" style={{ boxShadow: '0 0 6px #4cc96f' }} />
              LIVE
            </div>
            {actions}
          </div>
        </div>

        {/* Page content */}
        <div className="flex-1 p-7 overflow-auto">
          {children}
        </div>
      </div>
    </div>
  )
}
