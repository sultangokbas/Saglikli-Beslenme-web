import os
import psycopg2
import psycopg2.extras
from datetime import date
from werkzeug.security import generate_password_hash, check_password_hash

DATABASE_URL = os.environ.get("DATABASE_URL")


class DatabaseManager:
    def __init__(self):
        self.init_db()

    def get_connection(self):
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        return conn

    def today(self):
        return str(date.today())

    def init_db(self):
        with self.get_connection() as conn:
            c = conn.cursor()

            c.execute('''CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL
            )''')

            c.execute('''CREATE TABLE IF NOT EXISTS user_profiles (
                user_id        INTEGER PRIMARY KEY,
                first_name     TEXT    DEFAULT '',
                last_name      TEXT    DEFAULT '',
                age            INTEGER DEFAULT NULL,
                gender         TEXT    DEFAULT '',
                activity_level TEXT    DEFAULT 'orta',
                current_weight REAL    DEFAULT 70,
                target_weight  REAL    DEFAULT 60,
                height_cm      REAL    DEFAULT 165,
                notes          TEXT    DEFAULT '',
                FOREIGN KEY (user_id) REFERENCES users(id)
            )''')

            c.execute('''CREATE TABLE IF NOT EXISTS chat_history (
                id        SERIAL PRIMARY KEY,
                user_id   INTEGER NOT NULL,
                role      TEXT    NOT NULL,
                content   TEXT    NOT NULL,
                day       TEXT    NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )''')

            c.execute('''CREATE TABLE IF NOT EXISTS weight_log (
                id        SERIAL PRIMARY KEY,
                user_id   INTEGER NOT NULL,
                weight    REAL    NOT NULL,
                day       TEXT    NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )''')

            c.execute('''CREATE TABLE IF NOT EXISTS food_log (
                id      SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                day     TEXT    NOT NULL,
                name    TEXT    NOT NULL,
                kcal    REAL    DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )''')

            c.execute('''CREATE TABLE IF NOT EXISTS exercise_log (
                id      SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                day     TEXT    NOT NULL,
                name    TEXT    NOT NULL,
                emoji   TEXT    DEFAULT '🏃',
                kcal    REAL    DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )''')

            c.execute('''CREATE TABLE IF NOT EXISTS water_log (
                id      SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                day     TEXT    NOT NULL,
                count   INTEGER DEFAULT 0,
                UNIQUE(user_id, day),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )''')

            c.execute('''CREATE TABLE IF NOT EXISTS sleep_logs (
                id          SERIAL PRIMARY KEY,
                user_id     INTEGER NOT NULL,
                sleep_start TEXT,
                sleep_end   TEXT,
                quality     INTEGER,
                notes       TEXT,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )''')

            c.execute('''CREATE TABLE IF NOT EXISTS period_log (
                id               SERIAL PRIMARY KEY,
                user_id          INTEGER UNIQUE NOT NULL,
                last_period_date TEXT,
                cycle_length     INTEGER DEFAULT 28,
                period_duration  INTEGER DEFAULT 5,
                notes            TEXT    DEFAULT '',
                updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )''')

            # ─── AYARLAR TABLOSU ─────────────────────────────────────────────
            c.execute('''CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )''')

            # Varsayılan ayarlar (OpenRouter tabanlı)
            default_settings = [
                # OpenRouter
                ('openrouter_api_key', ''),
                ('primary_model',      'meta-llama/llama-3.3-70b-instruct:free'),
                ('fallback_model',     'mistralai/mistral-7b-instruct:free'),
                ('max_tokens',         '1500'),
                # Eski Groq anahtarı (geriye dönük uyumluluk için bırakıldı)
                ('groq_api_key',       ''),
                ('usda_api_key',       ''),
                # Hedefler
                ('daily_calorie_goal', '2200'),
                ('daily_water_goal',   '8'),
                # Blog
                ('blog_auto_enabled',  'true'),
                ('blog_topic_mode',    'karma'),
                # Site
                ('site_title',         'FitLife AI'),
                ('maintenance_mode',   'false'),
            ]
            for key, val in default_settings:
                c.execute(
                    "INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT(key) DO NOTHING",
                    (key, val)
                )

            # ─── BLOG TABLOSU ─────────────────────────────────────────────────
            c.execute('''CREATE TABLE IF NOT EXISTS blog_posts (
                id           SERIAL PRIMARY KEY,
                title        TEXT    NOT NULL,
                content      TEXT    NOT NULL,
                category     TEXT    DEFAULT 'genel',
                emoji        TEXT    DEFAULT '🥗',
                reading_time INTEGER DEFAULT 3,
                published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                publish_date TEXT    NOT NULL,
                is_active    BOOLEAN DEFAULT TRUE
            )''')

            conn.commit()
        print("🥑 FitLife PostgreSQL Veritabanı hazır!")

    # ─── KULLANICI ───────────────────────────────────────────────────────────

    def register_user(self, username, email, password):
        try:
            with self.get_connection() as conn:
                c = conn.cursor()
                c.execute(
                    "INSERT INTO users (username, email, password_hash) VALUES (%s,%s,%s) RETURNING id",
                    (username, email, generate_password_hash(password))
                )
                uid = c.fetchone()[0]
                c.execute(
                    "INSERT INTO user_profiles (user_id) VALUES (%s)", (uid,))
                conn.commit()
            return True, "Kayıt başarılı! 🥑"
        except psycopg2.errors.UniqueViolation as e:
            if "username" in str(e):
                return False, "Bu kullanıcı adı zaten alınmış. ❌"
            return False, "Bu e-posta zaten kayıtlı. ❌"
        except Exception as e:
            return False, f"Hata: {str(e)}"

    def login_user(self, username, password):
        with self.get_connection() as conn:
            c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            c.execute("SELECT * FROM users WHERE username=%s", (username,))
            user = c.fetchone()
            if user and check_password_hash(user['password_hash'], password):
                return True, user['id']
            return False, "Kullanıcı adı veya şifre hatalı. ❌"

    # ─── PROFİL ──────────────────────────────────────────────────────────────

    def get_user_profile(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            c.execute("SELECT * FROM user_profiles WHERE user_id=%s", (user_id,))
            row = c.fetchone()
            return dict(row) if row else None

    def update_user_profile(self, user_id, first_name=None, last_name=None,
                            age=None, gender=None, activity_level=None,
                            current_weight=None, target_weight=None,
                            height_cm=None, notes=None):
        fields, values = [], []
        mapping = [
            ("first_name",     first_name),
            ("last_name",      last_name),
            ("age",            age),
            ("gender",         gender),
            ("activity_level", activity_level),
            ("current_weight", current_weight),
            ("target_weight",  target_weight),
            ("height_cm",      height_cm),
            ("notes",          notes),
        ]
        for col, val in mapping:
            if val is not None:
                fields.append(f"{col}=%s")
                values.append(val)
        if not fields:
            return False, "Güncellenecek alan yok."
        values.append(user_id)
        try:
            with self.get_connection() as conn:
                c = conn.cursor()
                c.execute(
                    f"UPDATE user_profiles SET {', '.join(fields)} WHERE user_id=%s", values
                )
                conn.commit()
            return True, "Profil güncellendi! ✅"
        except Exception as e:
            return False, str(e)

    # ─── SOHBET GEÇMİŞİ ──────────────────────────────────────────────────────

    def save_chat_message(self, user_id, role, content):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO chat_history (user_id, role, content, day) VALUES (%s,%s,%s,%s)",
                (user_id, role, content, self.today())
            )
            conn.commit()

    def get_chat_history(self, user_id, limit=12):
        with self.get_connection() as conn:
            c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            c.execute(
                "SELECT role, content FROM chat_history "
                "WHERE user_id=%s AND day=%s ORDER BY id DESC LIMIT %s",
                (user_id, self.today(), limit)
            )
            rows = c.fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def clear_chat_history(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM chat_history WHERE user_id=%s", (user_id,))
            conn.commit()

    # ─── KİLO GEÇMİŞİ ────────────────────────────────────────────────────────

    def add_weight_log(self, user_id, weight):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO weight_log (user_id, weight, day) VALUES (%s,%s,%s)",
                (user_id, weight, self.today())
            )
            conn.commit()

    def get_weight_history(self, user_id, limit=30):
        with self.get_connection() as conn:
            c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            c.execute(
                "SELECT weight, day FROM weight_log WHERE user_id=%s ORDER BY id DESC LIMIT %s",
                (user_id, limit)
            )
            rows = c.fetchall()
        return [dict(r) for r in rows]

    # ─── YEMEK LOGU ──────────────────────────────────────────────────────────

    def add_food_log(self, user_id, name, kcal):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO food_log (user_id, day, name, kcal) VALUES (%s,%s,%s,%s) RETURNING id",
                (user_id, self.today(), name, kcal)
            )
            food_id = c.fetchone()[0]
            conn.commit()
            return food_id

    def delete_food_log(self, user_id, food_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute(
                "DELETE FROM food_log WHERE id=%s AND user_id=%s",
                (food_id, user_id)
            )
            conn.commit()

    def get_today_foods(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            c.execute(
                "SELECT id, name, kcal FROM food_log WHERE user_id=%s AND day=%s ORDER BY id",
                (user_id, self.today())
            )
            rows = c.fetchall()
        return [dict(r) for r in rows]

    # ─── EGZERSİZ LOGU ───────────────────────────────────────────────────────

    def add_exercise_log(self, user_id, name, emoji, kcal):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO exercise_log (user_id, day, name, emoji, kcal) VALUES (%s,%s,%s,%s,%s)",
                (user_id, self.today(), name, emoji, kcal)
            )
            conn.commit()

    def get_today_exercises(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            c.execute(
                "SELECT name, emoji, kcal FROM exercise_log WHERE user_id=%s AND day=%s ORDER BY id",
                (user_id, self.today())
            )
            rows = c.fetchall()
        return [dict(r) for r in rows]

    # ─── SU TAKİBİ ───────────────────────────────────────────────────────────

    def save_water(self, user_id, count):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO water_log (user_id, day, count) VALUES (%s,%s,%s) "
                "ON CONFLICT(user_id, day) DO UPDATE SET count=EXCLUDED.count",
                (user_id, self.today(), count)
            )
            conn.commit()

    def get_today_water(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT count FROM water_log WHERE user_id=%s AND day=%s",
                (user_id, self.today())
            )
            row = c.fetchone()
        return row[0] if row else 0

    # ─── UYKU ────────────────────────────────────────────────────────────────

    def add_sleep_log(self, user_id, sleep_start, sleep_end, quality, notes=None):
        try:
            with self.get_connection() as conn:
                c = conn.cursor()
                c.execute(
                    "INSERT INTO sleep_logs (user_id, sleep_start, sleep_end, quality, notes) VALUES (%s,%s,%s,%s,%s)",
                    (user_id, sleep_start, sleep_end, quality, notes)
                )
                conn.commit()
            return True
        except Exception:
            return False

    def get_latest_sleep_log(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            c.execute(
                "SELECT * FROM sleep_logs WHERE user_id=%s ORDER BY id DESC LIMIT 1",
                (user_id,)
            )
            row = c.fetchone()
        return dict(row) if row else None

    # ─── REGL TAKİBİ ─────────────────────────────────────────────────────────

    def save_period_log(self, user_id, last_period_date,
                        cycle_length=28, period_duration=5, notes=""):
        try:
            with self.get_connection() as conn:
                c = conn.cursor()
                c.execute(
                    """INSERT INTO period_log
                       (user_id, last_period_date, cycle_length,
                        period_duration, notes, updated_at)
                       VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                       ON CONFLICT(user_id) DO UPDATE SET
                           last_period_date = EXCLUDED.last_period_date,
                           cycle_length     = EXCLUDED.cycle_length,
                           period_duration  = EXCLUDED.period_duration,
                           notes            = EXCLUDED.notes,
                           updated_at       = CURRENT_TIMESTAMP""",
                    (user_id, last_period_date, cycle_length, period_duration, notes)
                )
                conn.commit()
            return True
        except Exception as e:
            print(f"Period log hatası: {e}")
            return False

    def get_latest_period_log(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            c.execute("SELECT * FROM period_log WHERE user_id=%s", (user_id,))
            row = c.fetchone()
        return dict(row) if row else None

    # ─── ADMİN ───────────────────────────────────────────────────────────────

    def get_all_users(self):
        with self.get_connection() as conn:
            c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            c.execute("SELECT id, username, email FROM users ORDER BY id DESC")
            rows = c.fetchall()
        return [dict(r) for r in rows]

    def get_user_count(self):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users")
            return c.fetchone()[0]

    def get_today_active_users(self):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT COUNT(DISTINCT user_id) FROM chat_history WHERE day=%s",
                (self.today(),)
            )
            return c.fetchone()[0]

    def get_total_messages(self):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM chat_history")
            return c.fetchone()[0]

    def delete_user(self, user_id):
        try:
            with self.get_connection() as conn:
                c = conn.cursor()
                for table in ['chat_history', 'food_log', 'exercise_log',
                              'water_log', 'weight_log', 'sleep_logs',
                              'period_log', 'user_profiles']:
                    c.execute(
                        f"DELETE FROM {table} WHERE user_id=%s", (user_id,))
                c.execute("DELETE FROM users WHERE id=%s", (user_id,))
                conn.commit()
            return True, "Kullanıcı silindi."
        except Exception as e:
            return False, str(e)

    # ─── AYARLAR ─────────────────────────────────────────────────────────────

    def get_setting(self, key, default=''):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT value FROM settings WHERE key=%s", (key,))
            row = c.fetchone()
        return row[0] if row else default

    def set_setting(self, key, value):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO settings (key, value) VALUES (%s, %s) "
                "ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value",
                (key, str(value))
            )
            conn.commit()

    def get_all_settings(self):
        with self.get_connection() as conn:
            c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            c.execute("SELECT key, value FROM settings ORDER BY key")
            rows = c.fetchall()
        return {r['key']: r['value'] for r in rows}

    def bulk_update_settings(self, settings_dict):
        try:
            with self.get_connection() as conn:
                c = conn.cursor()
                for key, value in settings_dict.items():
                    c.execute(
                        "INSERT INTO settings (key, value) VALUES (%s, %s) "
                        "ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value",
                        (key, str(value))
                    )
                conn.commit()
            return True
        except Exception as e:
            print(f"Settings güncelleme hatası: {e}")
            return False

    # ─── BLOG ────────────────────────────────────────────────────────────────

    def create_blog_post(self, title, content, category='genel', emoji='🥗', reading_time=3):
        try:
            with self.get_connection() as conn:
                c = conn.cursor()
                c.execute(
                    """INSERT INTO blog_posts
                       (title, content, category, emoji, reading_time, publish_date)
                       VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                    (title, content, category, emoji, reading_time, self.today())
                )
                post_id = c.fetchone()[0]
                conn.commit()
            return True, post_id
        except Exception as e:
            return False, str(e)

    def get_today_blog_post(self):
        with self.get_connection() as conn:
            c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            c.execute(
                "SELECT * FROM blog_posts WHERE publish_date=%s AND is_active=TRUE ORDER BY id DESC LIMIT 1",
                (self.today(),)
            )
            row = c.fetchone()
        return dict(row) if row else None

    def get_blog_posts(self, limit=10, offset=0):
        with self.get_connection() as conn:
            c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            c.execute(
                "SELECT * FROM blog_posts WHERE is_active=TRUE ORDER BY published_at DESC LIMIT %s OFFSET %s",
                (limit, offset)
            )
            rows = c.fetchall()
        return [dict(r) for r in rows]

    def get_blog_post_by_id(self, post_id):
        with self.get_connection() as conn:
            c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            c.execute("SELECT * FROM blog_posts WHERE id=%s", (post_id,))
            row = c.fetchone()
        return dict(row) if row else None

    def delete_blog_post(self, post_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute(
                "UPDATE blog_posts SET is_active=FALSE WHERE id=%s", (post_id,))
            conn.commit()

    def get_blog_count(self):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM blog_posts WHERE is_active=TRUE")
            return c.fetchone()[0]

    def blog_exists_today(self):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT COUNT(*) FROM blog_posts WHERE publish_date=%s AND is_active=TRUE",
                (self.today(),)
            )
            return c.fetchone()[0] > 0


if __name__ == "__main__":
    db = DatabaseManager()
    print("Tüm tablolar hazır!")
