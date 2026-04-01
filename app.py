import os
import re
import json
import requests
from datetime import date
from flask import (Flask, render_template, request, jsonify,
                   send_from_directory, session, redirect, url_for)
from database_manager import DatabaseManager

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY", "fitlife-secret-2026")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = "llama-3.3-70b-versatile"
USDA_API_KEY = os.environ.get("USDA_API_KEY", "")

db = DatabaseManager()


def today():
    return str(date.today())


def call_groq(messages, system_prompt, max_tokens=1500):
    try:
        all_messages = [
            {"role": "system", "content": system_prompt}] + messages
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": GROQ_MODEL,
                "messages": all_messages,
                "max_tokens": max_tokens,
                "temperature": 0.7
            },
            timeout=30
        )
        result = resp.json()
        if "choices" in result and result["choices"]:
            content = result["choices"][0]["message"]["content"]
            lines = content.split('\n')
            filtered = []
            for line in lines:
                lower = line.lower().strip()
                if any(word in lower for word in ['merhaba', 'selam', 'hos geldin', 'sultan', 'gunaydin', 'iyi gunler', 'nasilsin', 'nasil yardimci']):
                    continue
                filtered.append(line)
            content = '\n'.join(filtered).strip()
            return content
        elif "error" in result:
            err = result["error"].get("message", "Bilinmeyen hata")
            return f"AI hatasi: {err}"
        return "Su an cevap uretemiyorum, biraz sonra tekrar dene"
    except requests.exceptions.Timeout:
        return "AI yanit vermede gecikiyor. Biraz sonra tekrar dene."
    except Exception as e:
        return f"Baglanti hatasi: {str(e)}"


def build_system_prompt(user_id):
    profile = db.get_user_profile(user_id)
    sleep_data = db.get_latest_sleep_log(user_id)
    foods = db.get_today_foods(user_id)
    exercises = db.get_today_exercises(user_id)
    weight_log = db.get_weight_history(user_id, limit=5)
    period_log = db.get_latest_period_log(user_id)

    if not profile:
        return "Sen FitBot'sun. Saglikli beslenme ve fitness konusunda Turkce yardim eden bir asistansin."

    current = profile.get('current_weight', 70)
    target = profile.get('target_weight', 60)
    diff = round(current - target, 1)
    notes = profile.get('notes', '')
    username = session.get('username', 'Kullanici')
    ad_soyad = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip(
    ) or username
    age = profile.get('age', '')
    gender = profile.get('gender', '')
    height = profile.get('height_cm', '')
    activity = profile.get('activity_level', 'orta')

    food_str = (", ".join(f"{f['name']} ({int(f['kcal'])} kcal)" for f in foods)
                if foods else "Bugun henuz yemek kaydedilmemis")
    total_kcal = sum(f['kcal'] for f in foods)

    ex_str = (", ".join(f"{e['emoji']} {e['name']} (~{int(e['kcal'])} kcal)" for e in exercises)
              if exercises else "Bugun egzersiz yapilmamis")
    ex_kcal = sum(e['kcal'] for e in exercises)

    sleep_str = "Uyku verisi henuz girilmemis."
    if sleep_data:
        sleep_str = f"Son uykun {sleep_data.get('sleep_start', '?')} ile {sleep_data.get('sleep_end', '?')} arasindaydi."

    trend_str = "Henuz yeterli kilo gecmisi yok."
    if len(weight_log) >= 2:
        trend = weight_log[0]['weight'] - weight_log[-1]['weight']
        trend_str = f"Son {len(weight_log)} kayitta {abs(trend):.1f} kg {'vermis' if trend > 0 else 'almis'}."

    period_str = "Regl verisi girilmemis."
    if period_log:
        period_str = (f"Son regl: {period_log['last_period_date']}, "
                      f"dongu uzunlugu: {period_log['cycle_length']} gun, "
                      f"sure: {period_log['period_duration']} gun.")

    return f"""Sen FitBot'sun. Saglikli beslenme ve fitness konusunda Turkce yardim eden uzman bir asistansin.

Kullanici: {ad_soyad}
Yas/Cinsiyet: {age} / {gender} | Boy: {height} cm
Aktivite: {activity}
Mevcut kilo: {current} kg | Hedef: {target} kg | Kalan: {diff} kg
Kilo trendi: {trend_str}
Bugun yedikleri: {food_str} (Toplam: {int(total_kcal)} kcal)
Egzersizler: {ex_str} (Yakilan: {int(ex_kcal)} kcal)
Net kalori: {int(total_kcal - ex_kcal)} kcal
Uyku: {sleep_str}
Regl dongusu: {period_str}
Ozel notlar: {notes}

Turkce yanitla. Selamlama yapma. Direkt soruyu cevapla. Kisa, net ve destekleyici ol.
"""


