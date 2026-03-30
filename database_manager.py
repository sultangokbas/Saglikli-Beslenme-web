import sqlite3
from datetime import date
from werkzeug.security import generate_password_hash, check_password_hash


class DatabaseManager:
    def __init__(self, db_name="fitlife_pro.db"):
        self.db_name = db_name
        self.init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        return conn

    def today(self):
        return str(date.today())

    def init_db(self):
        with self.get_connection() as conn:
            c = conn.cursor()

            c.execute('''CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL
            )''')

            c.execute('''CREATE TABLE IF NOT EXISTS user_profiles (
                user_id        INTEGER PRIMARY KEY,
                first_name     TEXT    DEFAULT "",
                last_name      TEXT    DEFAULT "",
                age            INTEGER DEFAULT NULL,
                gender         TEXT    DEFAULT "",
                activity_level TEXT    DEFAULT "orta",
                current_weight REAL    DEFAULT 70,
                target_weight  REAL    DEFAULT 60,
                height_cm      REAL    DEFAULT 165,
                notes          TEXT    DEFAULT "",
                FOREIGN KEY (user_id) REFERENCES users(id)
            )''')

            # Mevcut DB'ye yeni kolonları güvenle ekle
            for col, defn in [
                ("first_name",     "TEXT DEFAULT ''"),
                ("last_name",      "TEXT DEFAULT ''"),
                ("gender",         "TEXT DEFAULT ''"),
                ("activity_level", "TEXT DEFAULT 'orta'"),
            ]:
                try:
                    c.execute(
                        f"ALTER TABLE user_profiles ADD COLUMN {col} {defn}")
                except Exception:
                    pass
            try:
                c.execute(
                    "ALTER TABLE user_profiles ADD COLUMN age INTEGER DEFAULT NULL")
            except Exception:
                pass

            c.execute('''CREATE TABLE IF NOT EXISTS chat_history (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER NOT NULL,
                role      TEXT    NOT NULL,
                content   TEXT    NOT NULL,
                day       TEXT    NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )''')

            c.execute('''CREATE TABLE IF NOT EXISTS weight_log (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER NOT NULL,
                weight    REAL    NOT NULL,
                day       TEXT    NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )''')

            c.execute('''CREATE TABLE IF NOT EXISTS food_log (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                day     TEXT    NOT NULL,
                name    TEXT    NOT NULL,
                kcal    REAL    DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )''')

            c.execute('''CREATE TABLE IF NOT EXISTS exercise_log (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                day     TEXT    NOT NULL,
                name    TEXT    NOT NULL,
                emoji   TEXT    DEFAULT "🏃",
                kcal    REAL    DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )''')

            c.execute('''CREATE TABLE IF NOT EXISTS water_log (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                day     TEXT    NOT NULL,
                count   INTEGER DEFAULT 0,
                UNIQUE(user_id, day),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )''')

            c.execute('''CREATE TABLE IF NOT EXISTS sleep_logs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                sleep_start TEXT,
                sleep_end   TEXT,
                quality     INTEGER,
                notes       TEXT,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )''')

            # Regl: kullanıcı başına tek satır (UNIQUE user_id)
            c.execute('''CREATE TABLE IF NOT EXISTS period_log (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id          INTEGER UNIQUE NOT NULL,
                last_period_date TEXT,
                cycle_length     INTEGER DEFAULT 28,
                period_duration  INTEGER DEFAULT 5,
                notes            TEXT    DEFAULT "",
                updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )''')

            conn.commit()
        print("🥑 FitLife Veritabanı hazır!")

    # ─── KULLANICI ───────────────────────────────────────────────────────────

    def register_user(self, username, email, password):
        try:
            with self.get_connection() as conn:
                c = conn.cursor()
                c.execute(
                    "INSERT INTO users (username, email, password_hash) VALUES (?,?,?)",
                    (username, email, generate_password_hash(password))
                )
                uid = c.lastrowid
                c.execute(
                    "INSERT INTO user_profiles (user_id) VALUES (?)", (uid,))
                conn.commit()
            return True, "Kayıt başarılı! 🥑"
        except sqlite3.IntegrityError as e:
            if "username" in str(e):
                return False, "Bu kullanıcı adı zaten alınmış. ❌"
            return False, "Bu e-posta zaten kayıtlı. ❌"
        except Exception as e:
            return False, f"Hata: {str(e)}"

    def login_user(self, username, password):
        with self.get_connection() as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE username=?", (username,)
            ).fetchone()
            if user and check_password_hash(user['password_hash'], password):
                return True, user['id']
            return False, "Kullanıcı adı veya şifre hatalı. ❌"

    # ─── PROFİL ──────────────────────────────────────────────────────────────

    def get_user_profile(self, user_id):
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM user_profiles WHERE user_id=?", (user_id,)
            ).fetchone()
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
                fields.append(f"{col}=?")
                values.append(val)
        if not fields:
            return False, "Güncellenecek alan yok."
        values.append(user_id)
        try:
            with self.get_connection() as conn:
                conn.execute(
                    f"UPDATE user_profiles SET {', '.join(fields)} WHERE user_id=?", values
                )
                conn.commit()
            return True, "Profil güncellendi! ✅"
        except Exception as e:
            return False, str(e)

    # ─── SOHBET GEÇMİŞİ ──────────────────────────────────────────────────────

    def save_chat_message(self, user_id, role, content):
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO chat_history (user_id, role, content, day) VALUES (?,?,?,?)",
                (user_id, role, content, self.today())
            )
            conn.commit()

    def get_chat_history(self, user_id, limit=12):
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT role, content FROM chat_history "
                "WHERE user_id=? AND day=? ORDER BY id DESC LIMIT ?",
                (user_id, self.today(), limit)
            ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def clear_chat_history(self, user_id):
        with self.get_connection() as conn:
            conn.execute(
                "DELETE FROM chat_history WHERE user_id=?", (user_id,))
            conn.commit()

    # ─── KİLO GEÇMİŞİ ────────────────────────────────────────────────────────

    def add_weight_log(self, user_id, weight):
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO weight_log (user_id, weight, day) VALUES (?,?,?)",
                (user_id, weight, self.today())
            )
            conn.commit()

    def get_weight_history(self, user_id, limit=30):
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT weight, day FROM weight_log WHERE user_id=? ORDER BY id DESC LIMIT ?",
                (user_id, limit)
            ).fetchall()
        return [dict(r) for r in rows]

    # ─── YEMEK LOGU ──────────────────────────────────────────────────────────

    def add_food_log(self, user_id, name, kcal):
        """Yemek ekler ve yeni satırın id'sini döndürür (frontend silme için kullanır)."""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO food_log (user_id, day, name, kcal) VALUES (?,?,?,?)",
                (user_id, self.today(), name, kcal)
            )
            conn.commit()
            return c.lastrowid

    def delete_food_log(self, user_id, food_id):
        """Sadece o kullanıcıya ait kaydı siler."""
        with self.get_connection() as conn:
            conn.execute(
                "DELETE FROM food_log WHERE id=? AND user_id=?",
                (food_id, user_id)
            )
            conn.commit()

    def get_today_foods(self, user_id):
        """id alanını da döndürür — frontend silme için gerekli."""
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT id, name, kcal FROM food_log WHERE user_id=? AND day=? ORDER BY id",
                (user_id, self.today())
            ).fetchall()
        return [dict(r) for r in rows]

    # ─── EGZERSİZ LOGU ───────────────────────────────────────────────────────

    def add_exercise_log(self, user_id, name, emoji, kcal):
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO exercise_log (user_id, day, name, emoji, kcal) VALUES (?,?,?,?,?)",
                (user_id, self.today(), name, emoji, kcal)
            )
            conn.commit()

    def get_today_exercises(self, user_id):
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT name, emoji, kcal FROM exercise_log WHERE user_id=? AND day=? ORDER BY id",
                (user_id, self.today())
            ).fetchall()
        return [dict(r) for r in rows]

    # ─── SU TAKİBİ ───────────────────────────────────────────────────────────

    def save_water(self, user_id, count):
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO water_log (user_id, day, count) VALUES (?,?,?) "
                "ON CONFLICT(user_id, day) DO UPDATE SET count=excluded.count",
                (user_id, self.today(), count)
            )
            conn.commit()

    def get_today_water(self, user_id):
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT count FROM water_log WHERE user_id=? AND day=?",
                (user_id, self.today())
            ).fetchone()
        return row["count"] if row else 0

    # ─── UYKU ────────────────────────────────────────────────────────────────

    def add_sleep_log(self, user_id, sleep_start, sleep_end, quality, notes=None):
        try:
            with self.get_connection() as conn:
                conn.execute(
                    "INSERT INTO sleep_logs (user_id, sleep_start, sleep_end, quality, notes) VALUES (?,?,?,?,?)",
                    (user_id, sleep_start, sleep_end, quality, notes)
                )
                conn.commit()
            return True
        except Exception:
            return False

    def get_latest_sleep_log(self, user_id):
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM sleep_logs WHERE user_id=? ORDER BY id DESC LIMIT 1",
                (user_id,)
            ).fetchone()
        return dict(row) if row else None

    # ─── REGL TAKİBİ ─────────────────────────────────────────────────────────

    def save_period_log(self, user_id, last_period_date,
                        cycle_length=28, period_duration=5, notes=""):
        """Kullanıcı başına tek satır — varsa günceller, yoksa ekler."""
        try:
            with self.get_connection() as conn:
                conn.execute(
                    """INSERT INTO period_log
                       (user_id, last_period_date, cycle_length, period_duration, notes, updated_at)
                       VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                       ON CONFLICT(user_id) DO UPDATE SET
                           last_period_date = excluded.last_period_date,
                           cycle_length     = excluded.cycle_length,
                           period_duration  = excluded.period_duration,
                           notes            = excluded.notes,
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
            row = conn.execute(
                "SELECT * FROM period_log WHERE user_id=?", (user_id,)
            ).fetchone()
        return dict(row) if row else None


if __name__ == "__main__":
    db = DatabaseManager()
    print("Tüm tablolar hazır!")
