'use client'
import { useEffect, useState, useCallback } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'

const API = process.env.NEXT_PUBLIC_API_URL

interface User { id: string; email: string; name: string; avatar: string; credits: number }
interface Job {
  id: string; yupoo_url: string; status: string; destination: string;
  total_images: number; processed: number; failed: number;
  credits_used: number; created_at: number; log: string;
  job_type?: string;
}

function StatusBadge({ status }: { status: string }) {
  const t = useTranslations('Dashboard.status')
  return (
    <span className={`badge badge-${status}`}>
      {status === 'running' && <span className="pulse" style={{ width: 6, height: 6, borderRadius: '50%', background: '#60aaff', display: 'inline-block' }} />}
      {t(status as any)}
    </span>
  )
}

function JobCard({ job, onRefresh }: { job: Job; onRefresh: () => void }) {
  const t = useTranslations('Dashboard')
  const pct = job.total_images > 0 ? Math.round((job.processed / job.total_images) * 100) : 0
  const url = new URL(job.yupoo_url)

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
            <span style={{ fontWeight: 600, fontSize: 14 }}>{url.hostname}{url.pathname}</span>
            {job.job_type === 'store' && <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 4, background: '#2d1f4e', color: '#b39dff', fontWeight: 600 }}>STORE</span>}
          </div>
          <div style={{ fontSize: 12, color: 'var(--muted)' }}>
            {new Date(job.created_at * 1000).toLocaleString()} · {job.destination === 'drive' ? 'Google Drive' : 'Download'}
          </div>
        </div>
        <StatusBadge status={job.status} />
      </div>

      {job.total_images > 0 && (
        <>
          <div style={{ background: 'var(--bg3)', borderRadius: 4, height: 4, marginBottom: 8, overflow: 'hidden' }}>
            <div style={{ height: 4, width: `${pct}%`, background: job.status === 'completed' ? 'var(--success)' : 'var(--accent)', borderRadius: 4, transition: 'width .4s' }} />
          </div>
          <div style={{ display: 'flex', gap: 16, fontSize: 13, color: 'var(--muted)' }}>
            <span>{t('images_count', {processed: job.processed, total: job.total_images})}</span>
            {job.failed > 0 && <span style={{ color: 'var(--danger)' }}>{job.failed} falhas</span>}
            <span>{t('credits_count', {amount: job.credits_used})}</span>
            <span style={{ marginLeft: 'auto' }}>{pct}%</span>
          </div>
        </>
      )}

      {job.status === 'running' && (
        <button className="btn-ghost" onClick={onRefresh} style={{ marginTop: 10, padding: '6px 14px', fontSize: 12 }}>
          {t('refresh')}
        </button>
      )}
    </div>
  )
}

