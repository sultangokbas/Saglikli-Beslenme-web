import os
import re
import json
import requests
from datetime import date, datetime
from flask import (Flask, render_template, request, jsonify,
                   send_from_directory, session, redirect, url_for)
from database_manager import DatabaseManager

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "fitlife-secret-2026")

db = DatabaseManager()


def today():
    return str(date.today())


# ─── API KEY'LERİ DB'DEN OKU (env yoksa) ─────────────────────────────────────
def get_groq_key():
    key = db.get_setting('groq_api_key')
    return key if key else os.environ.get("GROQ_API_KEY", "")


def get_groq_model():
    return db.get_setting('groq_model') or "llama-3.3-70b-versatile"


def get_max_tokens():
    try:
        return int(db.get_setting('max_tokens') or 1500)
    except:
        return 1500


def call_groq(messages, system_prompt, max_tokens=None):
    if max_tokens is None:
        max_tokens = get_max_tokens()
    groq_key = get_groq_key()
    model = get_groq_model()
    try:
        all_messages = [
            {"role": "system", "content": system_prompt}] + messages
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {groq_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": model,
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
                if any(word in lower for word in ['merhaba', 'selam', 'hos geldin', 'sultan',
                                                  'gunaydin', 'iyi gunler', 'nasilsin', 'nasil yardimci']):
                    continue
                filtered.append(line)
            return '\n'.join(filtered).strip()
        elif "error" in result:
            return f"AI hatası: {result['error'].get('message', 'Bilinmeyen hata')}"
        return "Şu an cevap üretemiyorum, biraz sonra tekrar dene."
    except requests.exceptions.Timeout:
        return "AI yanıt vermede gecikiyor. Biraz sonra tekrar dene."
    except Exception as e:
        return f"Bağlantı hatası: {str(e)}"


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
        sleep_str = f"Son uyku {sleep_data.get('sleep_start', '?')} ile {sleep_data.get('sleep_end', '?')} arasındaydı."

    trend_str = "Henüz yeterli kilo geçmişi yok."
    if len(weight_log) >= 2:
        trend = weight_log[0]['weight'] - weight_log[-1]['weight']
        trend_str = f"Son {len(weight_log)} kayıtta {abs(trend):.1f} kg {'vermiş' if trend > 0 else 'almış'}."

    period_str = "Regl verisi girilmemiş."
    if period_log:
        period_str = (f"Son regl: {period_log['last_period_date']}, "
                      f"döngü: {period_log['cycle_length']} gün, "
                      f"süre: {period_log['period_duration']} gün.")

    calorie_goal = db.get_setting('daily_calorie_goal') or '2200'

    return f"""Sen FitBot'sun. Sağlıklı beslenme ve fitness konusunda Türkçe yardım eden uzman bir asistansın.

Kullanıcı: {ad_soyad}
Yaş/Cinsiyet: {age} / {gender} | Boy: {height} cm
Aktivite: {activity}
Mevcut kilo: {current} kg | Hedef: {target} kg | Kalan: {diff} kg
Kilo trendi: {trend_str}
Bugün yedikleri: {food_str} (Toplam: {int(total_kcal)} kcal / Hedef: {calorie_goal} kcal)
Egzersizler: {ex_str} (Yakılan: {int(ex_kcal)} kcal)
Net kalori: {int(total_kcal - ex_kcal)} kcal
Uyku: {sleep_str}
Regl döngüsü: {period_str}
Özel notlar: {notes}

Türkçe yanıtla. Selamlama yapma. Direkt soruyu cevapla. Kısa, net ve destekleyici ol."""


# ════════════════════════════════════════════════════════════════════════════
# KULLANICI ROUTE'LARI
# ════════════════════════════════════════════════════════════════════════════

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
        return jsonify({"success": False, "message": "Lütfen tüm alanları doldur!"}), 400
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
        return jsonify({"success": True, "message": f"Hoş geldin {username}!"})
    return jsonify({"success": False, "message": result})


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('ana_sayfa'))


