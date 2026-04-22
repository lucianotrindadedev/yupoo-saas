// auth_bridge.js
// Roda em yupoodownloader.online para sincronizar o login com a extensão

function syncAuth() {
  const token = localStorage.getItem('token');
  const driveToken = localStorage.getItem('drive_token');

  if (token) {
    chrome.storage.local.set({ 
      'token': token, 
      'drive_token': driveToken || '',
      'last_sync': Date.now()
    }, () => {
      console.log('YupooDL: Login sincronizado com a extensão!');
    });
  }
}

// Sincroniza ao carregar e quando o localStorage mudar
syncAuth();
window.addEventListener('storage', syncAuth);