@app.route('/')
def ana_sayfa():
    return render_template('index.html')


@app.route('/login-page')
def login_page():
    if 'user_id' in session:
        return redirect(url_for('ana_sayfa'))
    return render_template('auth.html')


@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    if not username or not email or not password:
        return jsonify({"success": False, "message": "Lutfen tum alanlari doldur!"}), 400
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
        return jsonify({"success": True, "message": f"Hos geldin {username}!"})
    return jsonify({"success": False, "message": result})


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('ana_sayfa'))


@app.route('/soru-sor', methods=['POST'])
def cevap_ver():
    if 'user_id' not in session:
        return jsonify({"login_required": True, "reply": "FitBot'u kullanmak icin giris yapman gerekiyor!"})
    user_id = session['user_id']
    user_message = request.json.get("message", "").strip()
    if not user_message:
        return jsonify({"reply": "Bir seyler yazmay unuttun!"})
    history = db.get_chat_history(user_id, limit=12)
    db.save_chat_message(user_id, "user", user_message)
    messages = history + [{"role": "user", "content": user_message}]
    system = build_system_prompt(user_id)
    reply = call_groq(messages, system, max_tokens=1500)
    db.save_chat_message(user_id, "assistant", reply)
    return jsonify({"reply": reply})


# DÜZELTME: Türkçe karakter içeren route ASCII'ye çevrildi
@app.route('/ogun-plani', methods=['POST'])
def ogun_plani():
    if 'user_id' not in session:
        return jsonify({"login_required": True, "reply": "Giris yapmalısin!"}), 401
    user_id = session['user_id']
    profile = db.get_user_profile(user_id)
    notes = profile.get('notes', '') if profile else ''
    current = profile.get('current_weight', 70) if profile else 70
    target = profile.get('target_weight', 60) if profile else 60
    diff = current - target
    hedef = "kilo vermek" if diff > 0 else (
        "kilo almak" if diff < 0 else "kilosunu korumak")
    prompt = (f"Kullanici icin 7 gunluk ogun plani olustur.\n"
              f"Hedef: {hedef} ({abs(diff):.1f} kg)\nOzel notlar: {notes}\n\n"
              f"Format: Pazartesi - Kahvalti: ... - Ogle: ... - Aksam: ... - Atistirmalik: ...\n"
              f"7 gunun tamamini yaz.")
    reply = call_groq([{"role": "user", "content": prompt}],
                      "Turkce, pratik ogun planlari yapan diyetisyensin.",
                      max_tokens=2000)
    db.save_chat_message(user_id, "user", "Haftalik ogun plani olustur")
    db.save_chat_message(user_id, "assistant", reply)
    return jsonify({"reply": reply})


