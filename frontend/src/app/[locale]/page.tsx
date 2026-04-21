'use client'
import {useTranslations} from 'next-intl';
import {Link, useRouter, usePathname} from '../../navigation';
import {useParams} from 'next/navigation';

const API = process.env.NEXT_PUBLIC_API_URL

export default function Home() {
  const t = useTranslations('Index');
  const router = useRouter();
  const pathname = usePathname();
  const params = useParams();
  const locale = params.locale as string;

  const login = () => { window.location.href = `${API}/auth/google` }

  const handleLocaleChange = (newLocale: string) => {
    router.replace(pathname, {locale: newLocale});
  };

  return (
    <main style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Nav */}
      <nav style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1.25rem 2rem', borderBottom: '1px solid var(--border)' }}>
        <span style={{ fontWeight: 700, fontSize: 18, letterSpacing: '-0.02em' }}>
          yupoo<span style={{ color: 'var(--accent)' }}>dl</span>
        </span>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <select 
            value={locale} 
            onChange={(e) => handleLocaleChange(e.target.value)}
            style={{ background: 'transparent', border: '1px solid var(--border)', borderRadius: 6, color: 'var(--muted)', fontSize: 12, padding: '4px 8px' }}
          >
            <option value="en">🇺🇸 EN</option>
            <option value="pt">🇧🇷 PT</option>
            <option value="es">🇪🇸 ES</option>
            <option value="zh">🇨🇳 ZH</option>
          </select>
          <Link href="/pricing" style={{ color: 'var(--muted)', fontSize: 14, padding: '8px 14px' }}>
            {t('pricing')}
          </Link>
          <button className="btn-primary" onClick={login}>{t('signIn')}</button>
        </div>
      </nav>

      {/* Hero */}
      <section style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center', padding: '4rem 1.5rem' }}>
        <div style={{ background: 'var(--bg3)', border: '1px solid var(--border)', borderRadius: 999, fontSize: 12, padding: '4px 14px', color: 'var(--accent)', marginBottom: '1.5rem', display: 'inline-flex', gap: 6, alignItems: 'center' }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)', display: 'inline-block' }} />
          {t('badge')}
        </div>
        <h1 style={{ fontSize: 'clamp(2rem, 6vw, 4rem)', fontWeight: 800, lineHeight: 1.1, letterSpacing: '-0.03em', maxWidth: 700, marginBottom: '1.25rem' }}>
          {t('title')}
        </h1>
        <p style={{ fontSize: 17, color: 'var(--muted)', maxWidth: 480, marginBottom: '2.5rem', lineHeight: 1.7 }}>
          {t('subtitle')}
        </p>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', justifyContent: 'center' }}>
          <button className="btn-primary" onClick={login} style={{ fontSize: 16, padding: '14px 32px' }}>
            {t('ctaStart')}
          </button>
          <Link href="/pricing" style={{ display: 'flex', alignItems: 'center' }}>
            <button className="btn-ghost" style={{ fontSize: 16, padding: '14px 28px' }}>{t('ctaPricing')}</button>
          </Link>
        </div>
        <p style={{ marginTop: '1rem', fontSize: 13, color: 'var(--muted)' }}>{t('noCard')}</p>
      </section>

      {/* Features */}
      <section style={{ padding: '3rem 2rem 5rem', maxWidth: 900, margin: '0 auto', width: '100%' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16 }}>
          {[
            { icon: '☁️', title: t('feature1Title'), desc: t('feature1Desc') },
            { icon: '📁', title: t('feature2Title'), desc: t('feature2Desc') },
            { icon: '⚡', title: t('feature3Title'), desc: t('feature3Desc') },
            { icon: '💳', title: t('feature4Title'), desc: t('feature4Desc') },
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
        {t('footer', {year: new Date().getFullYear()})}
      </footer>
    </main>
  )
}
