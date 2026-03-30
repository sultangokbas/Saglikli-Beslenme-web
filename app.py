import os
import re
import json
import requests
from datetime import date
from flask import (Flask, render_template, request, jsonify,
                   send_from_directory, session, redirect, url_for)
from database_manager import DatabaseManager

app = Flask(__name__)

# ─── AYARLAR ────────────────────────────────────────────────────────────────
app.secret_key = os.environ.get("SECRET_KEY", "fitlife-secret-2026")

OPENROUTER_API_KEY = os.environ.get(
    "OPENROUTER_API_KEY",
    "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"
)
OPENROUTER_MODEL = "openai/gpt-4o-mini"
USDA_API_KEY = "jiiyv22D8iIax8T3Uhd8EGs6YGScugGwUGD5ynEf"

db = DatabaseManager()


# ─── YARDIMCI ───────────────────────────────────────────────────────────────

def today():
    return str(date.today())


def build_system_prompt(user_id):
    profile = db.get_user_profile(user_id)
    sleep_data = db.get_latest_sleep_log(user_id)
    foods = db.get_today_foods(user_id)
    exercises = db.get_today_exercises(user_id)
    weight_log = db.get_weight_history(user_id, limit=5)
    period_log = db.get_latest_period_log(user_id)

    if not profile:
        return "Sen FitBot'sun. Sağlıklı beslenme ve fitness konusunda Türkçe yardım eden bir asistansın."

    current = profile.get('current_weight', 70)
    target = profile.get('target_weight', 60)
    diff = round(current - target, 1)
    notes = profile.get('notes', '')
    username = session.get('username', 'Kullanıcı')
    ad_soyad = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip(
    ) or username
    age = profile.get('age', '')
    gender = profile.get('gender', '')
    height = profile.get('height_cm', '')
    activity = profile.get('activity_level', 'orta')

    food_str = (", ".join(f"{f['name']} ({int(f['kcal'])} kcal)" for f in foods)
                if foods else "Bugün henüz yemek kaydedilmemiş")
    total_kcal = sum(f['kcal'] for f in foods)

    ex_str = (", ".join(f"{e['emoji']} {e['name']} (~{int(e['kcal'])} kcal)" for e in exercises)
              if exercises else "Bugün egzersiz yapılmamış")
    ex_kcal = sum(e['kcal'] for e in exercises)

    sleep_str = "Uyku verisi henüz girilmemiş."
    if sleep_data:
        sleep_str = (f"Son uykun {sleep_data.get('sleep_start', '?')}–{sleep_data.get('sleep_end', '?')} "
                     f"arasındaydı.")

    trend_str = "Henüz yeterli kilo geçmişi yok."
    if len(weight_log) >= 2:
        trend = weight_log[0]['weight'] - weight_log[-1]['weight']
        trend_str = f"Son {len(weight_log)} kayıtta {abs(trend):.1f} kg {'vermiş' if trend > 0 else 'almış'}."

    period_str = "Regl verisi girilmemiş."
    if period_log:
        period_str = (f"Son regl: {period_log['last_period_date']}, "
                      f"döngü uzunluğu: {period_log['cycle_length']} gün, "
                      f"süre: {period_log['period_duration']} gün.")

    return f"""Sen FitBot'sun — FitLife AI'ın kişisel diyetisyen ve fitness koç asistanısın.

## Kullanıcı: {ad_soyad}
- Yaş / Cinsiyet   : {age} / {gender}  |  Boy: {height} cm
- Aktivite seviyesi: {activity}
- Mevcut kilo      : {current} kg  |  Hedef: {target} kg  |  Kalan: {diff} kg
- Kilo trendi      : {trend_str}
- Bugün yedikleri  : {food_str}  (Toplam: {int(total_kcal)} kcal)
- Egzersizler      : {ex_str}  (Yakılan: {int(ex_kcal)} kcal)
- Net kalori       : {int(total_kcal - ex_kcal)} kcal
- Uyku             : {sleep_str}
- Regl döngüsü     : {period_str}
- Özel notlar      : {notes}

Sen; alanında uzman bir diyetisyen, kişisel antrenör ve kadın sağlığı/hormon dengesi uzmanısın.
Empatik, anlayışlı, yargılamayan, motive eden ve gerçekçi çözümler sunan bir yaşam koçusun.
Türkçe yanıt ver. Kısa, net ve destekleyici ol."""