@app.route('/tarif-oner', methods=['POST'])
def tarif_oner():
    if 'user_id' not in session:
        return jsonify({"login_required": True, "reply": "Giris yapmalısin!"}), 401
    user_id = session['user_id']
    profile = db.get_user_profile(user_id)
    foods = db.get_today_foods(user_id)
    notes = profile.get('notes', '') if profile else ''
    total_kcal = sum(f['kcal'] for f in foods)
    kalan_kcal = max(0, 2200 - int(total_kcal))
    ogun_tipi = request.json.get("meal_type", "aksam yemegi")
    prompt = (f"Bugun {int(total_kcal)} kcal yedi, kalan: {kalan_kcal} kcal\n"
              f"Ogun: {ogun_tipi}\nYasak malzeme: {notes}\n\n"
              f"2 kisa tarif oner (isim, kalori, malzeme, 3 adim).")
    reply = call_groq([{"role": "user", "content": prompt}],
                      "Turkce pratik tarif oneren diyetisyensin.",
                      max_tokens=1000)
    db.save_chat_message(user_id, "user", f"{ogun_tipi} tarif onerisi istedi")
    db.save_chat_message(user_id, "assistant", reply)
    return jsonify({"reply": reply})


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
        msg = f"Hedefe ulastin! {kilo} kg"
    elif diff > 0:
        msg = f"{kilo} kg kaydedildi. Hedefe {diff} kg kaldi!"
    else:
        msg = f"{kilo} kg kaydedildi. Hedefe {abs(diff)} kg gectin!"
    return jsonify({"success": True, "message": msg})


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