@app.route('/soru-sor', methods=['POST'])
def cevap_ver():
    if 'user_id' not in session:
        return jsonify({"login_required": True, "reply": "FitBot'u kullanmak için giriş yapman gerekiyor!"})
    user_id = session['user_id']
    user_message = request.json.get("message", "").strip()
    if not user_message:
        return jsonify({"reply": "Bir şeyler yazmayı unuttun!"})
    history = db.get_chat_history(user_id, limit=12)
    db.save_chat_message(user_id, "user", user_message)
    messages = history + [{"role": "user", "content": user_message}]
    system = build_system_prompt(user_id)
    reply = call_groq(messages, system)
    db.save_chat_message(user_id, "assistant", reply)
    return jsonify({"reply": reply})


@app.route('/ogun-plani', methods=['POST'])
def ogun_plani():
    if 'user_id' not in session:
        return jsonify({"login_required": True}), 401
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
              f"Format: Pazartesi - Kahvaltı: ... - Öğle: ... - Akşam: ... - Atıştırmalık: ...\n7 günün tamamını yaz.")
    reply = call_groq([{"role": "user", "content": prompt}],
                      "Türkçe, pratik öğün planları yapan diyetisyensin.", max_tokens=2000)
    db.save_chat_message(user_id, "user", "Haftalık öğün planı oluştur")
    db.save_chat_message(user_id, "assistant", reply)
    return jsonify({"reply": reply})


@app.route('/tarif-oner', methods=['POST'])
def tarif_oner():
    if 'user_id' not in session:
        return jsonify({"login_required": True}), 401
    user_id = session['user_id']
    profile = db.get_user_profile(user_id)
    foods = db.get_today_foods(user_id)
    notes = profile.get('notes', '') if profile else ''
    total_kcal = sum(f['kcal'] for f in foods)
    kalan_kcal = max(0, 2200 - int(total_kcal))
    ogun_tipi = request.json.get("meal_type", "akşam yemeği")
    prompt = (f"Bugün {int(total_kcal)} kcal yedi, kalan: {kalan_kcal} kcal\n"
              f"Öğün: {ogun_tipi}\nYasak malzeme: {notes}\n\n"
              f"2 kısa tarif öner (isim, kalori, malzeme, 3 adım).")
    reply = call_groq([{"role": "user", "content": prompt}],
                      "Türkçe pratik tarif öneren diyetisyensin.", max_tokens=1000)
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
        msg = f"Hedefe ulaştın! {kilo} kg"
    elif diff > 0:
        msg = f"{kilo} kg kaydedildi. Hedefe {diff} kg kaldı!"
    else:
        msg = f"{kilo} kg kaydedildi. Hedefe {abs(diff)} kg geçtin!"
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
        return jsonify({"error": "Geçersiz değer"}), 400
    if boy_cm <= 0 or kilo <= 0:
        return jsonify({"error": "Boy ve kilo sıfırdan büyük olmalı"}), 400
    bmi = round(kilo / (boy_cm / 100) ** 2, 1)
    if bmi < 18.5:
        kategori = "Zayıf"
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
SADECE geçerli JSON döndür, başka hiçbir şey yazma.
JSON FORMATI:
{"name":"yemek adı","kcal_per_100g":sayı,"portion":"porsiyon miktarı","portion_kcal":sayı,"protein_per_100g":sayı,"carb_per_100g":sayı,"fat_per_100g":sayı}"""
    prompt = f'Bu yiyecek için kalori bilgisi ver: "{food_name}". SADECE JSON döndür:'
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
        return jsonify({"found": False, "message": "Yemek adı boş"})
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
            return jsonify({"found": False, "message": "Kalori hesaplanamadı."})
        if 'user_id' in session:
            food_id = db.add_food_log(session['user_id'], name, display_kcal)
        return jsonify({
            "found": True, "id": food_id, "name": name,
            "kcal_per_100g": kcal_100, "portion": portion,
            "portion_kcal": display_kcal, "protein": protein,
            "carb": carb, "fat": fat, "source": "ai",
            "message": f"{name}: ~{display_kcal} kcal ({portion})"
        })
    return jsonify({"found": False, "message": f"'{food_name}' bulunamadı."})


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
        "profile":   db.get_user_profile(uid),
        "water":     db.get_today_water(uid),
        "foods":     db.get_today_foods(uid),
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
    return jsonify({"success": ok, "message": "Regl verisi kaydedildi!" if ok else "Hata oluştu"})


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


# ════════════════════════════════════════════════════════════════════════════
# BLOG ROUTE'LARI
# ════════════════════════════════════════════════════════════════════════════

def generate_blog_post():
    """AI ile günlük blog yazısı üret."""
    topic_mode = db.get_setting('blog_topic_mode', 'karma')

    topics_beslenme = [
        "Sabah kahvaltısının metabolizmaya etkisi",
        "Protein tüketimini artırmanın 5 kolay yolu",
        "Şeker bağımlılığını kırmak için pratik öneriler",
        "Akdeniz diyetinin sağlığa faydaları",
        "Aralıklı oruç: faydaları ve dikkat edilmesi gerekenler",
        "Fermente gıdalar ve bağırsak sağlığı",
        "Kış sebzelerinden besleyici tarifler",
        "Su içmenin doğru zamanlaması",
    ]
    topics_egzersiz = [
        "Evde yapılabilecek 20 dakikalık HIIT antrenmanı",
        "Masa başı çalışanlar için günlük hareket önerileri",
        "Egzersiz öncesi ve sonrası beslenme rehberi",
        "Esneklik egzersizlerinin faydaları",
        "Yürüyüşü daha etkili hale getirmenin yolları",
        "Kas iyileşmesi için uyku ve dinlenmenin önemi",
        "Kardiyovasküler sağlık için en iyi spor türleri",
        "Motivasyonu yüksek tutmanın psikolojik yöntemleri",
    ]

    if topic_mode == 'beslenme':
        topics = topics_beslenme
    elif topic_mode == 'egzersiz':
        topics = topics_egzersiz
    else:
        topics = topics_beslenme + topics_egzersiz

    import random
    topic = random.choice(topics)

    category_map = {t: 'beslenme' for t in topics_beslenme}
    category_map.update({t: 'egzersiz' for t in topics_egzersiz})
    category = category_map.get(topic, 'genel')

    emoji_map = {'beslenme': '🥗', 'egzersiz': '💪', 'genel': '🌿'}
    emoji = emoji_map.get(category, '🌿')

    system = """Sen FitLife AI için Türkçe blog yazıları yazan sağlıklı yaşam uzmanısın.