def call_openrouter(messages, system_prompt, max_tokens=1500):
    """OpenRouter API çağrısı. system prompt messages listesinin başında gönderilir."""
    try:
        all_messages = [
            {"role": "system", "content": system_prompt}] + messages
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:5000",
                "X-Title": "FitLife AI"
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": all_messages,
                "max_tokens": max_tokens,
                "temperature": 0.7
            },
            timeout=45
        )
        result = resp.json()
        if "choices" in result and result["choices"]:
            return result["choices"][0]["message"]["content"]
        elif "error" in result:
            err = result['error'].get('message', 'Bilinmeyen hata')
            print(f"OpenRouter hatası: {err}")
            return f"⚠️ AI hatası: {err}"
        return "Şu an cevap üretemiyorum, biraz sonra tekrar dene 🙏"
    except requests.exceptions.Timeout:
        return "AI yanıt vermede gecikiyor ⏳ Biraz sonra tekrar dene."
    except Exception as e:
        return f"Bağlantı hatası: {str(e)}"


# ─── SAYFALAR ────────────────────────────────────────────────────────────────

@app.route('/')
def ana_sayfa():
    return render_template('index.html')


@app.route('/login-page')
def login_page():
    if 'user_id' in session:
        return redirect(url_for('ana_sayfa'))
    return render_template('auth.html')


# ─── AUTH ─────────────────────────────────────────────────────────────────────

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    if not username or not email or not password:
        return jsonify({"success": False, "message": "Lütfen tüm alanları doldur! 🥑"}), 400
    success, message = db.register_user(username, email, password)
    return jsonify({"success": success, "message": message})


@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')
    success, result = db.login_user(username, password)
    if success:
        session['user_id'] = result
        session['username'] = username
        return jsonify({"success": True, "message": f"Hoş geldin {username}! ✨"})
    return jsonify({"success": False, "message": result})


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('ana_sayfa'))


# ─── FİTBOT ──────────────────────────────────────────────────────────────────

@app.route('/soru-sor', methods=['POST'])
def cevap_ver():
    if 'user_id' not in session:
        return jsonify({"login_required": True,
                        "reply": "FitBot'u kullanmak için giriş yapman gerekiyor! 🔑"})
    user_id = session['user_id']
    user_message = request.json.get("message", "").strip()
    if not user_message:
        return jsonify({"reply": "Bir şeyler yazmayı unuttun! 😊"})

    history = db.get_chat_history(user_id, limit=12)
    db.save_chat_message(user_id, "user", user_message)
    messages = history + [{"role": "user", "content": user_message}]
    system = build_system_prompt(user_id)
    reply = call_openrouter(messages, system, max_tokens=1500)
    db.save_chat_message(user_id, "assistant", reply)
    return jsonify({"reply": reply})


# ─── ÖĞÜN PLANI ──────────────────────────────────────────────────────────────

@app.route('/ogün-plani', methods=['POST'])
def ogün_plani():
    if 'user_id' not in session:
        return jsonify({"login_required": True, "reply": "Giriş yapmalısın!"}), 401
    user_id = session['user_id']
    profile = db.get_user_profile(user_id)
    notes = profile.get('notes', '') if profile else ''
    current = profile.get('current_weight', 70) if profile else 70
    target = profile.get('target_weight', 60) if profile else 60
    diff = current - target
    hedef = "kilo vermek" if diff > 0 else (
        "kilo almak" if diff < 0 else "kilosunu korumak")
    prompt = (f"Kullanıcı için 7 günlük öğün planı oluştur.\n"
              f"Hedef: {hedef} ({abs(diff):.1f} kg)\nÖzel notlar: {notes}\n\n"
              f"Format: **Pazartesi** - Kahvaltı: ... - Öğle: ... - Akşam: ... - Atıştırmalık: ...\n"
              f"7 günün tamamını yaz. Yasak malzemeleri kullanma.")
    reply = call_openrouter([{"role": "user", "content": prompt}],
                            "Türkçe, pratik öğün planları yapan diyetisyensin.",
                            max_tokens=2000)
    db.save_chat_message(user_id, "user", "Haftalık öğün planı oluştur")
    db.save_chat_message(user_id, "assistant", reply)
    return jsonify({"reply": reply})


