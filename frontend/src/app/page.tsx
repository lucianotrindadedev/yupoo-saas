'use client'
const API = process.env.NEXT_PUBLIC_API_URL

export default function Home() {
  const login = () => { window.location.href = `${API}/auth/google` }

  return (
    <main style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Nav */}
      <nav style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1.25rem 2rem', borderBottom: '1px solid var(--border)' }}>
        <span style={{ fontWeight: 700, fontSize: 18, letterSpacing: '-0.02em' }}>
          yupoo<span style={{ color: 'var(--accent)' }}>dl</span>
        </span>
        <div style={{ display: 'flex', gap: 10 }}>
          <a href="/pricing" style={{ color: 'var(--muted)', fontSize: 14, padding: '8px 14px' }}>Preços</a>
          <button className="btn-primary" onClick={login}>Entrar com Google</button>
        </div>
      </nav>

      {/* Hero */}
      <section style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center', padding: '4rem 1.5rem' }}>
        <div style={{ background: 'var(--bg3)', border: '1px solid var(--border)', borderRadius: 999, fontSize: 12, padding: '4px 14px', color: 'var(--accent)', marginBottom: '1.5rem', display: 'inline-flex', gap: 6, alignItems: 'center' }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)', display: 'inline-block' }} />
          Roda no seu Google Drive — sem armazenar nada
        </div>
        <h1 style={{ fontSize: 'clamp(2rem, 6vw, 4rem)', fontWeight: 800, lineHeight: 1.1, letterSpacing: '-0.03em', maxWidth: 700, marginBottom: '1.25rem' }}>
          Baixe qualquer álbum da Yupoo em segundos
        </h1>
        <p style={{ fontSize: 17, color: 'var(--muted)', maxWidth: 480, marginBottom: '2.5rem', lineHeight: 1.7 }}>
          Cole o link do álbum, conecte seu Google Drive e pronto — todas as imagens organizadas em pastas automaticamente.
        </p>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', justifyContent: 'center' }}>
          <button className="btn-primary" onClick={login} style={{ fontSize: 16, padding: '14px 32px' }}>
            Começar grátis — 10 créditos
          </button>
          <a href="/pricing" style={{ display: 'flex', alignItems: 'center' }}>
            <button className="btn-ghost" style={{ fontSize: 16, padding: '14px 28px' }}>Ver preços</button>
          </a>
        </div>
        <p style={{ marginTop: '1rem', fontSize: 13, color: 'var(--muted)' }}>Sem cartão de crédito para começar</p>
      </section>

      {/* Features */}
      <section style={{ padding: '3rem 2rem 5rem', maxWidth: 900, margin: '0 auto', width: '100%' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16 }}>
          {[
            { icon: '☁️', title: 'Direto para o Drive', desc: 'Imagens enviadas diretamente para sua conta Google. Zero armazenamento no servidor.' },
            { icon: '📁', title: 'Pastas automáticas', desc: 'Cada álbum vira uma pasta separada no seu Drive com o nome original.' },
            { icon: '⚡', title: 'Jobs em paralelo', desc: 'Submeta vários álbuns de uma vez. Processamos em fila enquanto você faz outra coisa.' },
            { icon: '💳', title: 'Pague pelo uso', desc: '1 crédito = 1 imagem. Sem mensalidade. Compre o pacote que precisar.' },
          ].map(f => (
            <div key={f.title} className="card">
              <div style={{ fontSize: 24, marginBottom: 10 }}>{f.icon}</div>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>{f.title}</div>
              <div style={{ fontSize: 14, color: 'var(--muted)', lineHeight: 1.6 }}>{f.desc}</div>
            </div>
          ))}
        </div>
      </section>

      <footer style={{ borderTop: '1px solid var(--border)', padding: '1.5rem 2rem', textAlign: 'center', color: 'var(--muted)', fontSize: 13 }}>
        © {new Date().getFullYear()} YupooDL — Feito no Brasil
      </footer>
    </main>
  )
}