Verilen konuda 400-500 kelimelik, bilgilendirici ve motive edici bir blog yazısı yaz.
SADECE JSON döndür:
{"title":"yazı başlığı","content":"tam yazı içeriği (paragraflar \\n\\n ile ayrılmış)","reading_time":dakika_sayısı}"""

    prompt = f"Konu: {topic}\nBu konuda blog yazısı yaz."
    raw = call_groq([{"role": "user", "content": prompt}],
                    system, max_tokens=1000)

    raw = raw.strip()
    code_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
    if code_match:
        raw = code_match.group(1)
    json_match = re.search(r'\{.*\}', raw, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            return {
                "title":        data.get("title", topic),
                "content":      data.get("content", raw),
                "category":     category,
                "emoji":        emoji,
                "reading_time": int(data.get("reading_time", 3))
            }
        except:
            pass

    return {
        "title":        topic,
        "content":      raw,
        "category":     category,
        "emoji":        emoji,
        "reading_time": 3
    }


@app.route('/blog', methods=['GET'])
def blog_listesi():
    posts = db.get_blog_posts(limit=10)
    return jsonify({"success": True, "posts": posts})


@app.route('/blog/bugun', methods=['GET'])
def blog_bugun():
    post = db.get_today_blog_post()
    if not post:
        # Eğer otomatik yazı açıksa ve bugün yazı yoksa üret
        if db.get_setting('blog_auto_enabled') == 'true':
            result = generate_blog_post()
            ok, post_id = db.create_blog_post(
                title=result['title'],
                content=result['content'],
                category=result['category'],
                emoji=result['emoji'],
                reading_time=result['reading_time']
            )
            if ok:
                post = db.get_blog_post_by_id(post_id)
    if post:
        # datetime'ı string'e çevir (JSON serileştirme için)
        if isinstance(post.get('published_at'), datetime):
            post['published_at'] = post['published_at'].strftime('%d %B %Y')
        return jsonify({"success": True, "post": post})
    return jsonify({"success": False, "message": "Bugün için blog yazısı bulunamadı."})


@app.route('/blog/<int:post_id>', methods=['GET'])
def blog_detay(post_id):
    post = db.get_blog_post_by_id(post_id)
    if not post:
        return jsonify({"success": False, "message": "Yazı bulunamadı."}), 404
    if isinstance(post.get('published_at'), datetime):
        post['published_at'] = post['published_at'].strftime('%d %B %Y')
    return jsonify({"success": True, "post": post})


# ════════════════════════════════════════════════════════════════════════════
# ADMİN PANEL ROUTE'LARI
# ════════════════════════════════════════════════════════════════════════════

def admin_required(f):
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('admin_panel'))
        return f(*args, **kwargs)
    return decorated


@app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    admin_password = os.environ.get("ADMIN_PASSWORD", "fitlife-admin-2026")
    if request.method == 'POST':
        pw = request.form.get('pw')
        if pw == admin_password:
            session['admin'] = True
            return redirect(url_for('admin_panel'))
        else:
            return render_template('admin.html', error="Şifre hatalı!", logged_in=False)
    if not session.get('admin'):
        return render_template('admin.html', logged_in=False)
    # İstatistikler
    stats = {
        "user_count":    db.get_user_count(),
        "active_today":  db.get_today_active_users(),
        "total_messages": db.get_total_messages(),
        "blog_count":    db.get_blog_count(),
    }
    users = db.get_all_users()
    settings = db.get_all_settings()
    posts = db.get_blog_posts(limit=20)
    # datetime'ları string'e çevir
    for p in posts:
        if isinstance(p.get('published_at'), datetime):
            p['published_at'] = p['published_at'].strftime('%d.%m.%Y')
    return render_template('admin.html', logged_in=True,
                           stats=stats, users=users,
                           settings=settings, posts=posts)


@app.route('/admin/ayarlar-kaydet', methods=['POST'])
@admin_required
def admin_ayarlar_kaydet():
    data = request.json
    allowed_keys = [
        'groq_api_key', 'usda_api_key', 'groq_model', 'max_tokens',
        'daily_calorie_goal', 'daily_water_goal',
        'blog_auto_enabled', 'blog_topic_mode',
        'site_title', 'maintenance_mode'
    ]
    filtered = {k: v for k, v in data.items() if k in allowed_keys}
    ok = db.bulk_update_settings(filtered)
    return jsonify({"success": ok, "message": "Ayarlar kaydedildi!" if ok else "Hata oluştu."})


@app.route('/admin/kullanici-sil', methods=['POST'])
@admin_required
def admin_kullanici_sil():
    user_id = request.json.get('user_id')
    if not user_id:
        return jsonify({"success": False, "message": "ID eksik"}), 400
    ok, msg = db.delete_user(int(user_id))
    return jsonify({"success": ok, "message": msg})


@app.route('/admin/blog-olustur', methods=['POST'])
@admin_required
def admin_blog_olustur():
    data = request.json or {}
    # Manuel yazı mı yoksa AI ile mi?
    if data.get('manual'):
        title = data.get('title', '').strip()
        content = data.get('content', '').strip()
        if not title or not content:
            return jsonify({"success": False, "message": "Başlık ve içerik gerekli."}), 400
        category = data.get('category', 'genel')
        emoji = data.get('emoji', '🌿')
        reading_time = int(data.get('reading_time', 3))
    else:
        # AI ile üret
        result = generate_blog_post()
        title = result['title']
        content = result['content']
        category = result['category']
        emoji = result['emoji']
        reading_time = result['reading_time']

    ok, post_id = db.create_blog_post(
        title, content, category, emoji, reading_time)
    return jsonify({"success": ok, "message": "Blog yazısı oluşturuldu!" if ok else str(post_id)})


@app.route('/admin/blog-sil', methods=['POST'])
@admin_required
def admin_blog_sil():
    post_id = request.json.get('post_id')
    if not post_id:
        return jsonify({"success": False, "message": "ID eksik"}), 400
    db.delete_blog_post(int(post_id))
    return jsonify({"success": True, "message": "Yazı silindi."})


@app.route('/admin/istatistik', methods=['GET'])
@admin_required
def admin_istatistik():
    return jsonify({
        "user_count":     db.get_user_count(),
        "active_today":   db.get_today_active_users(),
        "total_messages": db.get_total_messages(),
        "blog_count":     db.get_blog_count(),
    })


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('admin_panel'))


if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
