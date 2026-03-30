

// ─── MESAJ FONKSİYONLARI ────────────────────────────────────
function addMsg(text, type) {
  const msgs = document.getElementById('chatMessages');
  const div  = document.createElement('div');
  div.className = 'msg ' + type;

  // Markdown benzeri **bold** desteği
  div.innerHTML = text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>');

  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function addTyping() {
  const msgs = document.getElementById('chatMessages');
  const div  = document.createElement('div');
  div.className = 'msg bot';
  div.id        = 'typing';
  div.innerHTML = '<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>';
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}
function removeTyping() {
  const t = document.getElementById('typing');
  if (t) t.remove();
}

// ─── ANA SOHBET ──────────────────────────────────────────────
async function sendChat() {
  const inp = document.getElementById('chatInput');
  const v   = inp.value.trim();
  if (!v) return;
  addMsg(v, 'user');
  inp.value = '';
  addTyping();
  try {
    const reply = await getBotResponse(v);
    removeTyping();
    addMsg(reply, 'bot');
  } catch (err) {
    removeTyping();
    addMsg('Bir hata oluştu, tekrar dener misin?', 'bot');
  }
}

async function sendSug(text) {
  addMsg(text, 'user');
  addTyping();
  try {
    const reply = await getBotResponse(text);
    removeTyping();
    addMsg(reply, 'bot');
  } catch (err) {
    removeTyping();
    addMsg('Bir hata oluştu, tekrar dener misin?', 'bot');
  }
}

async function getBotResponse(userMessage) {
  const res  = await fetch('/soru-sor', {
    method : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body   : JSON.stringify({ message: userMessage })
  });
  const data = await res.json();
  return data.reply;
}

// ─── ÖĞÜN PLANI ──────────────────────────────────────────────
async function getMealPlan() {
  addMsg('Haftalık öğün planı oluştur 📅', 'user');
  addTyping();
  try {
    const res  = await fetch('/ogün-plani', { method: 'POST' });
    const data = await res.json();
    removeTyping();
    addMsg(data.reply, 'bot');
  } catch {
    removeTyping();
    addMsg('Öğün planı oluşturulamadı, tekrar dene.', 'bot');
  }
}

// ─── TARİF ÖNERİSİ ───────────────────────────────────────────
async function getRecipeSuggestion() {
  const saat = new Date().getHours();
  const ogün = saat < 10 ? 'kahvaltı' : saat < 15 ? 'öğle yemeği' : 'akşam yemeği';

  addMsg(`${ogün} için tarif öner 🍽️`, 'user');
  addTyping();
  try {
    const res  = await fetch('/tarif-oner', {
      method : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body   : JSON.stringify({ meal_type: ogün })
    });
    const data = await res.json();
    removeTyping();
    addMsg(data.reply, 'bot');
  } catch {
    removeTyping();
    addMsg('Tarif önerisi alınamadı, tekrar dene.', 'bot');
  }
}

// ─── KİLO KAYDET ─────────────────────────────────────────────
function showWeightInput() {
  const msgs = document.getElementById('chatMessages');

  // Varsa eski input'u kaldır
  const existing = document.getElementById('weight-input-msg');
  if (existing) existing.remove();

  const div = document.createElement('div');
  div.id        = 'weight-input-msg';
  div.className = 'msg bot';
  div.innerHTML = `
    <div style="font-size:13px;margin-bottom:8px">Bugünkü kilonu gir:</div>
    <div style="display:flex;gap:8px">
      <input id="weightInputField" type="number" step="0.1" min="30" max="250"
        placeholder="örn: 68.5"
        style="flex:1;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);
               color:white;border-radius:8px;padding:8px 12px;font-size:14px;outline:none">
      <button onclick="saveWeight()"
        style="background:var(--lime);color:var(--dark);border:none;border-radius:8px;
               padding:8px 14px;font-weight:700;cursor:pointer;font-size:13px">
        Kaydet
      </button>
    </div>`;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
  document.getElementById('weightInputField').focus();
}

async function saveWeight() {
  const val = document.getElementById('weightInputField')?.value;
  if (!val) return;

  document.getElementById('weight-input-msg')?.remove();
  addMsg(`Kilom: ${val} kg ⚖️`, 'user');
  addTyping();

  try {
    const res  = await fetch('/kilo-kaydet', {
      method : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body   : JSON.stringify({ weight: parseFloat(val) })
    });
    const data = await res.json();
    removeTyping();
    addMsg(data.message || 'Kilo kaydedildi! ✅', 'bot');
  } catch {
    removeTyping();
    addMsg('Kilo kaydedilemedi, tekrar dene.', 'bot');
  }
}

// ─── SOHBET TEMİZLE ──────────────────────────────────────────
async function clearChat() {
  if (!confirm('Sohbet geçmişini temizlemek istediğinden emin misin?')) return;

  await fetch('/sohbet-temizle', { method: 'POST' });

  const msgs = document.getElementById('chatMessages');
  msgs.innerHTML = '';
  addMsg('Sohbet temizlendi! Yeni bir konuşmaya başlayalım 🌱', 'bot');
}

// ─── CHATBOT AÇ/KAPAT ────────────────────────────────────────
let chatOpen = false;

function openChat() {
  chatOpen = true;
  const w = document.getElementById('chatWindow');
  w.style.display = 'flex';
  setTimeout(() => w.classList.add('open'), 10);
}

function closeChat() {
  chatOpen = false;
  const w = document.getElementById('chatWindow');
  w.classList.remove('open');
  setTimeout(() => w.style.display = 'none', 300);
}

// ─── TYPING ANİMASYONU CSS ────────────────────────────────────
(function injectTypingStyle() {
  if (document.getElementById('typing-style')) return;
  const s = document.createElement('style');
  s.id = 'typing-style';
  s.textContent = `
    .typing-dot {
      display: inline-block;
      width: 7px; height: 7px;
      background: var(--lime);
      border-radius: 50%;
      margin: 0 2px;
      animation: typingBounce 1.2s infinite ease-in-out;
    }
    .typing-dot:nth-child(2) { animation-delay: 0.2s; }
    .typing-dot:nth-child(3) { animation-delay: 0.4s; }
    @keyframes typingBounce {
      0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
      40%           { transform: translateY(-6px); opacity: 1; }
    }
  `;
  document.head.appendChild(s);
})();