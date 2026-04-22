const API_URL = 'https://yupoodownloader.online/api'  // ← altere para seu domínio
const SITE = 'https://yupoodownloader.online'

const $ = id => document.getElementById(id)

function setStatus(msg, type = 'info') {
  const el = $('statusMsg')
  el.textContent = msg
  el.className = `status ${type}`
}

function setProgress(pct) {
  const bar = $('progressBar')
  bar.style.display = 'block'
  $('progressFill').style.width = pct + '%'
}

async function getToken() {
  return new Promise(res => chrome.storage.local.get(['token', 'drive_token'], res))
}

async function saveTokens(token, drive_token) {
  return new Promise(res => chrome.storage.local.set({ token, drive_token }, res))
}

async function fetchUser(token) {
  const r = await fetch(`${API_URL}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
  if (!r.ok) return null
  return r.json()
}

async function startJob(token, driveToken, url) {
  const r = await fetch(`${API_URL}/jobs/`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ yupoo_url: url, destination: 'drive', drive_token: driveToken })
  })
  return r.json()
}

async function pollJob(token, jobId) {
  return new Promise((resolve) => {
    const interval = setInterval(async () => {
      try {
        const r = await fetch(`${API_URL}/jobs/${jobId}`, { headers: { Authorization: `Bearer ${token}` } })
        const job = await r.json()
        const pct = job.total_images > 0 ? Math.round(job.processed / job.total_images * 100) : 10
        setProgress(pct)
        setStatus(`${job.processed}/${job.total_images} imagens enviadas...`, 'info')
        if (['completed', 'failed', 'cancelled', 'paused'].includes(job.status)) {
          clearInterval(interval)
          resolve(job)
        }
      } catch { clearInterval(interval); resolve(null) }
    }, 3000)
  })
}

async function init() {
  // Links de rodapé
  $('dashLink').href = `${SITE}/dashboard`
  $('buyLink').href = `${SITE}/pricing`
  $('pricingLink').href = `${SITE}/pricing`

  // Verifica se está em página Yupoo
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
  const url = tab?.url || ''
  const isYupoo = /yupoo\.com/.test(url) && /\/albums\//.test(url)

  if (!isYupoo) {
    $('main').style.display = 'none'
    $('not-yupoo').style.display = 'block'
    return
  }

  $('currentUrl').textContent = url.replace(/https?:\/\//, '').substring(0, 45) + '...'

  // Verifica autenticação
  const { token, drive_token } = await getToken()

  // Checa parâmetros de retorno do OAuth (quando abre via redirect)
  const params = new URLSearchParams(window.location.search)
  const newToken = params.get('token')
  const newDrive = params.get('drive_token')
  if (newToken) { await saveTokens(newToken, newDrive || ''); location.reload(); return }

  if (!token) {
    $('main').style.display = 'none'
    $('login-section').style.display = 'block'
    $('loginBtn').onclick = () => { chrome.tabs.create({ url: `${API_URL}/auth/google` }) }
    return
  }

  // Carrega dados do usuário
  const user = await fetchUser(token)
  if (!user) {
    await saveTokens('', '')
    $('main').style.display = 'none'
    $('login-section').style.display = 'block'
    $('loginBtn').onclick = () => { chrome.tabs.create({ url: `${API_URL}/auth/google` }) }
    return
  }

  $('creditsVal').textContent = user.credits.toLocaleString('pt-BR')

  if (user.credits < 1) {
    setStatus('Créditos insuficientes. Compre mais para continuar.', 'err')
    return
  }

  // Botão de download
  const btn = $('downloadBtn')
  btn.disabled = false
  btn.onclick = async () => {
    btn.disabled = true
    setStatus('Criando job de download...', 'info')
    setProgress(5)

    try {
      const job = await startJob(token, drive_token || '', url)
      if (job.detail) { setStatus(job.detail, 'err'); btn.disabled = false; return }

      setStatus('Download iniciado! Processando imagens...', 'info')
      const result = await pollJob(token, job.job_id)

      if (result?.status === 'completed') {
        setProgress(100)
        setStatus(`Concluído! ${result.processed} imagens enviadas para o Drive.`, 'ok')
        // Atualiza créditos
        const updated = await fetchUser(token)
        if (updated) $('creditsVal').textContent = updated.credits.toLocaleString('pt-BR')
      } else {
        setStatus(`Status final: ${result?.status || 'desconhecido'}`, 'err')
      }
    } catch (e) {
      setStatus('Erro de conexão com o servidor.', 'err')
    }
    btn.disabled = false
  }
}

init()
