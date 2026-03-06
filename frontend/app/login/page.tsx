'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { authApi } from '@/lib/api'
import toast from 'react-hot-toast'

export default function LoginPage() {
  const router = useRouter()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault()
    if (!username || !password) { setError('Enter username and password'); return }
    setLoading(true)
    setError('')
    try {
      const res = await authApi.login(username, password)
      localStorage.setItem('access_token', res.data.access_token)
      localStorage.setItem('user', JSON.stringify(res.data.user))
      toast.success(`Welcome, ${res.data.user.name}!`)
      router.push('/dashboard')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#0e0d0b] flex items-center justify-center"
      style={{ backgroundImage: 'radial-gradient(ellipse at 20% 50%, #C9A84C08, transparent 50%), radial-gradient(ellipse at 80% 20%, #4ca8c908, transparent 50%)' }}>
      <div className="w-[380px] bg-[#13110e] border border-[#2a2318] rounded-xl p-10">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="w-14 h-14 rounded-full mx-auto mb-3"
            style={{ background: 'radial-gradient(circle at 35% 35%, #FFD700, #8B6914)', boxShadow: '0 0 24px #C9A84C55' }} />
          <div className="serif text-[26px] font-semibold text-[#e8d89a]">Sona ERP</div>
          <div className="text-[10px] text-[#5a4a2a] tracking-widest mt-1">JEWELLERY MANUFACTURING SYSTEM</div>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-4 p-3 rounded text-[12px] bg-[#2e0a0a] border border-[#4a0a0a] text-[#e04c4c]">
            {error}
          </div>
        )}

        <form onSubmit={handleLogin}>
          <div className="mb-4">
            <label className="block text-[10px] text-[#5a4a2a] tracking-widest uppercase mb-1.5">Username</label>
            <input value={username} onChange={e => setUsername(e.target.value)}
              className="erp-input" placeholder="Enter username" autoComplete="username" />
          </div>
          <div className="mb-6">
            <label className="block text-[10px] text-[#5a4a2a] tracking-widest uppercase mb-1.5">Password</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)}
              className="erp-input" placeholder="Enter password" autoComplete="current-password" />
          </div>
          <button type="submit" disabled={loading} className="btn-gold w-full justify-center py-3 text-[12px]">
            {loading ? 'Signing in...' : 'Sign In →'}
          </button>
        </form>

        <div className="mt-6 p-3 rounded text-[11px] text-[#5a4a2a] bg-[#1a1612] border border-[#2a2318]">
          Default login: <span className="text-[#8a7a5a]">admin</span> / <span className="text-[#8a7a5a]">password123</span>
        </div>
      </div>
    </div>
  )
}
