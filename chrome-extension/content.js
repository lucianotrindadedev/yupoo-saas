// Injeta botão flutuante nas páginas de álbum da Yupoo
;(function () {
  if (!location.href.includes('/albums/')) return
  if (document.getElementById('yupooDLBtn')) return

  const btn = document.createElement('button')
  btn.id = 'yupooDLBtn'
  btn.textContent = '⬇ Baixar álbum'
  Object.assign(btn.style, {
    position: 'fixed', bottom: '24px', right: '24px', zIndex: '99999',
    background: '#e8ff47', color: '#000', border: 'none',
    padding: '12px 20px', borderRadius: '10px',
    fontWeight: '700', fontSize: '14px', cursor: 'pointer',
    fontFamily: '-apple-system, sans-serif',
    boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
  })

  btn.addEventListener('click', () => {
    // Abre o popup da extensão
    btn.textContent = '⬇ Abrindo...'
    setTimeout(() => { btn.textContent = '⬇ Baixar álbum' }, 1500)
  })

  document.body.appendChild(btn)
})()
