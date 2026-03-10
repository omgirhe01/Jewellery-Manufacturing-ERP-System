'use client'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import ERPLayout from '@/components/layout/ERPLayout'
import { reportsApi, karigarApi, scrapApi, costingApi } from '@/lib/api'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, LineChart, Line, Legend } from 'recharts'

const GOLD_COLORS = ['#C9A84C','#e07b3b','#b57bee','#4ca8c9','#4cc96f','#e04c4c']

export default function ReportsPage() {
  const [tab, setTab] = useState<'dashboard'|'wages'|'scrap'|'profit'|'audit'>('dashboard')

  const { data: dash } = useQuery({ queryKey: ['dashReport'], queryFn: () => reportsApi.dashboard().then(r => r.data) })
  const { data: wages } = useQuery({ queryKey: ['wagesReport'], queryFn: () => reportsApi.wages().then(r => r.data), enabled: tab === 'wages' })
  const { data: scrapReport } = useQuery({ queryKey: ['scrapReport'], queryFn: () => scrapApi.report().then(r => r.data), enabled: tab === 'scrap' })
  const { data: profitReport } = useQuery({ queryKey: ['profitReport'], queryFn: () => costingApi.profitability().then(r => r.data), enabled: tab === 'profit' })
  const { data: audit } = useQuery({ queryKey: ['auditReport'], queryFn: () => reportsApi.auditTrail().then(r => r.data), enabled: tab === 'audit' })

  const TABS = [
    { key: 'dashboard', label: 'Production Dashboard' },
    { key: 'wages', label: 'Artisan Wages' },
    { key: 'scrap', label: 'Scrap Analysis' },
    { key: 'profit', label: 'Profitability' },
    { key: 'audit', label: 'Audit Trail' },
  ]

  return (
    <ERPLayout title="Reports" subtitle="ANALYTICS & INSIGHTS">
      {/* Tab bar */}
      <div className="flex gap-2 mb-5 flex-wrap">
        {TABS.map(t => (
          <button key={t.key} onClick={() => setTab(t.key as any)}
            className={`text-[11px] px-4 py-2 rounded border transition-all ${tab === t.key ? 'bg-[#C9A84C18] text-[#C9A84C] border-[#C9A84C33]' : 'text-[#5a4a2a] border-transparent hover:text-[#e8e0d0]'}`}>
            {t.label}
          </button>
        ))}
      </div>

      {/* PRODUCTION DASHBOARD */}
      {tab === 'dashboard' && dash && (
        <div className="space-y-5">
          <div className="grid grid-cols-4 gap-3.5">
            {[
              { l: 'Total Jobs', v: dash.jobs.total, c: '#C9A84C' },
              { l: 'Active', v: dash.jobs.active, c: '#4cc96f' },
              { l: 'QC Pending', v: dash.jobs.qc_pending, c: '#e07b3b' },
              { l: 'Completed', v: dash.jobs.completed, c: '#b57bee' },
            ].map(m => (
              <div key={m.l} className="erp-card p-5">
                <div className="text-[10px] text-[#5a4a2a] uppercase tracking-widest mb-2">{m.l}</div>
                <div className="serif text-[36px] font-bold" style={{ color: m.c }}>{m.v}</div>
              </div>
            ))}
          </div>

          <div className="erp-card p-5">
            <div className="text-[10px] text-[#5a4a2a] uppercase tracking-widest mb-4">Pipeline by Stage</div>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={dash.pipeline}>
                <XAxis dataKey="stage" tick={{ fill: '#5a4a2a', fontSize: 9 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#5a4a2a', fontSize: 9 }} axisLine={false} tickLine={false} allowDecimals={false} />
                <Tooltip contentStyle={{ background: '#13110e', border: '1px solid #2a2318', color: '#e8e0d0', fontSize: 11 }} />
                <Bar dataKey="count" fill="#C9A84C" radius={[4,4,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* WAGES */}
      {tab === 'wages' && wages && (
        <div className="erp-card">
          <div className="p-4 border-b border-[#2a2318] text-[10px] text-[#5a4a2a] uppercase tracking-widest">Artisan Wages Report</div>
          <table className="erp-table">
            <thead><tr><th>Artisan</th><th>Code</th><th>Skill</th><th>Total Wages</th><th>Metal Balance</th></tr></thead>
            <tbody>
              {wages.map((k: any) => (
                <tr key={k.code}>
                  <td className="font-medium">{k.karigar}</td>
                  <td className="text-[#C9A84C]">{k.code}</td>
                  <td className="text-[#8a7a5a]">{k.metal_balance}</td>
                  <td className="text-[#4cc96f]">₹{Number(k.total_wages).toLocaleString('en-IN', { maximumFractionDigits: 2 })}</td>
                  <td className={Number(k.metal_balance) > 0 ? 'text-[#e07b3b]' : 'text-[#5a4a2a]'}>{Number(k.metal_balance).toFixed(3)}g</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* SCRAP */}
      {tab === 'scrap' && scrapReport && (
        <div className="grid grid-cols-2 gap-5">
          <div className="erp-card p-5">
            <div className="text-[10px] text-[#5a4a2a] uppercase tracking-widest mb-4">Scrap by Type</div>
            <div className="text-[#C9A84C] serif text-[32px] font-bold mb-2">{Number(scrapReport.total_weight).toFixed(3)}g</div>
            <div className="text-[10px] text-[#5a4a2a] mb-4">Total scrap collected</div>
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie data={Object.entries(scrapReport.by_type || {}).map(([k, v]) => ({ name: k, value: v }))}
                  dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80}>
                  {Object.keys(scrapReport.by_type || {}).map((_, i) => (
                    <Cell key={i} fill={GOLD_COLORS[i % GOLD_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ background: '#13110e', border: '1px solid #2a2318', fontSize: 11 }} />
                <Legend wrapperStyle={{ fontSize: 10, color: '#8a7a5a' }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="erp-card p-5">
            <div className="text-[10px] text-[#5a4a2a] uppercase tracking-widest mb-4">Scrap by Status</div>
            {scrapReport.by_status?.map((s: any) => (
              <div key={s.status} className="flex justify-between py-3 border-b border-[#1a1612] text-[11px]">
                <span className="text-[#8a7a5a]">{s.status}</span>
                <div className="text-right">
                  <div className="text-[#e8e0d0]">{s.count} batches</div>
                  <div className="text-[#5a4a2a]">{Number(s.weight).toFixed(3)}g</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* PROFITABILITY */}
      {tab === 'profit' && profitReport && (
        <div className="erp-card">
          <div className="p-4 border-b border-[#2a2318] text-[10px] text-[#5a4a2a] uppercase tracking-widest">Job Profitability Analysis</div>
          <table className="erp-table">
            <thead><tr><th>Job ID</th><th>Total Cost</th><th>Sale Price</th><th>Profit/Loss</th><th>Margin</th></tr></thead>
            <tbody>
              {profitReport.map((r: any) => (
                <tr key={r.job_id}>
                  <td className="text-[#C9A84C]">#{r.job_id}</td>
                  <td>₹{Number(r.total_cost).toLocaleString('en-IN', { maximumFractionDigits: 2 })}</td>
                  <td>₹{Number(r.sale_price).toLocaleString('en-IN', { maximumFractionDigits: 2 })}</td>
                  <td className={r.profit >= 0 ? 'text-[#4cc96f]' : 'text-[#e04c4c]'}>₹{Number(r.profit).toLocaleString('en-IN', { maximumFractionDigits: 2 })}</td>
                  <td className={r.margin_pct >= 0 ? 'text-[#4cc96f]' : 'text-[#e04c4c]'}>{r.margin_pct.toFixed(2)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* AUDIT TRAIL */}
      {tab === 'audit' && audit && (
        <div className="erp-card">
          <div className="p-4 border-b border-[#2a2318] text-[10px] text-[#5a4a2a] uppercase tracking-widest">Audit Trail — Last 50 Actions</div>
          <table className="erp-table">
            <thead><tr><th>User ID</th><th>Action</th><th>Module</th><th>Record</th><th>Time</th></tr></thead>
            <tbody>
              {audit.items?.map((l: any) => (
                <tr key={l.id}>
                  <td className="text-[#5a4a2a]">#{l.user_id}</td>
                  <td>{l.action}</td>
                  <td><span className="badge badge-blue">{l.module}</span></td>
                  <td className="text-[#5a4a2a]">{l.record_id || '—'}</td>
                  <td className="text-[#5a4a2a] text-[10px]">{l.at ? new Date(l.at).toLocaleString('en-IN') : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </ERPLayout>
  )
}
