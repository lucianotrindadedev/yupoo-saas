'use client'
import { useState } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL

const PACKAGES = [
  { id: 'starter',  name: 'Starter',   credits: 200,   price: 'R$ 19',  per: 'R$0,095/img', highlight: false },
  { id: 'pro',      name: 'Pro',        credits: 1000,  price: 'R$ 59',  per: 'R$0,059/img', highlight: true  },
  { id: 'business', name: 'Business',   credits: 5000,  price: 'R$ 149', per: 'R$0,030/img', highlight: false },
  { id: 'unlimited',name: 'Unlimited',  credits: 999999,price: 'R$ 349', per: '30 dias ilimitado', highlight: false },
]

export default function Pricing() {
  const [loading, setLoading] = useState<string | null>(null)

  const checkout = async (pkg_id: string) => {
    const token = localStorage.getItem('token')
    if (!token) { window.location.href = `${API}/auth/google`; return }
    setLoading(pkg_id)
    const r = await fetch(`${API}/credits/checkout/${pkg_id}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` }
    })
    const data = await r.json()
    if (data.checkout_url) window.location.href = data.checkout_url
    else { alert('Erro ao criar checkout'); setLoading(null) }
  }

  return (
    <div style={{ minHeight: '100vh', padding: '3rem 1.5rem' }}>
      <div style={{ maxWidth: 860, margin: '0 auto' }}>
        <div style={{ textAlign: 'center', marginBottom: '3rem' }}>
          <h1 style={{ fontSize: 'clamp(1.8rem, 4vw, 3rem)', fontWeight: 800, letterSpacing: '-0.03em', marginBottom: 12 }}>Preços simples</h1>
          <p style={{ color: 'var(--muted)', fontSize: 16 }}>1 crédito = 1 imagem baixada. Sem assinatura, sem surpresas.</p>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 14 }}>
          {PACKAGES.map(pkg => (
            <div key={pkg.id} className="card" style={pkg.highlight ? { border: '2px solid var(--accent)' } : {}}>
              {pkg.highlight && (
                <div style={{ background: 'var(--accent)', color: '#000', fontSize: 11, fontWeight: 700, padding: '3px 10px', borderRadius: 999, display: 'inline-block', marginBottom: 10 }}>
                  MAIS VENDIDO
                </div>
              )}
              <div style={{ fontWeight: 700, fontSize: 17, marginBottom: 4 }}>{pkg.name}</div>
              <div style={{ fontSize: 28, fontWeight: 800, letterSpacing: '-0.02em', marginBottom: 2 }}>{pkg.price}</div>
              <div style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 16 }}>
                {pkg.credits > 100000 ? 'Ilimitado' : pkg.credits.toLocaleString('pt-BR') + ' créditos'} · {pkg.per}
              </div>
              <div style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 20, display: 'flex', flexDirection: 'column', gap: 6 }}>
                {['Download p/ Drive', 'Download p/ PC', 'Histórico completo', pkg.highlight || pkg.id === 'business' || pkg.id === 'unlimited' ? 'Fila prioritária' : null].filter(Boolean).map(f => (
                  <div key={f as string} style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                    <span style={{ color: 'var(--success)', fontSize: 12 }}>✓</span> {f}
                  </div>
                ))}
              </div>
              <button
                className={pkg.highlight ? 'btn-primary' : 'btn-ghost'}
                style={{ width: '100%', padding: '10px 0' }}
                disabled={loading === pkg.id}
                onClick={() => checkout(pkg.id)}>
                {loading === pkg.id ? 'Aguarde...' : 'Comprar'}
              </button>
            </div>
          ))}
        </div>

        <p style={{ textAlign: 'center', color: 'var(--muted)', fontSize: 13, marginTop: '2rem' }}>
          Pagamento seguro via Stripe · Créditos não expiram · Suporte por email
        </p>
      </div>
    </div>
  )
}
