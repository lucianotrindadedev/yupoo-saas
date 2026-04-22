const API_URL = 'https://yupoodownloader.online/api'
const SITE = 'https://yupoodownloader.online'

const $ = id => document.getElementById(id)

function setStatus(msg, type = 'info') {
  const el = $('statusMsg')
  if (el) {
    el.textContent = msg
    el.className = `status ${type}`
  }
}

function setProgress(pct) {
  const bar = $('progressBar')
  if (bar) {
    bar.style.display = 'block'
    const fill = $('progressFill')
    if (fill) fill.style.width = pct + '%'
  }
}

async function getToken() {
  return new Promise(res => {
    chrome.storage.local.get(['token', 'drive_token'], (data) => {
      res(data || { token: '', drive_token: '' });
    });
  });
}

async function saveTokens(token, drive_token) {
  return new Promise(res => chrome.storage.local.set({ token, drive_token }, res))
}

async function fetchUser(token) {
  try {
    const r = await fetch(`${API_URL}/auth/me`, { 
      headers: { Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(5000)
    })
    if (!r.ok) return null
    return r.json()
  } catch (e) {
    console.error('Erro ao buscar usuário:', e);
    return null;
  }
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
  try {
    // Configura links básicos
    if ($('dashLink')) $('dashLink').href = `${SITE}/dashboard`
    if ($('buyLink')) $('buyLink').href = `${SITE}/pricing`
    if ($('pricingLink')) $('pricingLink').href = `${SITE}/pricing`

    // 1. Pega a URL da aba ativa
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const tab = tabs[0];
    const url = tab?.url || '';
    
    const isYupoo = /yupoo\.com/.test(url);
    const isSingleAlbum = /\/albums\/\d+/.test(url);

    if (!isYupoo) {
      $('main').style.display = 'none';
      $('not-yupoo').style.display = 'block';
      return;
    }

    // 2. Atualiza UI da URL
    const btn = $('downloadBtn');
    if (isSingleAlbum) {
      btn.textContent = 'Baixar Álbum para o Drive';
      $('currentUrl').textContent = url.replace(/https?:\/\//, '').substring(0, 40) + '...';
    } else {
      btn.textContent = 'Baixar Loja Inteira para o Drive';
      const domain = url.split('/')[2] || 'Yupoo';
      $('currentUrl').textContent = 'Loja: ' + domain;
    }

    // 3. Verifica Tokens
    const { token, drive_token } = await getToken();
    
    if (!token) {
      $('main').style.display = 'none';
      $('login-section').style.display = 'block';
      $('loginBtn').onclick = () => { chrome.tabs.create({ url: `${SITE}/dashboard` }) };
      return;
    }

    // 4. Busca Usuário e Créditos
    const user = await fetchUser(token);
    if (!user) {
      // Se o token falhar, pode ser expirado
      $('creditsVal').textContent = 'Erro';
      setStatus('Erro ao validar login. Tente abrir o site e logar novamente.', 'err');
      return;
    }

    $('creditsVal').textContent = user.credits.toLocaleString('pt-BR');

    if (user.credits < 1) {
      setStatus('Créditos insuficientes.', 'err');
      btn.disabled = true;
      btn.style.opacity = '0.5';
      return;
    }

    // Habilita o botão se tiver créditos
    btn.disabled = false;
    btn.style.opacity = '1';

    // 5. Lógica do Botão
    btn.onclick = async () => {
      btn.disabled = true;
      btn.textContent = 'Iniciando...';
      setStatus('Criando pedido de download...', 'info');
      setProgress(5);

      try {
        const job = await startJob(token, drive_token || '', url);
        if (job.detail) { setStatus(job.detail, 'err'); btn.disabled = false; return; }

        setStatus('Processando imagens...', 'info');
        const result = await pollJob(token, job.job_id);

        if (result?.status === 'completed') {
          setProgress(100);
          setStatus(`Concluído! ${result.processed} imagens enviadas.`, 'ok');
          // Atualiza créditos após finalizar
          const updated = await fetchUser(token);
          if (updated) $('creditsVal').textContent = updated.credits.toLocaleString('pt-BR');
        } else {
          setStatus(`Finalizado com status: ${result?.status || 'erro'}`, 'err');
        }
      } catch (e) {
        setStatus('Erro de conexão com o servidor.', 'err');
      }
      btn.disabled = false;
      btn.textContent = isSingleAlbum ? 'Baixar Álbum para o Drive' : 'Baixar Loja Inteira para o Drive';
    };

  } catch (err) {
    console.error('Erro crítico no popup:', err);
    setStatus('Erro interno na extensão.', 'err');
  }
}

// Inicia tudo
document.addEventListener('DOMContentLoaded', init);