# ─── TARİF ÖNERİSİ ───────────────────────────────────────────────────────────

@app.route('/tarif-oner', methods=['POST'])
def tarif_oner():
    if 'user_id' not in session:
        return jsonify({"login_required": True, "reply": "Giriş yapmalısın!"}), 401
    user_id = session['user_id']
    profile = db.get_user_profile(user_id)
    foods = db.get_today_foods(user_id)
    notes = profile.get('notes', '') if profile else ''
    total_kcal = sum(f['kcal'] for f in foods)
    kalan_kcal = max(0, 2200 - int(total_kcal))
    ogün_tipi = request.json.get("meal_type", "akşam yemeği")
    prompt = (f"Bugün {int(total_kcal)} kcal yedi, kalan: {kalan_kcal} kcal\n"
              f"Öğün: {ogün_tipi}\nYasak malzeme: {notes}\n\n"
              f"2 kısa tarif öner (isim, kalori, malzeme, 3 adım).")
    reply = call_openrouter([{"role": "user", "content": prompt}],
                            "Türkçe pratik tarif öneren diyetisyensin.",
                            max_tokens=1000)
    db.save_chat_message(user_id, "user", f"{ogün_tipi} tarif önerisi istedi")
    db.save_chat_message(user_id, "assistant", reply)
    return jsonify({"reply": reply})


# ─── KİLO TAKİBİ ─────────────────────────────────────────────────────────────

@app.route('/kilo-kaydet', methods=['POST'])
def kilo_kaydet():
    if 'user_id' not in session:
        return jsonify({"success": False}), 401
    kilo = request.json.get("weight")
    if not kilo:
        return jsonify({"success": False, "message": "Kilo girilmedi"}), 400
    db.add_weight_log(session['user_id'], float(kilo))
    db.update_user_profile(session['user_id'], current_weight=float(kilo))
    profile = db.get_user_profile(session['user_id'])
    target = profile.get('target_weight', 60)
    diff = round(float(kilo) - target, 1)
    if abs(diff) < 0.5:
        msg = f"🎉 Hedefe ulaştın! {kilo} kg — inanılmaz!"
    elif diff > 0:
        msg = f"💪 {kilo} kg kaydedildi. Hedefe {diff} kg kaldı!"
    else:
        msg = f"🔥 {kilo} kg kaydedildi. Hedefi {abs(diff)} kg geçtin!"
    return jsonify({"success": True, "message": msg})


# ─── SOHBET GEÇMİŞİ ──────────────────────────────────────────────────────────

@app.route('/sohbet-gecmisi', methods=['GET'])
def sohbet_gecmisi():
    if 'user_id' not in session:
        return jsonify({"success": False}), 401
    return jsonify({"success": True, "data": db.get_chat_history(session['user_id'], limit=50)})


@app.route('/sohbet-temizle', methods=['POST'])
def sohbet_temizle():
    if 'user_id' not in session:
        return jsonify({"success": False}), 401
    db.clear_chat_history(session['user_id'])
    return jsonify({"success": True})


# ─── BMI ─────────────────────────────────────────────────────────────────────