@app.route('/hesapla-bmi', methods=['POST'])
def hesapla_bmi():
    data = request.json
    try:
        kilo = float(data.get("weight", 0))
        boy_cm = float(data.get("height", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Gecersiz deger"}), 400
    if boy_cm <= 0 or kilo <= 0:
        return jsonify({"error": "Boy ve kilo sifirdan buyuk olmali"}), 400
    bmi = round(kilo / (boy_cm / 100) ** 2, 1)
    if bmi < 18.5:
        kategori = "Zayif"
    elif bmi < 25:
        kategori = "Normal Kilolu"
    elif bmi < 30:
        kategori = "Fazla Kilolu"
    else:
        kategori = "Obez"
    if 'user_id' in session:
        db.update_user_profile(
            session['user_id'], current_weight=kilo, height_cm=boy_cm)
    return jsonify({"bmi": bmi, "message": kategori})


def _ai_kalori(food_name):
    system_prompt = """Sen uzman bir beslenme bilimcisi ve diyetisyensin.
SADECE gecerli JSON don dur, baska hicbir sey yazma.
JSON FORMATI:
{"name":"yemek adi","kcal_per_100g":sayi,"portion":"porsiyon miktari","portion_kcal":sayi,"protein_per_100g":sayi,"carb_per_100g":sayi,"fat_per_100g":sayi}"""

    prompt = f'Bu yiyecek icin kalori bilgisi ver: "{food_name}". SADECE JSON don dur:'

    raw = call_groq([{"role": "user", "content": prompt}],
                    system_prompt, max_tokens=300)
    raw = raw.strip()

    code_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
    if code_match:
        raw = code_match.group(1)

    json_match = re.search(r'\{[^{}]+\}', raw, re.DOTALL)
    if not json_match:
        return None

    try:
        data = json.loads(json_match.group())
        kcal_100 = data.get("kcal_per_100g", 0)
        portion_kcal = data.get("portion_kcal", 0)
        if kcal_100 == 0 and portion_kcal == 0:
            return None
        if portion_kcal == 0 and kcal_100 > 0:
            data["portion_kcal"] = round(kcal_100 * 1.5)
            data["portion"] = data.get("portion", "~150g")
        return data
    except json.JSONDecodeError:
        return None


@app.route('/kalori-ara', methods=['POST'])
def kalori_ara():
    food_name = request.json.get("food", "").strip()
    if not food_name:
        return jsonify({"found": False, "message": "Yemek adi bos"})

    food_id = None
    ai_result = _ai_kalori(food_name)
    if ai_result:
        name = ai_result.get("name", food_name)
        kcal_100 = ai_result.get("kcal_per_100g", 0)
        portion_kcal = ai_result.get("portion_kcal", 0) or kcal_100
        portion = ai_result.get("portion", "1 porsiyon")
        protein = ai_result.get("protein_per_100g", 0)
        carb = ai_result.get("carb_per_100g", 0)
        fat = ai_result.get("fat_per_100g", 0)
        display_kcal = portion_kcal if portion_kcal > 0 else kcal_100
        if display_kcal == 0:
            return jsonify({"found": False, "message": "Kalori hesaplanamadi."})
        if 'user_id' in session:
            food_id = db.add_food_log(session['user_id'], name, display_kcal)
        return jsonify({
            "found": True, "id": food_id, "name": name,
            "kcal_per_100g": kcal_100, "portion": portion,
            "portion_kcal": display_kcal, "protein": protein,
            "carb": carb, "fat": fat, "source": "ai",
            "message": f"{name}: ~{display_kcal} kcal ({portion})"
        })

    return jsonify({"found": False, "message": f"'{food_name}' bulunamadi."})


@app.route('/yemek-sil', methods=['POST'])
def yemek_sil():
    if 'user_id' not in session:
        return jsonify({"success": False}), 401
    food_id = request.json.get("id")
    if not food_id:
        return jsonify({"success": False, "message": "ID eksik"}), 400
    db.delete_food_log(session['user_id'], int(food_id))
    return jsonify({"success": True})


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
                        data.get("name", ""), data.get("emoji", ""), data.get("kcal", 0))
    return jsonify({"success": True})


@app.route('/bugunun-verileri', methods=['GET'])
def bugunun_verileri():
    if 'user_id' not in session:
        return jsonify({"water": 0, "foods": [], "exercises": [], "username": None, "profile": None})
    uid = session['user_id']
    return jsonify({
        "profile": db.get_user_profile(uid),
        "water": db.get_today_water(uid),
        "foods": db.get_today_foods(uid),
        "exercises": db.get_today_exercises(uid),
        "username": session.get('username', '')
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
    return jsonify({"success": True, "message": "Uyku verisi kaydedildi!"})


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
    return jsonify({"success": ok, "message": "Regl verisi kaydedildi!" if ok else "Hata olustu"})


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


@app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    admin_password = os.environ.get("ADMIN_PASSWORD", "fitlife-admin-2026")
    if request.method == 'POST':
        pw = request.form.get('pw')
        if pw == admin_password:
            session['admin'] = True
            return redirect(url_for('admin_panel'))
        else:
            return jsonify({'error': 'Yanlış şifre'}), 401

    # GET request
    if not session.get('admin'):
        return """
        <form method="post">
          <h2>🔐 Admin Paneli</h2>
          <input type="password" name="pw" placeholder="Şifre">
          <button type="submit">Giriş</button>
        </form>
        """, 401
    users = db.get_all_users()
    rows = "".join(
        f"<tr><td>{u['id']}</td><td>{u['username']}</td><td>{u['email']}</td></tr>"
        for u in users
    )
    return f"""
    <html><head><style>
      body{{font-family:sans-serif;padding:30px;background:#0f172a;color:#e2e8f0;margin:0}}
      h2{{color:#a78bfa}} 
      table{{border-collapse:collapse;width:100%;margin-top:20px}}
      th,td{{border:1px solid #334155;padding:12px;text-align:left}}
      th{{background:#1e293b;color:#a78bfa}}
      tr:hover{{background:#1e293b}}
    </style></head><body>
      <h2>👥 Kayıtlı Kullanıcılar — {len(users)} kişi</h2>
      <table>
        <tr><th>ID</th><th>Kullanıcı Adı</th><th>Email</th></tr>
        {rows}
      </table>
      <a href="/logout">Çıkış</a>
    </body></html>"""


if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
