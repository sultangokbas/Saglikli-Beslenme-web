// ─── AUTH FORMLARI ──────────────────────────────────────────────────────────

let isLoginMode = true;

function toggleAuth() {
  isLoginMode = !isLoginMode;

  const loginForm    = document.getElementById('login-form');
  const registerForm = document.getElementById('register-form');
  const subtitle     = document.getElementById('auth-subtitle');

  if (isLoginMode) {
    loginForm.style.display    = 'flex';
    registerForm.style.display = 'none';
    subtitle.textContent       = 'Yolculuğuna devam et ';
  } else {
    loginForm.style.display    = 'none';
    registerForm.style.display = 'flex';
    subtitle.textContent       = 'Yolculuğuna başlamaya hazır mısın?';
  }
}

// Bildirim göster
function showNotification(message, isError = false) {
  // Varsa eski bildirimi kaldır
  const existing = document.getElementById('auth-notif');
  if (existing) existing.remove();

  const notif = document.createElement('div');
  notif.id = 'auth-notif';
  notif.textContent = message;
  notif.style.cssText = `
    position: fixed;
    top: 24px;
    left: 50%;
    transform: translateX(-50%);
    background: ${isError ? 'rgba(231,76,60,0.9)' : 'rgba(46,204,113,0.9)'};
    color: white;
    padding: 14px 28px;
    border-radius: 40px;
    font-size: 14px;
    font-weight: 600;
    backdrop-filter: blur(10px);
    z-index: 9999;
    animation: slideDown 0.3s ease;
    box-shadow: 0 8px 24px rgba(0,0,0,0.3);
  `;

  // Animasyon ekle
  if (!document.getElementById('notif-style')) {
    const style = document.createElement('style');
    style.id = 'notif-style';
    style.textContent = `
      @keyframes slideDown {
        from { opacity: 0; transform: translateX(-50%) translateY(-20px); }
        to   { opacity: 1; transform: translateX(-50%) translateY(0); }
      }
    `;
    document.head.appendChild(style);
  }

  document.body.appendChild(notif);
  setTimeout(() => notif.remove(), 3500);
}

// Buton yükleme durumu
function setLoading(btn, isLoading) {
  btn.disabled   = isLoading;
  btn.textContent = isLoading ? '...' : btn.dataset.original;
}

// ─── GİRİŞ FORMU ────────────────────────────────────────────────────────────

document.getElementById('login-form').addEventListener('submit', async (e) => {
  e.preventDefault();

  const username = document.getElementById('login-username').value.trim();
  const password = document.getElementById('login-password').value;
  const btn      = e.target.querySelector('button[type="submit"]');

  if (!username || !password) {
    showNotification('Kullanıcı adı ve şifreyi gir!', true);
    return;
  }

  if (!btn.dataset.original) btn.dataset.original = btn.textContent;
  setLoading(btn, true);

  try {
    const res  = await fetch('/login', {
      method : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body   : JSON.stringify({ username, password })
    });
    const data = await res.json();

    if (data.success) {
      showNotification(data.message);
      setTimeout(() => {
        window.location.href = '/';   // Flask ana sayfaya yönlendir
      }, 800);
    } else {
      showNotification(data.message, true);
    }
  } catch (err) {
    showNotification('Bağlantı hatası, tekrar dene!', true);
  } finally {
    setLoading(btn, false);
  }
});

// ─── KAYIT FORMU ─────────────────────────────────────────────────────────────

document.getElementById('register-form').addEventListener('submit', async (e) => {
  e.preventDefault();

  const username = document.getElementById('reg-username').value.trim();
  const email    = document.getElementById('reg-email').value.trim();
  const password = document.getElementById('reg-password').value;
  const btn      = e.target.querySelector('button[type="submit"]');

  if (!username || !email || !password) {
    showNotification('Lütfen tüm alanları doldur!', true);
    return;
  }

  if (password.length < 6) {
    showNotification('Şifre en az 6 karakter olmalı!', true);
    return;
  }

  if (!btn.dataset.original) btn.dataset.original = btn.textContent;
  setLoading(btn, true);

  try {
    const res  = await fetch('/register', {
      method : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body   : JSON.stringify({ username, email, password })
    });
    const data = await res.json();

    if (data.success) {
      showNotification('Kayıt başarılı! Giriş yapabilirsin 🎉');
      setTimeout(() => toggleAuth(), 1500);   // Giriş formuna geç
    } else {
      showNotification(data.message, true);
    }
  } catch (err) {
    showNotification('Bağlantı hatası, tekrar dene!', true);
  } finally {
    setLoading(btn, false);
  }
});