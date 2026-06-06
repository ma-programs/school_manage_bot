# in the name of god
import sqlite3
import json
import time
from threading import Lock
from typing import Dict, Any, Optional, List, Tuple

DB_FILE = "teachers_bot.db"
db_lock = Lock()

def _connect():
    conn = sqlite3.connect(DB_FILE, timeout=30, detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
    except Exception:
        pass
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
    except Exception:
        pass
    return conn

def init():
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                telegram_id INTEGER,
                role TEXT DEFAULT 'teacher'
            )
            """)
            c.execute("PRAGMA table_info(users)")
            cols = [r[1] for r in c.fetchall()]
            if "role" not in cols:
                try:
                    c.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'teacher'")
                except Exception:
                    pass

            c.execute("""
            CREATE TABLE IF NOT EXISTS schools (
                school_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                owner TEXT,
                created INTEGER,
                password TEXT,
                meta TEXT,
                FOREIGN KEY(owner) REFERENCES users(username) ON DELETE SET NULL
            )
            """)
            c.execute("""
            CREATE TABLE IF NOT EXISTS school_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                school_id TEXT NOT NULL,
                username TEXT NOT NULL,
                role TEXT NOT NULL,
                joined INTEGER,
                FOREIGN KEY(school_id) REFERENCES schools(school_id) ON DELETE CASCADE,
                FOREIGN KEY(username) REFERENCES users(username) ON DELETE CASCADE
            )
            """)
            c.execute("""
            CREATE TABLE IF NOT EXISTS students (
                sid TEXT PRIMARY KEY,
                created_by TEXT,
                school_id TEXT,
                name TEXT NOT NULL,
                password TEXT NOT NULL,
                student_code TEXT,
                claimed_by INTEGER,
                claimed_at INTEGER,
                pn TEXT,
                scores TEXT,
                FOREIGN KEY(created_by) REFERENCES users(username) ON DELETE SET NULL,
                FOREIGN KEY(school_id) REFERENCES schools(school_id) ON DELETE SET NULL
            )
            """)
            c.execute("""
            CREATE TABLE IF NOT EXISTS classes (
                class_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                school_id TEXT,
                created_by TEXT,
                created INTEGER,
                password TEXT,
                FOREIGN KEY(school_id) REFERENCES schools(school_id) ON DELETE SET NULL,
                FOREIGN KEY(created_by) REFERENCES users(username) ON DELETE SET NULL
            )
            """)
            c.execute("""
            CREATE TABLE IF NOT EXISTS class_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                class_id TEXT NOT NULL,
                sid TEXT NOT NULL,
                added_by TEXT,
                joined INTEGER,
                FOREIGN KEY(class_id) REFERENCES classes(class_id) ON DELETE CASCADE,
                FOREIGN KEY(sid) REFERENCES students(sid) ON DELETE CASCADE
            )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_users_telegram ON users(telegram_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_schools_owner ON schools(owner)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_members_school ON school_members(school_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_members_username ON school_members(username)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_students_school ON students(school_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_students_created_by ON students(created_by)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_students_student_code ON students(student_code)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_classes_school ON classes(school_id)")
            conn.commit()
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_school_members_school_user ON school_members(school_id, username)")
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_class_members_class_sid ON class_members(class_id, sid)")
            conn.commit()
        finally:
            conn.close()

# small helper
def user_exists(username: str) -> bool:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("SELECT 1 FROM users WHERE username = ?", (username,))
            return bool(c.fetchone())
        finally:
            conn.close()

def load_users() -> Dict[str, Dict[str, Any]]:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("SELECT username, password, telegram_id, role FROM users")
            rows = c.fetchall()
            res: Dict[str, Dict[str, Any]] = {}
            for username, password, telegram_id, role in rows:
                res[username] = {"password": password, "telegram_id": telegram_id, "role": role or "teacher"}
            return res
        finally:
            conn.close()

def save_users(users: Dict[str, Dict[str, Any]]):
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            for username, u in users.items():
                tid = u.get("telegram_id")
                role = u.get("role") or "teacher"
                c.execute("INSERT OR REPLACE INTO users (username, password, telegram_id, role) VALUES (?, ?, ?, ?)", (username, u["password"], tid, role))
            conn.commit()
        finally:
            conn.close()

def get_user_by_telegram(telegram_id: int) -> Optional[str]:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("SELECT username FROM users WHERE telegram_id = ?", (telegram_id,))
            row = c.fetchone()
            return row[0] if row else None
        finally:
            conn.close()

def bind_telegram_to_user(username: str, telegram_id: int):
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("UPDATE users SET telegram_id = ? WHERE username = ?", (telegram_id, username))
            conn.commit()
        finally:
            conn.close()

def create_user(username: str, password: str, telegram_id: Optional[int] = None, role: str = "teacher") -> bool:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("SELECT 1 FROM users WHERE username = ?", (username,))
            if c.fetchone():
                return False
            c.execute("INSERT INTO users (username, password, telegram_id, role) VALUES (?, ?, ?, ?)", (username, password, telegram_id, role))
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

def get_user_role(username: str) -> Optional[str]:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("SELECT role FROM users WHERE username = ?", (username,))
            row = c.fetchone()
            return row[0] if row else None
        finally:
            conn.close()

def create_school(owner: str, name: str, password: Optional[str] = None, meta: Optional[Dict[str, Any]] = None) -> Optional[str]:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("SELECT 1 FROM users WHERE username = ?", (owner,))
            if not c.fetchone():
                return None
            school_id = "SCH_" + (hex(int(time.time() * 1000))[2:])
            created = int(time.time())
            meta_json = json.dumps(meta or {}, ensure_ascii=False)
            try:
                c.execute("INSERT INTO schools (school_id, name, owner, created, password, meta) VALUES (?, ?, ?, ?, ?, ?)",
                          (school_id, name, owner, created, password, meta_json))
                c.execute("INSERT INTO school_members (school_id, username, role, joined) VALUES (?, ?, ?, ?)",
                          (school_id, owner, "owner", created))
                conn.commit()
                return school_id
            except Exception:
                conn.rollback()
                raise
        finally:
            conn.close()

def delete_school(school_id: str) -> bool:
    """
    حذف آموزشگاه — اعضا (school_members) با ON DELETE CASCADE پاک می‌شوند.
    کلاس‌ها (classes) به دلیل ON DELETE SET NULL، school_id آنها NULL خواهد شد.
    """
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            try:
                c.execute("DELETE FROM schools WHERE school_id = ?", (school_id,))
                changed = c.rowcount
                conn.commit()
                return changed > 0
            except Exception:
                conn.rollback()
                raise
        finally:
            conn.close()

def get_school(school_id: str) -> Optional[Dict[str, Any]]:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("SELECT school_id, name, owner, created, password, meta FROM schools WHERE school_id = ?", (school_id,))
            row = c.fetchone()
            if not row:
                return None
            try:
                meta = json.loads(row[5] or "{}")
            except Exception:
                meta = {}
            return {"school_id": row[0], "name": row[1], "owner": row[2], "created": row[3], "password": row[4], "meta": meta}
        finally:
            conn.close()

def list_schools_for_owner(owner: str) -> List[Dict[str, Any]]:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("SELECT school_id, name, created FROM schools WHERE owner = ?", (owner,))
            return [{"school_id": r[0], "name": r[1], "created": r[2]} for r in c.fetchall()]
        finally:
            conn.close()

def list_schools_for_member(username: str) -> List[Dict[str, Any]]:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("SELECT s.school_id, s.name, sm.role FROM schools s JOIN school_members sm ON s.school_id = sm.school_id WHERE sm.username = ?", (username,))
            return [{"school_id": r[0], "name": r[1], "role": r[2]} for r in c.fetchall()]
        finally:
            conn.close()

def add_member_to_school(school_id: str, username: str, role: str = "teacher") -> bool:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("SELECT 1 FROM schools WHERE school_id = ?", (school_id,))
            if not c.fetchone():
                return False
            c.execute("SELECT 1 FROM users WHERE username = ?", (username,))
            if not c.fetchone():
                return False
            c.execute("SELECT 1 FROM school_members WHERE school_id = ? AND username = ?", (school_id, username))
            if c.fetchone():
                return False
            joined = int(time.time())
            try:
                c.execute("INSERT INTO school_members (school_id, username, role, joined) VALUES (?, ?, ?, ?)", (school_id, username, role, joined))
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                raise
        finally:
            conn.close()

def remove_member_from_school(school_id: str, username: str) -> bool:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            try:
                c.execute("DELETE FROM school_members WHERE school_id = ? AND username = ?", (school_id, username))
                changed = c.rowcount
                conn.commit()
                return changed > 0
            except Exception:
                conn.rollback()
                raise
        finally:
            conn.close()

def get_members_of_school(school_id: str) -> List[Dict[str, Any]]:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("SELECT username, role, joined FROM school_members WHERE school_id = ?", (school_id,))
            return [{"username": r[0], "role": r[1], "joined": r[2]} for r in c.fetchall()]
        finally:
            conn.close()

def is_user_member_of_school(username: str, school_id: str, roles: Optional[List[str]] = None) -> bool:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            if roles:
                placeholders = ",".join("?" for _ in roles)
                q = f"SELECT 1 FROM school_members WHERE school_id = ? AND username = ? AND role IN ({placeholders})"
                c.execute(q, (school_id, username, *roles))
            else:
                c.execute("SELECT 1 FROM school_members WHERE school_id = ? AND username = ?", (school_id, username))
            return bool(c.fetchone())
        finally:
            conn.close()

def _gen_student_code() -> str:
    import secrets, string
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(6))

def create_student(created_by: str, school_id: Optional[str], name: str, sid: str, password: str) -> Tuple[bool, Optional[str]]:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("SELECT 1 FROM students WHERE sid = ?", (sid,))
            if c.fetchone():
                return False, None
            c.execute("SELECT 1 FROM students WHERE LOWER(name) = LOWER(?)", (name.strip(),))
            if c.fetchone():
                return False, None
            if school_id:
                c.execute("SELECT 1 FROM schools WHERE school_id = ?", (school_id,))
                if not c.fetchone():
                    school_id = None
            code = _gen_student_code()
            created = int(time.time())
            pn_json = json.dumps([], ensure_ascii=False)
            scores_json = json.dumps([], ensure_ascii=False)
            try:
                c.execute("INSERT INTO students (sid, created_by, school_id, name, password, student_code, pn, scores) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                          (sid, created_by, school_id, name.strip(), password, code, pn_json, scores_json))
                conn.commit()
                return True, code
            except Exception:
                conn.rollback()
                raise
        finally:
            conn.close()

def get_student_by_sid(sid: str) -> Optional[Dict[str, Any]]:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("SELECT sid, created_by, school_id, name, student_code, claimed_by, claimed_at, pn, scores FROM students WHERE sid = ?", (sid,))
            row = c.fetchone()
            if not row:
                return None
            try:
                pn = json.loads(row[7] or "[]")
            except Exception:
                pn = []
            try:
                scores = json.loads(row[8] or "[]")
            except Exception:
                scores = []
            return {"sid": row[0], "created_by": row[1], "school_id": row[2], "name": row[3], "student_code": row[4], "claimed_by": row[5], "claimed_at": row[6], "pn": pn, "scores": scores}
        finally:
            conn.close()

def get_student_password(sid: str) -> Optional[str]:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("SELECT password FROM students WHERE sid = ?", (sid,))
            row = c.fetchone()
            return row[0] if row else None
        finally:
            conn.close()

def list_students_for_teacher(username: str) -> List[Dict[str, Any]]:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("SELECT sid, name, school_id, claimed_by FROM students WHERE created_by = ?", (username,))
            return [{"sid": r[0], "name": r[1], "school_id": r[2], "claimed_by": r[3]} for r in c.fetchall()]
        finally:
            conn.close()

def list_students_in_school(school_id: str) -> List[Dict[str, Any]]:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("SELECT sid, name, created_by FROM students WHERE school_id = ?", (school_id,))
            return [{"sid": r[0], "name": r[1], "created_by": r[2]} for r in c.fetchall()]
        finally:
            conn.close()

def assign_student_to_school(sid: str, school_id: str) -> bool:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("SELECT 1 FROM students WHERE sid = ?", (sid,))
            if not c.fetchone():
                return False
            c.execute("SELECT 1 FROM schools WHERE school_id = ?", (school_id,))
            if not c.fetchone():
                return False
            try:
                c.execute("UPDATE students SET school_id = ? WHERE sid = ?", (school_id, sid))
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                raise
        finally:
            conn.close()

def claim_student_by_code(sid: str, code: str, telegram_id: int) -> bool:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("SELECT student_code, claimed_by FROM students WHERE sid = ?", (sid,))
            row = c.fetchone()
            if not row:
                return False
            real_code, claimed_by = row
            if claimed_by:
                return False
            if (real_code or "").upper() != code.upper():
                return False
            ts = int(time.time())
            try:
                c.execute("UPDATE students SET claimed_by = ?, claimed_at = ? WHERE sid = ?", (telegram_id, ts, sid))
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                raise
        finally:
            conn.close()

def reset_student_code(sid: str) -> Optional[str]:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("SELECT 1 FROM students WHERE sid = ?", (sid,))
            if not c.fetchone():
                return None
            new_code = _gen_student_code()
            try:
                c.execute("UPDATE students SET student_code = ?, claimed_by = NULL, claimed_at = NULL WHERE sid = ?", (new_code, sid))
                conn.commit()
                return new_code
            except Exception:
                conn.rollback()
                raise
        finally:
            conn.close()

def add_score_to_student(sid: str, subject: str, score: float, term: str, created_by: str):
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("SELECT scores FROM students WHERE sid = ?", (sid,))
            row = c.fetchone()
            scores = json.loads(row[0] or "[]") if row and row[0] else []
            scores.append({"subject": subject, "score": score, "term": term, "timestamp": int(time.time()), "created_by": created_by})
            try:
                c.execute("UPDATE students SET scores = ? WHERE sid = ?", (json.dumps(scores, ensure_ascii=False), sid))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        finally:
            conn.close()

def add_pn_to_student(sid: str, pn_type: str, reason: str, created_by: str):
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("SELECT pn FROM students WHERE sid = ?", (sid,))
            row = c.fetchone()
            pn_list = json.loads(row[0] or "[]") if row and row[0] else []
            pn_list.append({"type": pn_type, "reason": reason, "timestamp": int(time.time()), "created_by": created_by})
            try:
                c.execute("UPDATE students SET pn = ? WHERE sid = ?", (json.dumps(pn_list, ensure_ascii=False), sid))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        finally:
            conn.close()

def delete_student(sid: str) -> bool:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            try:
                c.execute("DELETE FROM students WHERE sid = ?", (sid,))
                changed = c.rowcount
                conn.commit()
                return changed > 0
            except Exception:
                conn.rollback()
                raise
        finally:
            conn.close()

def create_class(created_by: str, name: str, school_id: Optional[str] = None, password: Optional[str] = None) -> Optional[str]:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            if school_id:
                c.execute("SELECT 1 FROM schools WHERE school_id = ?", (school_id,))
                if not c.fetchone():
                    return None
            class_id = "CLS_" + (hex(int(time.time() * 1000))[2:])
            created = int(time.time())
            try:
                c.execute("INSERT INTO classes (class_id, name, school_id, created_by, created, password) VALUES (?, ?, ?, ?, ?, ?)",
                          (class_id, name, school_id, created_by, created, password))
                conn.commit()
                return class_id
            except Exception:
                conn.rollback()
                raise
        finally:
            conn.close()

def create_class_with_id(created_by: str, school_id: Optional[str], name: str, class_id: str, password: Optional[str] = None) -> bool:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("SELECT 1 FROM classes WHERE class_id = ?", (class_id,))
            if c.fetchone():
                return False
            created = int(time.time())
            try:
                c.execute("INSERT INTO classes (class_id, name, school_id, created_by, created, password) VALUES (?, ?, ?, ?, ?, ?)", (class_id, name, school_id, created_by, created, password))
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                raise
        finally:
            conn.close()

def list_classes_for_owner(owner: str) -> List[Dict[str, Any]]:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("SELECT class_id, name, school_id, created FROM classes WHERE created_by = ?", (owner,))
            return [{"class_id": r[0], "name": r[1], "school_id": r[2], "created": r[3]} for r in c.fetchall()]
        finally:
            conn.close()

def get_class(class_id: str) -> Optional[Dict[str, Any]]:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("SELECT class_id, name, school_id, created_by, created FROM classes WHERE class_id = ?", (class_id,))
            row = c.fetchone()
            if not row:
                return None
            return {"class_id": row[0], "name": row[1], "school_id": row[2], "created_by": row[3], "created": row[4]}
        finally:
            conn.close()

def add_member_to_class(class_id: str, sid: str, added_by: Optional[str] = None) -> bool:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("SELECT 1 FROM classes WHERE class_id = ?", (class_id,))
            if not c.fetchone():
                return False
            c.execute("SELECT 1 FROM students WHERE sid = ?", (sid,))
            if not c.fetchone():
                return False
            c.execute("SELECT 1 FROM class_members WHERE class_id = ? AND sid = ?", (class_id, sid))
            if c.fetchone():
                return False
            joined = int(time.time())
            try:
                c.execute("INSERT INTO class_members (class_id, sid, added_by, joined) VALUES (?, ?, ?, ?)", (class_id, sid, added_by, joined))
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                raise
        finally:
            conn.close()

def remove_member_from_class(class_id: str, sid: str) -> bool:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            try:
                c.execute("DELETE FROM class_members WHERE class_id = ? AND sid = ?", (class_id, sid))
                changed = c.rowcount
                conn.commit()
                return changed > 0
            except Exception:
                conn.rollback()
                raise
        finally:
            conn.close()

def list_members_of_class(class_id: str) -> List[Dict[str, Any]]:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("SELECT cm.sid, s.name, cm.added_by, cm.joined FROM class_members cm JOIN students s ON cm.sid = s.sid WHERE cm.class_id = ?", (class_id,))
            return [{"sid": r[0], "name": r[1], "added_by": r[2], "joined": r[3]} for r in c.fetchall()]
        finally:
            conn.close()

def get_class_member_sids(class_id: str) -> List[str]:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("SELECT sid FROM class_members WHERE class_id = ?", (class_id,))
            return [r[0] for r in c.fetchall()]
        finally:
            conn.close()

def is_student_in_class(class_id: str, sid: str) -> bool:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("SELECT 1 FROM class_members WHERE class_id = ? AND sid = ?", (class_id, sid))
            return bool(c.fetchone())
        finally:
            conn.close()

def delete_class(class_id: str) -> bool:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            try:
                c.execute("DELETE FROM classes WHERE class_id = ?", (class_id,))
                changed = c.rowcount
                conn.commit()
                return changed > 0
            except Exception:
                conn.rollback()
                raise
        finally:
            conn.close()

def count_students_by_teacher(teacher_username: str) -> int:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("SELECT COUNT(1) FROM students WHERE created_by = ?", (teacher_username,))
            row = c.fetchone()
            return int(row[0]) if row and row[0] is not None else 0
        finally:
            conn.close()

def count_schools_for_owner(owner: str) -> int:
    with db_lock:
        conn = _connect()
        try:
            c = conn.cursor()
            c.execute("SELECT COUNT(1) FROM schools WHERE owner = ?", (owner,))
            row = c.fetchone()
            return int(row[0]) if row and row[0] is not None else 0
        finally:
            conn.close()