export default function DashboardInner() {
  const t = useTranslations('Dashboard')
  const params = useSearchParams()
  const router = useRouter()
  const [user, setUser] = useState<User | null>(null)
  const [jobs, setJobs] = useState<Job[]>([])
  const [url, setUrl] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [tab, setTab] = useState<'new' | 'history'>('new')

  const token = typeof window !== 'undefined' ? localStorage.getItem('token') || '' : ''
  const driveToken = typeof window !== 'undefined' ? localStorage.getItem('drive_token') || '' : ''

  useEffect(() => {
    const t = params.get('token')
    const dt = params.get('drive_token')
    if (t) { localStorage.setItem('token', t); localStorage.setItem('drive_token', dt || ''); router.replace('/dashboard') }
  }, [params, router])

  const fetchUser = useCallback(async () => {
    const t = localStorage.getItem('token')
    if (!t) { router.push('/'); return }
    const r = await fetch(`${API}/auth/me`, { headers: { Authorization: `Bearer ${t}` } })
    if (!r.ok) { localStorage.clear(); router.push('/'); return }
    setUser(await r.json())
  }, [router])

  const fetchJobs = useCallback(async () => {
    const t = localStorage.getItem('token')
    if (!t) return
    const r = await fetch(`${API}/jobs/`, { headers: { Authorization: `Bearer ${t}` } })
    if (r.ok) setJobs(await r.json())
  }, [])

  useEffect(() => { fetchUser(); fetchJobs() }, [fetchUser, fetchJobs])

  // Auto-refresh se tem job rodando
  useEffect(() => {
    const running = jobs.some(j => j.status === 'running' || j.status === 'pending')
    if (!running) return
    const id = setInterval(fetchJobs, 4000)
    return () => clearInterval(id)
  }, [jobs, fetchJobs])

  const submit = async () => {
    if (!url.trim()) return
    setError(''); setSubmitting(true)
    const t = localStorage.getItem('token')
    const dt = localStorage.getItem('drive_token')
    try {
      const r = await fetch(`${API}/jobs/`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${t}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ yupoo_url: url.trim(), destination: 'drive', drive_token: dt || '' }),
      })
      const data = await r.json()
      if (!r.ok) { setError(data.detail || 'Error creating job'); return }
      setUrl(''); setTab('history'); fetchJobs(); fetchUser()
    } catch { setError('Connection error') }
    finally { setSubmitting(false) }
  }

  if (!user) return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ color: 'var(--muted)', fontSize: 14 }}>{t('loading')}</div>
    </div>
  )

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Topbar */}
      <nav style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1rem 1.5rem', borderBottom: '1px solid var(--border)' }}>
        <span style={{ fontWeight: 700, fontSize: 17, letterSpacing: '-0.02em' }}>
          yupoo<span style={{ color: 'var(--accent)' }}>dl</span>
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 13, color: 'var(--muted)' }}>{t('credits_plural')}</div>
            <div style={{ fontWeight: 700, fontSize: 18, color: 'var(--accent)', lineHeight: 1 }}>{user.credits.toLocaleString()}</div>
          </div>
          <a href="/pricing">
            <button className="btn-ghost" style={{ padding: '7px 14px', fontSize: 13 }}>{t('buy')}</button>
          </a>
          <div style={{ width: 34, height: 34, borderRadius: '50%', background: 'var(--bg3)', border: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}
            title={user.email} onClick={() => { localStorage.clear(); window.location.href = '/' }}>
            {user.name?.[0]?.toUpperCase() || '?'}
          </div>
        </div>
      </nav>

      <main style={{ flex: 1, maxWidth: 720, margin: '0 auto', width: '100%', padding: '2rem 1.5rem' }}>
        {/* Tabs */}
        <div style={{ display: 'flex', gap: 4, marginBottom: '1.5rem', background: 'var(--bg3)', borderRadius: 10, padding: 4 }}>
          {(['new', 'history'] as const).map(tabKey => (
            <button key={tabKey} onClick={() => setTab(tabKey)}
              style={{ flex: 1, padding: '8px 0', borderRadius: 8, fontSize: 14, fontWeight: 500,
                background: tab === tabKey ? 'var(--bg2)' : 'transparent',
                color: tab === tabKey ? 'var(--text)' : 'var(--muted)',
                border: tab === tabKey ? '1px solid var(--border)' : 'none' }}>
              {tabKey === 'new' ? t('newJob') : t('history', {amount: jobs.length})}
            </button>
          ))}
        </div>

        {tab === 'new' && (
          <div className="card">
            <h2 style={{ fontWeight: 700, fontSize: 18, marginBottom: 4 }}>{t('newJob')}</h2>
            <p style={{ fontSize: 14, color: 'var(--muted)', marginBottom: '1.25rem' }}>
              {t('subtitle')}
            </p>
            <label style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 6, display: 'block' }}>{t('urlLabel')}</label>
            <input value={url} onChange={e => setUrl(e.target.value)}
              placeholder="https://store.x.yupoo.com/albums or /albums/12345"
              onKeyDown={e => e.key === 'Enter' && submit()} />
            {error && <p style={{ color: 'var(--danger)', fontSize: 13, marginTop: 8 }}>{error}</p>}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '1rem' }}>
              <span style={{ fontSize: 13, color: 'var(--muted)' }}>
                {user.credits} {user.credits === 1 ? t('credits') : t('credits_plural')} {user.credits === 1 ? t('available') : t('available_plural')}
              </span>
              <button className="btn-primary" onClick={submit} disabled={submitting || !url.trim() || user.credits < 1}>
                {submitting ? t('submitting') : t('start')}
              </button>
            </div>
            {user.credits < 1 && (
              <div style={{ marginTop: 12, padding: '10px 14px', background: '#1a0000', border: '1px solid #3a0000', borderRadius: 8, fontSize: 13, color: '#ff8080' }}>
                {t('noCredits')} <a href="/pricing" style={{ color: 'var(--accent)', textDecoration: 'underline' }}>{t('buyCreditsLink')}</a>
              </div>
            )}
          </div>
        )}

        {tab === 'history' && (
          <div>
            {jobs.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '4rem 0', color: 'var(--muted)' }}>
                <div style={{ fontSize: 32, marginBottom: 12 }}>📂</div>
                <div>{t('noJobs')}</div>
                <button className="btn-ghost" onClick={() => setTab('new')} style={{ marginTop: 16, padding: '8px 20px' }}>{t('createFirst')}</button>
              </div>
            ) : (
              jobs.map(j => <JobCard key={j.id} job={j} onRefresh={fetchJobs} />)
            )}
          </div>
        )}
      </main>
    </div>
  )
}
