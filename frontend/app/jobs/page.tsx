'use client'
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import ERPLayout from '@/components/layout/ERPLayout'
import { jobsApi, scaleApi } from '@/lib/api'
import toast from 'react-hot-toast'

const STAGES = ['Design','Wax','CAM','Casting','Filing','Pre-polish','StoneSetting','Polishing','QC','Finished','Dispatch']

export default function JobsPage() {
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [page, setPage] = useState(1)
  const [selectedJob, setSelectedJob] = useState<any>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [showAdvance, setShowAdvance] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['jobs', page, search, filterStatus],
    queryFn: () => jobsApi.list({ page, per_page: 20, q: search || undefined, status: filterStatus || undefined }).then(r => r.data)
  })

  const createMutation = useMutation({
    mutationFn: jobsApi.create,
    onSuccess: () => { toast.success('Job created!'); qc.invalidateQueries({ queryKey: ['jobs'] }); setShowCreate(false) }
  })

  const advanceMutation = useMutation({
    mutationFn: ({ id, data }: any) => jobsApi.advanceStage(id, data),
    onSuccess: (res) => { toast.success(`Moved to ${res.data.current_stage}`); qc.invalidateQueries({ queryKey: ['jobs'] }); setShowAdvance(false) }
  })

  return (
    <ERPLayout title="Job Orders" subtitle="JOB & PRODUCTION MANAGEMENT"
      actions={<button onClick={() => setShowCreate(true)} className="btn-gold text-[11px] py-2 px-4">+ New Job</button>}>

      {/* Filters */}
      <div className="flex items-center gap-3 mb-4">
        <input value={search} onChange={e => { setSearch(e.target.value); setPage(1) }}
          className="erp-input" style={{ width: 220 }} placeholder="Search job / design / barcode..." />
        <select value={filterStatus} onChange={e => { setFilterStatus(e.target.value); setPage(1) }} className="erp-input" style={{ width: 160 }}>
          <option value="">All Status</option>
          {['Active','On Hold','QC Pending','Completed','Dispatched','Cancelled'].map(s => <option key={s}>{s}</option>)}
        </select>
        <div className="text-[11px] text-[#5a4a2a]">{data?.total ?? 0} jobs</div>
      </div>

      <div className="flex gap-4 h-[calc(100vh-200px)]">
        {/* Table */}
        <div className="flex-1 erp-card overflow-auto">
          <table className="erp-table">
            <thead><tr>
              <th>Job Code</th><th>Design / Customer</th><th>Metal</th><th>Target Wt</th>
              <th>Stage</th><th>Status</th><th>Priority</th><th>Qty</th>
            </tr></thead>
            <tbody>
              {isLoading ? <tr><td colSpan={8} className="text-center text-[#5a4a2a] py-10">Loading...</td></tr>
              : data?.items?.map((j: any) => (
                <tr key={j.id} onClick={() => setSelectedJob(j)}>
                  <td className="text-[#C9A84C] font-medium">{j.job_code}</td>
                  <td><div>{j.design_name}</div><div className="text-[10px] text-[#5a4a2a]">{j.customer_name}</div></td>
                  <td><span className="badge badge-gold">{j.metal_type}</span></td>
                  <td className="text-[#e8e0d0]">{j.target_weight}g</td>
                  <td><span className="badge badge-blue text-[9px]">{j.current_stage}</span></td>
                  <td><span className={`badge ${j.status==='Active'?'badge-green':j.status==='QC Pending'?'badge-orange':j.status==='Completed'?'badge-gold':'badge-gray'}`}>{j.status}</span></td>
                  <td><span className={`badge ${j.priority==='Urgent'?'badge-red':j.priority==='High'?'badge-orange':'badge-gray'}`}>{j.priority}</span></td>
                  <td className="text-[#8a7a5a]">{j.order_qty} pcs</td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Pagination */}
          <div className="flex items-center gap-3 p-4 border-t border-[#2a2318] text-[11px] text-[#5a4a2a]">
            <span>Page {data?.page} of {data?.pages} · {data?.total} total</span>
            <button disabled={page <= 1} onClick={() => setPage(p => p - 1)} className="btn-outline text-[10px] py-1 px-3 disabled:opacity-40">← Prev</button>
            <button disabled={page >= (data?.pages || 1)} onClick={() => setPage(p => p + 1)} className="btn-outline text-[10px] py-1 px-3 disabled:opacity-40">Next →</button>
          </div>
        </div>

        {/* Detail Panel */}
        {selectedJob && (
          <div className="w-[290px] erp-card overflow-y-auto flex-shrink-0 p-4">
            <div className="flex items-center justify-between mb-4">
              <div className="serif text-[17px] text-[#e8d89a]">Job Detail</div>
              <button onClick={() => setSelectedJob(null)} className="text-[#5a4a2a] hover:text-[#e8e0d0]">×</button>
            </div>

            {/* Barcode visual */}
            <div className="text-center p-3 bg-[#0e0d0b] border border-[#2a2318] rounded mb-4">
              <div className="serif text-[18px] text-[#C9A84C] font-semibold">{selectedJob.job_code}</div>
              <div className="text-[9px] text-[#5a4a2a] mt-1 mb-2">{selectedJob.barcode_value}</div>
              <div className="flex gap-0.5 justify-center h-6 items-end">
                {Array.from({length: 28}, (_,i) => (
                  <div key={i} style={{ width: i%3===0?2:1, height: i%5===0?24:i%3===0?18:14,
                    background: '#C9A84C', borderRadius: 1, opacity: 0.6+(i%3)*0.15 }} />
                ))}
              </div>
            </div>

            {/* Details */}
            {[['Design', selectedJob.design_name], ['Customer', selectedJob.customer_name],
              ['Metal', selectedJob.metal_type], ['Qty', `${selectedJob.order_qty} pcs`],
              ['Target Wt', `${selectedJob.target_weight}g`], ['Priority', selectedJob.priority],
              ['Stage', selectedJob.current_stage],
            ].map(([l, v]) => (
              <div key={l} className="flex justify-between py-2 border-b border-[#1a1612] text-[11px]">
                <span className="text-[#5a4a2a]">{l}</span>
                <span className="text-[#e8e0d0]">{v || '—'}</span>
              </div>
            ))}

            {/* Stage tracker */}
            <div className="mt-4">
              <div className="text-[9px] text-[#5a4a2a] tracking-widest uppercase mb-3">Stage Progress</div>
              {STAGES.map((stage, i) => {
                const curr = STAGES.indexOf(selectedJob.current_stage)
                const done = i < curr
                const active = i === curr
                return (
                  <div key={stage} className="flex items-center gap-2 mb-2">
                    <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[9px] border flex-shrink-0
                      ${done ? 'bg-[#1a2e1a] border-[#4cc96f] text-[#4cc96f]' :
                        active ? 'bg-[#2e240a] border-[#C9A84C] text-[#C9A84C]' :
                        'bg-[#0e0d0b] border-[#2a2318] text-[#5a4a2a]'}`}>
                      {done ? '✓' : active ? '→' : ''}
                    </div>
                    <span className={`text-[11px] ${done ? 'text-[#5a4a2a]' : active ? 'text-[#e8d89a] font-medium' : 'text-[#3a3020]'}`}>{stage}</span>
                    {active && <span className="ml-auto text-[9px] badge badge-gold">ACTIVE</span>}
                  </div>
                )
              })}
            </div>

            {/* Actions */}
            <div className="mt-4 space-y-2">
              <button onClick={() => setShowAdvance(true)} className="btn-gold w-full py-2.5 text-center">→ Advance Stage</button>
              <button className="btn-outline w-full py-2 text-center text-[11px]">⚖ Read Weight</button>
            </div>
          </div>
        )}
      </div>

      {/* Create Job Modal */}
      {showCreate && <CreateJobModal onClose={() => setShowCreate(false)} onSubmit={(d: any) => createMutation.mutate(d)} loading={createMutation.isPending} />}

      {/* Advance Stage Modal */}
      {showAdvance && selectedJob && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 backdrop-blur-sm">
          <div className="erp-card w-[400px] p-6">
            <div className="flex justify-between items-center mb-5">
              <div className="serif text-[18px] text-[#e8d89a]">Advance Stage</div>
              <button onClick={() => setShowAdvance(false)} className="text-[#5a4a2a]">×</button>
            </div>
            <div className="mb-4">
              <label className="block text-[10px] text-[#5a4a2a] uppercase tracking-widest mb-1.5">Weight Out (g)</label>
              <input id="adv_weight" type="number" step="0.001" className="erp-input" placeholder="0.000" />
            </div>
            <div className="mb-5">
              <label className="block text-[10px] text-[#5a4a2a] uppercase tracking-widest mb-1.5">Notes</label>
              <textarea id="adv_notes" className="erp-input" rows={2} />
            </div>
            <div className="flex gap-3 justify-end">
              <button onClick={() => setShowAdvance(false)} className="btn-outline py-2 px-4">Cancel</button>
              <button onClick={() => {
                const w = parseFloat((document.getElementById('adv_weight') as HTMLInputElement).value) || 0
                const n = (document.getElementById('adv_notes') as HTMLTextAreaElement).value
                advanceMutation.mutate({ id: selectedJob.id, data: { weight_out: w, notes: n } })
              }} className="btn-gold py-2 px-4">Advance →</button>
            </div>
          </div>
        </div>
      )}
    </ERPLayout>
  )
}

function CreateJobModal({ onClose, onSubmit, loading }: any) {
  const [form, setForm] = useState({ design_name: '', customer_id: '', metal_type: '22K', target_weight: '', wastage_allowed: '2.50', order_qty: '1', priority: 'Normal', expected_delivery: '', notes: '' })
  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 backdrop-blur-sm">
      <div className="erp-card w-[540px] max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center p-5 border-b border-[#2a2318]">
          <div className="serif text-[18px] text-[#e8d89a]">Create New Job</div>
          <button onClick={onClose} className="text-[#5a4a2a] text-lg">×</button>
        </div>
        <div className="p-5 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-[10px] text-[#5a4a2a] uppercase tracking-widest mb-1.5">Design Name *</label>
              <input value={form.design_name} onChange={e => set('design_name', e.target.value)} className="erp-input" placeholder="e.g. Kundan Necklace" />
            </div>
            <div>
              <label className="block text-[10px] text-[#5a4a2a] uppercase tracking-widest mb-1.5">Customer ID *</label>
              <input type="number" value={form.customer_id} onChange={e => set('customer_id', e.target.value)} className="erp-input" placeholder="Customer ID" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-[10px] text-[#5a4a2a] uppercase tracking-widest mb-1.5">Metal Type *</label>
              <select value={form.metal_type} onChange={e => set('metal_type', e.target.value)} className="erp-input">
                {['24K','22K','18K','Silver'].map(m => <option key={m}>{m}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-[10px] text-[#5a4a2a] uppercase tracking-widest mb-1.5">Target Weight (g) *</label>
              <input type="number" step="0.001" value={form.target_weight} onChange={e => set('target_weight', e.target.value)} className="erp-input" placeholder="0.000" />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-[10px] text-[#5a4a2a] uppercase tracking-widest mb-1.5">Quantity</label>
              <input type="number" value={form.order_qty} onChange={e => set('order_qty', e.target.value)} className="erp-input" />
            </div>
            <div>
              <label className="block text-[10px] text-[#5a4a2a] uppercase tracking-widest mb-1.5">Wastage %</label>
              <input type="number" step="0.01" value={form.wastage_allowed} onChange={e => set('wastage_allowed', e.target.value)} className="erp-input" />
            </div>
            <div>
              <label className="block text-[10px] text-[#5a4a2a] uppercase tracking-widest mb-1.5">Priority</label>
              <select value={form.priority} onChange={e => set('priority', e.target.value)} className="erp-input">
                {['Normal','High','Urgent'].map(p => <option key={p}>{p}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label className="block text-[10px] text-[#5a4a2a] uppercase tracking-widest mb-1.5">Expected Delivery</label>
            <input type="date" value={form.expected_delivery} onChange={e => set('expected_delivery', e.target.value)} className="erp-input" />
          </div>
          <div>
            <label className="block text-[10px] text-[#5a4a2a] uppercase tracking-widest mb-1.5">Notes</label>
            <textarea value={form.notes} onChange={e => set('notes', e.target.value)} className="erp-input" rows={2} placeholder="Optional notes..." />
          </div>
        </div>
        <div className="flex gap-3 justify-end p-5 border-t border-[#2a2318]">
          <button onClick={onClose} className="btn-outline py-2 px-5">Cancel</button>
          <button onClick={() => onSubmit({ ...form, customer_id: parseInt(form.customer_id), target_weight: parseFloat(form.target_weight), order_qty: parseInt(form.order_qty), wastage_allowed: parseFloat(form.wastage_allowed) })}
            disabled={loading} className="btn-gold py-2 px-5">{loading ? 'Creating...' : 'Create Job'}</button>
        </div>
      </div>
    </div>
  )
}
