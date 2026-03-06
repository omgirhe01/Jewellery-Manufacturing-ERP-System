'use client'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { authApi } from '@/lib/api'
import toast from 'react-hot-toast'

const NAV = [
  { section: 'Overview', items: [{ href: '/dashboard', icon: '⬡', label: 'Dashboard' }] },
  { section: 'Production', items: [
    { href: '/jobs', icon: '◈', label: 'Job Orders' },
    { href: '/production', icon: '⊞', label: 'Production' },
    { href: '/weighing', icon: '⚖', label: 'Weighing Scale' },
  ]},
  { section: 'Metal & Artisan', items: [
    { href: '/metal', icon: '◎', label: 'Metal Ledger' },
    { href: '/karigar', icon: '✦', label: 'Karigar' },
  ]},
  { section: 'Materials', items: [
    { href: '/inventory', icon: '📦', label: 'Inventory' },
    { href: '/scrap', icon: '⋯', label: 'Scrap' },
    { href: '/refinery', icon: '⟳', label: 'Refinery' },
  ]},
  { section: 'Finance', items: [
    { href: '/costing', icon: '₹', label: 'Costing' },
    { href: '/reports', icon: '↗', label: 'Reports' },
  ]},
  { section: 'Admin', items: [{ href: '/users', icon: '⊙', label: 'Users' }] },
]

export default function Sidebar() {
  const pathname = usePathname()
  const router = useRouter()

  const user = typeof window !== 'undefined'
    ? JSON.parse(localStorage.getItem('user') || '{}') : {}

  async function handleLogout() {
    await authApi.logout()
    localStorage.removeItem('access_token')
    localStorage.removeItem('user')
    router.push('/login')
    toast.success('Logged out')
  }

  return (
    <aside className="fixed top-0 left-0 h-screen w-[210px] border-r border-[#2a2318] bg-[#0e0d0b] flex flex-col z-50">
      {/* Logo */}
      <div className="flex items-center gap-3 p-4 border-b border-[#2a2318]">
        <div className="w-8 h-8 rounded-full flex-shrink-0"
          style={{ background: 'radial-gradient(circle at 35% 35%, #FFD700, #8B6914)', boxShadow: '0 0 16px #C9A84C44' }} />
        <div>
          <div className="serif text-[20px] font-semibold text-[#e8d89a]">Sona ERP</div>
          <div className="text-[9px] text-[#5a4a2a] tracking-widest uppercase">Manufacturing</div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 overflow-y-auto">
        {NAV.map(section => (
          <div key={section.section} className="mb-5">
            <div className="text-[9px] text-[#5a4a2a] tracking-[0.15em] uppercase px-5 mb-1">{section.section}</div>
            {section.items.map(item => {
              const active = pathname.startsWith(item.href)
              return (
                <Link key={item.href} href={item.href}
                  className={`flex items-center gap-2.5 px-5 py-2.5 text-[12px] tracking-wider border-l-2 transition-all
                    ${active ? 'bg-[#1e1a14] text-[#e8d89a] border-[#C9A84C]' : 'text-[#8a7a5a] border-transparent hover:bg-[#1e1a14] hover:text-[#e8e0d0]'}`}>
                  <span className="text-sm w-5 text-center">{item.icon}</span>
                  {item.label}
                </Link>
              )
            })}
          </div>
        ))}
      </nav>

      {/* User */}
      <div className="p-4 border-t border-[#2a2318] flex items-center gap-2.5">
        <div className="w-7 h-7 rounded-full bg-[#1e1a14] border border-[#2a2318] flex items-center justify-center text-[11px] text-[#C9A84C]">
          {user.name?.[0] || 'A'}
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[11px] text-[#e8e0d0] truncate">{user.name || 'Admin'}</div>
          <div className="text-[9px] text-[#5a4a2a] truncate">{user.role || 'Admin'}</div>
        </div>
        <button onClick={handleLogout} className="text-[#5a4a2a] hover:text-[#e04c4c] text-sm" title="Logout">⏻</button>
      </div>
    </aside>
  )
}
