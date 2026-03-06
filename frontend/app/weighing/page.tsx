'use client'
import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import ERPLayout from '@/components/layout/ERPLayout'
import { scaleApi, jobsApi } from '@/lib/api'
import toast from 'react-hot-toast'

export default function WeighingPage() {
  const [expectedWeight, setExpectedWeight] = useState('10')
  const [jobId, setJobId] = useState('')
  const [lastReading, setLastReading] = useState<any>(null)
  const [reading, setReading] = useState(false)

  const { data: scaleStatus } = useQuery({
    queryKey: ['scaleStatus'],
    queryFn: () => scaleApi.status().then(r => r.data),
    refetchInterval: 5000
  })

  async function readWeight() {
    setReading(true)
    try {
      const res = await scaleApi.readWeight(parseFloat(expectedWeight) || 10)
      setLastReading(res.data)
      toast.success(`Weight: ${res.data.net_weight}g`)
    } catch (e) {
      toast.error('Scale read failed')
    } finally {
      setReading(false)
    }
  }

  async function logWeight() {
    if (!jobId || !lastReading) return
    await scaleApi.logWeight({ job_id: parseInt(jobId), gross_weight: lastReading.gross_weight, tare_weight: lastReading.tare_weight || 0, is_manual: false })
    toast.success('Weight logged to job')
  }

  return (
    <ERPLayout title="Weighing Scale" subtitle="REAL-TIME WEIGHT CAPTURE">
      <div className="grid grid-cols-2 gap-5">

        {/* Scale Panel */}
        <div className="erp-card p-6">
          <div className="text-[10px] text-[#5a4a2a] tracking-widest uppercase mb-5">Scale Control</div>

          {/* Status */}
          <div className={`flex items-center gap-2 p-3 rounded mb-5 border text-[11px] ${scaleStatus?.connected ? 'bg-[#1a2e1a] border-[#2a4a2a] text-[#4cc96f]' : 'bg-[#2e0a0a] border-[#4a0a0a] text-[#e04c4c]'}`}>
            <div className={`w-2 h-2 rounded-full ${scaleStatus?.connected ? 'bg-[#4cc96f]' : 'bg-[#e04c4c]'}`} style={{ boxShadow: scaleStatus?.connected ? '0 0 6px #4cc96f' : '0 0 6px #e04c4c' }} />
            {scaleStatus?.connected ? `Scale Connected — ${scaleStatus?.mode} Mode` : 'Scale Disconnected'}
          </div>

          {/* Reading Display */}
          <div className="text-center py-10 mb-5 bg-[#0e0d0b] border border-[#2a2318] rounded-lg">
            <div className="text-[10px] text-[#5a4a2a] tracking-widest uppercase mb-3">Net Weight</div>
            <div className="serif text-[64px] font-bold text-[#C9A84C] leading-none">
              {lastReading ? lastReading.net_weight.toFixed(3) : '---.-—-'}
            </div>
            <div className="text-[14px] text-[#5a4a2a] mt-2">grams</div>
            {lastReading && (
              <div className="mt-3 text-[10px] text-[#5a4a2a]">
                Gross: {lastReading.gross_weight}g · Tare: {lastReading.tare_weight || 0}g · 
                {lastReading.stable ? ' ✓ Stable' : ' ⚠ Unstable'} · {lastReading.source}
              </div>
            )}
          </div>

          {/* Controls */}
          <div className="space-y-3">
            <div>
              <label className="block text-[10px] text-[#5a4a2a] uppercase tracking-widest mb-1.5">Expected Weight (g)</label>
              <input type="number" step="0.001" value={expectedWeight} onChange={e => setExpectedWeight(e.target.value)} className="erp-input" />
            </div>
            <button onClick={readWeight} disabled={reading} className="btn-gold w-full py-3 text-[13px]">
              {reading ? '⌛ Reading...' : '⚖ Read Weight'}
            </button>
          </div>
        </div>

        {/* Log Weight to Job */}
        <div className="erp-card p-6">
          <div className="text-[10px] text-[#5a4a2a] tracking-widest uppercase mb-5">Log Weight to Job</div>

          <div className="mb-4">
            <label className="block text-[10px] text-[#5a4a2a] uppercase tracking-widest mb-1.5">Job ID</label>
            <input type="number" value={jobId} onChange={e => setJobId(e.target.value)} className="erp-input" placeholder="Enter Job ID" />
          </div>

          {lastReading && (
            <div className="mb-4 p-4 bg-[#0e0d0b] border border-[#2a2318] rounded">
              <div className="text-[10px] text-[#5a4a2a] uppercase tracking-widest mb-2">Last Reading</div>
              <div className="text-[#C9A84C] text-[18px] font-medium">{lastReading.net_weight.toFixed(3)}g</div>
              <div className="text-[10px] text-[#5a4a2a] mt-1">{lastReading.source} · {lastReading.stable ? 'Stable' : 'Unstable'}</div>
            </div>
          )}

          <button onClick={logWeight} disabled={!lastReading || !jobId} className="btn-gold w-full py-3 disabled:opacity-40">
            💾 Log Weight to Job
          </button>

          {/* Simulation info */}
          <div className="mt-6 p-4 bg-[#1a1a2e] border border-[#2a2a4a] rounded text-[11px] text-[#b57bee]">
            <div className="font-medium mb-1">🔬 Simulation Mode Active</div>
            <div className="text-[#5a4a5a]">Scale readings simulate ±5% variance from expected weight. Switch to REAL mode in .env: SIMULATION_MODE=false</div>
          </div>
        </div>
      </div>

      {/* Weight History would go here */}
    </ERPLayout>
  )
}
