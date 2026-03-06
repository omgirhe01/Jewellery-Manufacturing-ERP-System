'use client'
import { useQuery } from '@tanstack/react-query'
import ERPLayout from '@/components/layout/ERPLayout'
import { reportsApi, jobsApi } from '@/lib/api'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import Link from 'next/link'

const STAGE_COLORS: Record<string, string> = {
  Design: '#C9A84C', Wax: '#b57bee', CAM: '#4ca8c9', Casting: '#e07b3b',
  Filing: '#4cc9a8', 'Pre-polish': '#e0b43b', StoneSetting: '#e0b43b',
  Polishing: '#4cc9a8', QC: '#c94c6f', Finished: '#4cc96f', Dispatch: '#4cc96f'
}

function MetricCard({ label, value, sub, color }: any) {
  return (
    <div className="erp-card p-5 hover:border-[#C9A84C44] transition-colors">
      <div className="text-[10px] text-[#5a4a2a] tracking-widest uppercase mb-2">{label}</div>
      <div className="serif text-[38px] font-bold leading-none" style={{ color }}>{value}</div>
      <div className="text-[10px] text-[#5a4a2a] mt-1.5">{sub}</div>
    </div>
  )
}

export default function DashboardPage() {
  const { data: dash, isLoading } = useQuery({ queryKey: ['dashboard'], queryFn: () => reportsApi.dashboard().then(r => r.data) })
  const { data: recentJobs } = useQuery({ queryKey: ['recentJobs'], queryFn: () => jobsApi.list({ per_page: 8 }).then(r => r.data) })

  if (isLoading) return <ERPLayout title="Dashboard"><div className="text-[#5a4a2a] p-8">Loading...</div></ERPLayout>

  const pipelineData = dash?.pipeline?.filter((s: any) => s.count > 0) || []

  return (
    <ERPLayout title="Dashboard" subtitle="REAL-TIME PRODUCTION OVERVIEW">
      {/* Metrics */}
      <div className="grid grid-cols-4 gap-3.5 mb-5">
        <MetricCard label="Total Jobs" value={dash?.jobs?.total ?? '—'} sub="All time" color="#C9A84C" />
        <MetricCard label="Active" value={dash?.jobs?.active ?? '—'} sub="In production" color="#4cc96f" />
        <MetricCard label="QC Pending" value={dash?.jobs?.qc_pending ?? '—'} sub="Awaiting QC" color="#e07b3b" />
        <MetricCard label="Completed" value={dash?.jobs?.completed ?? '—'} sub="Done / dispatched" color="#b57bee" />
      </div>

      {/* Pipeline Chart + Alerts */}
      <div className="grid grid-cols-[1fr_260px] gap-3.5 mb-5">
        <div className="erp-card">
          <div className="px-5 py-3.5 border-b border-[#2a2318] text-[10px] text-[#8a7a5a] tracking-widest uppercase">
            Production Pipeline — Active Jobs by Stage
          </div>
          <div className="p-5" style={{ height: 200 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={dash?.pipeline || []} margin={{ top: 0, right: 0, bottom: 0, left: -30 }}>
                <XAxis dataKey="stage" tick={{ fill: '#5a4a2a', fontSize: 9 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#5a4a2a', fontSize: 9 }} axisLine={false} tickLine={false} allowDecimals={false} />
                <Tooltip contentStyle={{ background: '#13110e', border: '1px solid #2a2318', color: '#e8e0d0', fontSize: 11, fontFamily: 'DM Mono' }} />
                <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                  {(dash?.pipeline || []).map((s: any) => (
                    <Cell key={s.stage} fill={STAGE_COLORS[s.stage] || '#C9A84C'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="erp-card flex flex-col">
          <div className="px-5 py-3.5 border-b border-[#2a2318] text-[10px] text-[#8a7a5a] tracking-widest uppercase">
            Alerts
          </div>
          <div className="p-4 flex-1 space-y-3">
            <div className="p-3 rounded bg-[#2e1a0a] border border-[#4a2a0a] text-[11px] text-[#e07b3b]">
              ⚠ {dash?.low_stock_alerts ?? 0} low stock items
            </div>
            <div className="p-3 rounded bg-[#1a1a2e] border border-[#2a2a4a] text-[11px] text-[#b57bee]">
              🔬 {dash?.jobs?.qc_pending ?? 0} jobs in QC queue
            </div>
            <div className="p-3 rounded bg-[#1a2e1a] border border-[#2a4a2a] text-[11px] text-[#4cc96f]">
              📦 {dash?.scrap_pending_batches ?? 0} scrap batches pending
            </div>
            <div className="p-3 rounded bg-[#2e240a] border border-[#4a3a0a] text-[11px] text-[#C9A84C]">
              💰 Metal value: ₹{Number(dash?.metal_stock_value ?? 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
            </div>
          </div>
        </div>
      </div>

      {/* Recent Jobs */}
      <div className="erp-card">
        <div className="px-5 py-3.5 border-b border-[#2a2318] flex items-center justify-between">
          <span className="text-[10px] text-[#8a7a5a] tracking-widest uppercase">Recent Job Orders</span>
          <Link href="/jobs" className="text-[11px] text-[#C9A84C] hover:text-[#e8d89a]">View All →</Link>
        </div>
        <div className="overflow-x-auto">
          <table className="erp-table">
            <thead>
              <tr>
                <th>Job Code</th><th>Design</th><th>Customer</th><th>Metal</th><th>Stage</th><th>Status</th><th>Priority</th>
              </tr>
            </thead>
            <tbody>
              {recentJobs?.items?.map((j: any) => (
                <tr key={j.id}>
                  <td className="text-[#C9A84C] font-medium">{j.job_code}</td>
                  <td>{j.design_name}</td>
                  <td className="text-[#8a7a5a]">{j.customer_name}</td>
                  <td><span className="badge badge-gold">{j.metal_type}</span></td>
                  <td><span className="badge badge-blue">{j.current_stage}</span></td>
                  <td><StatusBadge status={j.status} /></td>
                  <td><span className={`badge ${j.priority === 'Urgent' ? 'badge-red' : j.priority === 'High' ? 'badge-orange' : 'badge-gray'}`}>{j.priority}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </ERPLayout>
  )
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    'Active': 'badge-green', 'QC Pending': 'badge-orange', 'Completed': 'badge-gold',
    'Dispatched': 'badge-blue', 'On Hold': 'badge-gray', 'Cancelled': 'badge-red'
  }
  return <span className={`badge ${map[status] || 'badge-gray'}`}>{status}</span>
}