@app.route('/hesapla-bmi', methods=['POST'])
def hesapla_bmi():
    data = request.json
    try:
        kilo = float(data.get("weight", 0))
        boy_cm = float(data.get("height", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Geçersiz değer"}), 400
    if boy_cm <= 0 or kilo <= 0:
        return jsonify({"error": "Boy ve kilo sıfırdan büyük olmalı"}), 400
    bmi = round(kilo / (boy_cm / 100) ** 2, 1)
    if bmi < 18.5:
        kategori = "⚠️ Zayıf"
    elif bmi < 25:
        kategori = "✅ Normal Kilolu"
    elif bmi < 30:
        kategori = "⚠️ Fazla Kilolu"
    else:
        kategori = "🔴 Obez"
    if 'user_id' in session:
        db.update_user_profile(
            session['user_id'], current_weight=kilo, height_cm=boy_cm)
    return jsonify({"bmi": bmi, "message": kategori})


# ─── KALORİ ARA — USDA önce, AI fallback ─────────────────────────────────────

def _usda_lookup(food_name: str):
    """USDA API'den kalori sorgular. (name, kcal_per_100g) ya da None döner."""
    try:
        resp = requests.get(
            "https://api.nal.usda.gov/fdc/v1/foods/search",
            params={"query": food_name, "api_key": USDA_API_KEY,
                    "pageSize": 1, "dataType": "SR Legacy,Survey (FNDDS)"},
            timeout=5
        )
        result = resp.json()
        if result.get("foods"):
            food = result["foods"][0]
            kcal = 0
            for n in food.get("foodNutrients", []):
                if n.get("nutrientId") == 1008:
                    kcal = round(n.get("value", 0))
                    break
            if kcal > 0:
                return food.get("description", food_name), kcal
    except Exception as e:
        print(f"USDA hata: {e}")
    return None


def _ai_kalori(food_name: str):
    """
    AI modelinden kalori sorgular.
    Sadece JSON döndür talimatıyla kısa ve güvenilir çıktı alır.
    max_tokens=250 JSON için yeterli, kesilme riski yok.
    """
    prompt = (
        f'"{food_name}" için kalori bilgisi ver.\n'
        f'SADECE aşağıdaki JSON formatında yanıt ver, başka hiçbir şey yazma:\n'
        f'{{"name":"Türkçe yemek adı","kcal_per_100g":sayı,"portion":"tipik porsiyon açıklaması","portion_kcal":sayı}}\n'
        f'Kurallar: kcal değerleri gerçekçi olsun, asla 0 yazma, yorum ekleme, sadece JSON.'
    )
    raw = call_openrouter(
        [{"role": "user", "content": prompt}],
        "Sen bir diyetisyensin. Sadece JSON formatında yanıt veriyorsun, açıklama yazmıyorsun.",
        max_tokens=250   # JSON için 250 token kesinlikle yeterli
    )
    # JSON bloğunu yakala (bazen model ``` ile sarar)
    match = re.search(r'\{[^{}]+\}', raw, re.DOTALL)
    if not match:
        print(f"AI JSON parse hatası. Raw: {raw[:200]}")
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError as e:
        print(f"JSON decode hatası: {e}. Raw: {match.group()[:200]}")
        return None


@app.route('/kalori-ara', methods=['POST'])
def kalori_ara():
    food_name = request.json.get("food", "").strip()
    if not food_name:
        return jsonify({"found": False, "message": "Yemek adı boş"})

    food_id = None

    # 1) USDA dene (daha hızlı ve güvenilir)
    usda = _usda_lookup(food_name)
    if usda:
        name, kcal_100 = usda
        if 'user_id' in session:
            food_id = db.add_food_log(session['user_id'], name, kcal_100)
        return jsonify({
            "found": True,
            "id": food_id,
            "name": name,
            "kcal_per_100g": kcal_100,
            "portion": "100g",
            "portion_kcal": kcal_100,
            "source": "usda",
            "message": f"{name}: 100g başına ~{kcal_100} kcal"
        })

    # 2) AI fallback
    ai = _ai_kalori(food_name)
    if ai:
        name = ai.get("name", food_name)
        kcal_100 = ai.get("kcal_per_100g") or 0
        por_kcal = ai.get("portion_kcal") or kcal_100
        portion = ai.get("portion", "")
        # Güvenlik: sıfır kcal gelirse kullanma
        display_kcal = por_kcal if por_kcal > 0 else kcal_100
        if display_kcal == 0:
            return jsonify({"found": False,
                            "message": "Kalori değeri hesaplanamadı, lütfen manuel gir"})
        if 'user_id' in session:
            food_id = db.add_food_log(session['user_id'], name, display_kcal)
        return jsonify({
            "found": True,
            "id": food_id,
            "name": name,
            "kcal_per_100g": kcal_100,
            "portion": portion,
            "portion_kcal": display_kcal,
            "source": "ai",
            "message": f"{name}: ~{display_kcal} kcal"
        })

    return jsonify({"found": False,
                    "message": "Yemek bulunamadı. Lütfen daha açık bir isim dene."})


# ─── YEMEK SİL ───────────────────────────────────────────────────────────────

@app.route('/yemek-sil', methods=['POST'])
def yemek_sil():
    if 'user_id' not in session:
        return jsonify({"success": False}), 401
    food_id = request.json.get("id")
    if not food_id:
        return jsonify({"success": False, "message": "ID eksik"}), 400
    db.delete_food_log(session['user_id'], int(food_id))
    return jsonify({"success": True})


# ─── DİĞER ARAÇLAR ───────────────────────────────────────────────────────────

@app.route('/su-kaydet', methods=['POST'])
def su_kaydet():
    if 'user_id' not in session:
        return jsonify({"success": False}), 401
    db.save_water(session['user_id'], request.json.get("count", 0))
    return jsonify({"success": True})


@app.route('/egzersiz-ekle', methods=['POST'])
def egzersiz_ekle():
    if 'user_id' not in session:
        return jsonify({"success": False}), 401
    data = request.json
    db.add_exercise_log(session['user_id'],
                        data.get("name", ""), data.get("emoji", "🏃"), data.get("kcal", 0))
    return jsonify({"success": True})


@app.route('/bugunun-verileri', methods=['GET'])
def bugunun_verileri():
    if 'user_id' not in session:
        return jsonify({"water": 0, "foods": [], "exercises": [],
                        "username": None, "profile": None})
    uid = session['user_id']
    return jsonify({
        "profile":   db.get_user_profile(uid),
        "water":     db.get_today_water(uid),
        "foods":     db.get_today_foods(uid),   # id alanı da geliyor artık
        "exercises": db.get_today_exercises(uid),
        "username":  session.get('username', '')
    })


@app.route('/update-profile', methods=['POST'])
def update_profile():
    if 'user_id' not in session:
        return jsonify({"success": False}), 401
    data = request.json
    success, message = db.update_user_profile(
        session['user_id'],
        first_name=data.get('first_name'),
        last_name=data.get('last_name'),
        age=data.get('age'),
        gender=data.get('gender'),
        activity_level=data.get('activity_level'),
        current_weight=data.get('current_weight'),
        target_weight=data.get('target_weight'),
        height_cm=data.get('height_cm'),
        notes=data.get('notes')
    )
    return jsonify({"success": success, "message": message})


@app.route('/log-sleep', methods=['POST'])
def log_sleep():
    if 'user_id' not in session:
        return jsonify({"success": False}), 401
    data = request.json
    db.add_sleep_log(session['user_id'],
                     data.get('start'), data.get('end'),
                     data.get('quality'), data.get('notes'))
    return jsonify({"success": True, "message": "Uyku verisi kaydedildi! 😴"})


# ─── REGL TAKİBİ ─────────────────────────────────────────────────────────────

@app.route('/regl-kaydet', methods=['POST'])
def regl_kaydet():
    if 'user_id' not in session:
        return jsonify({"success": False}), 401
    data = request.json
    ok = db.save_period_log(
        session['user_id'],
        last_period_date=data.get('last_period_date', ''),
        cycle_length=int(data.get('cycle_length', 28)),
        period_duration=int(data.get('period_duration', 5)),
        notes=data.get('notes', '')
    )
    return jsonify({"success": ok, "message": "Regl verisi kaydedildi! 🌸" if ok else "Hata oluştu"})


@app.route('/regl-verisi', methods=['GET'])
def regl_verisi():
    if 'user_id' not in session:
        return jsonify({"success": False}), 401
    log = db.get_latest_period_log(session['user_id'])
    return jsonify({"success": True, "data": log})


@app.route('/favicon.ico')
@app.route('/avokado-ikon.png')
def favicon():
    return send_from_directory(app.root_path, 'avokado-ikon.png', mimetype='image/png')


# ─── BAŞLATMA ────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
