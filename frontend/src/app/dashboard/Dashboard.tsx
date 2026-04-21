'use client'
import { useEffect, useState, useCallback } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'

const API = process.env.NEXT_PUBLIC_API_URL

interface User { id: string; email: string; name: string; avatar: string; credits: number }
interface Job {
  id: string; yupoo_url: string; status: string; destination: string;
  total_images: number; processed: number; failed: number;
  credits_used: number; created_at: number; log: string;
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`badge badge-${status}`}>
      {status === 'running' && <span className="pulse" style={{ width: 6, height: 6, borderRadius: '50%', background: '#60aaff', display: 'inline-block' }} />}
      {status}
    </span>
  )
}

function JobCard({ job, onRefresh }: { job: Job; onRefresh: () => void }) {
  const pct = job.total_images > 0 ? Math.round((job.processed / job.total_images) * 100) : 0
  const url = new URL(job.yupoo_url)

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
        <div>
          <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 2 }}>{url.hostname}{url.pathname}</div>
          <div style={{ fontSize: 12, color: 'var(--muted)' }}>
            {new Date(job.created_at * 1000).toLocaleString('pt-BR')} · {job.destination === 'drive' ? 'Google Drive' : 'Download'}
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
            <span>{job.processed}/{job.total_images} imagens</span>
            {job.failed > 0 && <span style={{ color: 'var(--danger)' }}>{job.failed} falhas</span>}
            <span>{job.credits_used} créditos</span>
            <span style={{ marginLeft: 'auto' }}>{pct}%</span>
          </div>
        </>
      )}

      {job.status === 'running' && (
        <button className="btn-ghost" onClick={onRefresh} style={{ marginTop: 10, padding: '6px 14px', fontSize: 12 }}>
          Atualizar
        </button>
      )}
    </div>
  )
}

export default function DashboardInner() {
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
      if (!r.ok) { setError(data.detail || 'Erro ao criar job'); return }
      setUrl(''); setTab('history'); fetchJobs(); fetchUser()
    } catch { setError('Erro de conexão') }
    finally { setSubmitting(false) }
  }

  if (!user) return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ color: 'var(--muted)', fontSize: 14 }}>Carregando...</div>
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
            <div style={{ fontSize: 13, color: 'var(--muted)' }}>créditos</div>
            <div style={{ fontWeight: 700, fontSize: 18, color: 'var(--accent)', lineHeight: 1 }}>{user.credits.toLocaleString('pt-BR')}</div>
          </div>
          <a href="/pricing">
            <button className="btn-ghost" style={{ padding: '7px 14px', fontSize: 13 }}>Comprar</button>
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
          {(['new', 'history'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)}
              style={{ flex: 1, padding: '8px 0', borderRadius: 8, fontSize: 14, fontWeight: 500,
                background: tab === t ? 'var(--bg2)' : 'transparent',
                color: tab === t ? 'var(--text)' : 'var(--muted)',
                border: tab === t ? '1px solid var(--border)' : 'none' }}>
              {t === 'new' ? 'Novo download' : `Histórico (${jobs.length})`}
            </button>
          ))}
        </div>

        {tab === 'new' && (
          <div className="card">
            <h2 style={{ fontWeight: 700, fontSize: 18, marginBottom: 4 }}>Novo download</h2>
            <p style={{ fontSize: 14, color: 'var(--muted)', marginBottom: '1.25rem' }}>
              Cole o link de qualquer álbum da Yupoo. As imagens serão enviadas para o seu Google Drive.
            </p>
            <label style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 6, display: 'block' }}>Link do álbum</label>
            <input value={url} onChange={e => setUrl(e.target.value)}
              placeholder="https://storenome.x.yupoo.com/albums/12345"
              onKeyDown={e => e.key === 'Enter' && submit()} />
            {error && <p style={{ color: 'var(--danger)', fontSize: 13, marginTop: 8 }}>{error}</p>}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '1rem' }}>
              <span style={{ fontSize: 13, color: 'var(--muted)' }}>
                {user.credits} crédito{user.credits !== 1 ? 's' : ''} disponível{user.credits !== 1 ? 'is' : ''}
              </span>
              <button className="btn-primary" onClick={submit} disabled={submitting || !url.trim() || user.credits < 1}>
                {submitting ? 'Enviando...' : 'Iniciar download'}
              </button>
            </div>
            {user.credits < 1 && (
              <div style={{ marginTop: 12, padding: '10px 14px', background: '#1a0000', border: '1px solid #3a0000', borderRadius: 8, fontSize: 13, color: '#ff8080' }}>
                Você não tem créditos. <a href="/pricing" style={{ color: 'var(--accent)', textDecoration: 'underline' }}>Comprar créditos →</a>
              </div>
            )}
          </div>
        )}

        {tab === 'history' && (
          <div>
            {jobs.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '4rem 0', color: 'var(--muted)' }}>
                <div style={{ fontSize: 32, marginBottom: 12 }}>📂</div>
                <div>Nenhum download ainda.</div>
                <button className="btn-ghost" onClick={() => setTab('new')} style={{ marginTop: 16, padding: '8px 20px' }}>Criar primeiro download</button>
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
