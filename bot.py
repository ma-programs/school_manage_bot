#in the name of god
import base64
import bcrypt
import logging
import time
from threading import Lock
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from config import BOT_TOKEN
from datetime import datetime
import db
import requests
import certifi
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import telebot.apihelper as apihelper
import os
import unicodedata
import re

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing")


session = requests.Session()
retries = Retry(total=5, connect=5, read=5, backoff_factor=0.5,
                status_forcelist=[429, 500, 502, 503, 504], raise_on_status=False)
adapter = HTTPAdapter(max_retries=retries)
session.mount("https://", adapter)
session.verify = certifi.where()
apihelper._get_req_session = lambda: session
proxy = os.getenv("TELEGRAM_PROXY")
if proxy:
    session.proxies.update({"http": proxy, "https": proxy})


db.init()
session_lock = Lock()


class SessionManager:
    def __init__(self):
        self.sessions = {}

    def set(self, chat_id, key, value):
        with session_lock:
            self.sessions.setdefault(str(chat_id), {})[key] = value

    def get(self, chat_id, key):
        with session_lock:
            return self.sessions.get(str(chat_id), {}).get(key)

    def pop(self, chat_id, key, default=None):
        with session_lock:
            s = self.sessions.get(str(chat_id), {})
            return s.pop(key, default)

    def clear_all(self, chat_id):
        with session_lock:
            self.sessions.pop(str(chat_id), None)

    def clear_interactive(self, chat_id, preserve_keys=None):
        if preserve_keys is None:
            preserve_keys = {"username"}
        with session_lock:
            s = self.sessions.get(str(chat_id), {})
            if not s:
                return
            preserved = {k: s[k] for k in list(s.keys()) if k in preserve_keys and k in s}
            if preserved:
                self.sessions[str(chat_id)] = preserved
            else:
                self.sessions.pop(str(chat_id), None)


sessions = SessionManager()
bot = telebot.TeleBot(BOT_TOKEN)

MAX_STUDENTS_PER_TEACHER = 300
MAX_SCHOOLS_PER_OWNER = 20


def normalize_text(s: str) -> str:
    if s is None:
        return ""
    s = unicodedata.normalize("NFC", s)
    for ch in ("\u200c", "\u200d", "\ufeff"):
        s = s.replace(ch, "")
    s = " ".join(s.split())
    return s.strip()


def format_ts(ts):
    try:
        return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "-"


# Labels (Persian)
LABEL_REGISTER = "📝 ثبت‌نام"
LABEL_LOGIN = "🔐 ورود"
LABEL_HELP = "📘 راهنما"
LABEL_CREATE_SCHOOL = "🏫 ثبت آموزشگاه"
LABEL_JOIN_SCHOOL = "🔗 پیوستن به آموزشگاه"
LABEL_MY_SCHOOLS = "📂 آموزشگاه‌های من"
LABEL_ADD_STUDENT = "➕ دانش‌آموز جدید"
LABEL_CHOOSE_STUDENT = "👤 انتخاب دانش‌آموز"
LABEL_LIST_STUDENTS = "📚 دانش‌آموزهای من"
LABEL_STUDENT_LOGIN = "🎫 ورود دانش‌آموز"
LABEL_VIEW_MY_SCORES = "📥 دیدن نمرات من"
LABEL_PN = "👍👎 امتیاز"
LABEL_ADD_SCORE = "📊 ثبت نمره"
LABEL_DELETE_STUDENT = "🗑️ حذف دانش‌آموز"
LABEL_LOGOUT = "🚪 خروج"
LABEL_CANCEL = "انصراف"
LABEL_BACK = "🔙 بازگشت"
LABEL_MAIN = "🏠 منوی اصلی"
LABEL_CONFIRM_DELETE = "بله حذف کن"
BUTTON_PLUS = "➕ مثبت"
BUTTON_MINUS = "➖ منفی"
BUTTON_ADD_TO_SCHOOL = "➕ افزودن به آموزشگاه"
BUTTON_REMOVE_FROM_SCHOOL = "حذف از آموزشگاه"
LABEL_ADD_EXISTING_STUDENT = "➕ افزودن از دانش‌آموزان من"
LABEL_ADD_TEACHER_BY_USERNAME = "➕ افزودن معلم با نام‌کاربری"
LABEL_ADD_CLASS = "➕ افزودن کلاس"
LABEL_REMOVE_CLASS = "🗑️ حذف کلاس"
LABEL_MY_CLASSES = "📂 کلاس‌های من"
LABEL_CREATE_CLASS = LABEL_ADD_CLASS
LABEL_CHOOSE_CLASS = "🏷️ انتخاب کلاس"
LABEL_ADD_STUDENT_TO_CLASS = "➕ افزودن دانش‌آموز به کلاس"
LABEL_REMOVE_STUDENT_FROM_CLASS = "🗑️ حذف دانش‌آموز از کلاس"
LABEL_DELETE_SCHOOL = "🗑️ حذف آموزشگاه"

ROLE_TEACHER_LABEL = "👨‍🏫 معلم"
ROLE_STUDENT_LABEL = "👦 دانش‌آموز"
ROLE_OWNER_LABEL = "👤 مدیر"

ALL_BUTTON_LABELS = {
    LABEL_REGISTER, LABEL_LOGIN, LABEL_HELP, LABEL_CREATE_SCHOOL, LABEL_JOIN_SCHOOL, LABEL_MY_SCHOOLS,
    LABEL_ADD_STUDENT, LABEL_CHOOSE_STUDENT, LABEL_LIST_STUDENTS, LABEL_STUDENT_LOGIN,
    LABEL_PN, LABEL_ADD_SCORE, LABEL_DELETE_STUDENT, LABEL_LOGOUT, LABEL_CANCEL,
    LABEL_BACK, LABEL_MAIN, LABEL_CONFIRM_DELETE, LABEL_DELETE_SCHOOL,
    BUTTON_PLUS, BUTTON_MINUS, BUTTON_ADD_TO_SCHOOL, BUTTON_REMOVE_FROM_SCHOOL,
    ROLE_TEACHER_LABEL, ROLE_STUDENT_LABEL, ROLE_OWNER_LABEL,
    LABEL_ADD_EXISTING_STUDENT, LABEL_ADD_TEACHER_BY_USERNAME, LABEL_VIEW_MY_SCORES, LABEL_MY_CLASSES,
    LABEL_ADD_CLASS, LABEL_REMOVE_CLASS, LABEL_CREATE_CLASS, LABEL_CHOOSE_CLASS,
    LABEL_ADD_STUDENT_TO_CLASS, LABEL_REMOVE_STUDENT_FROM_CLASS
}

LABEL_MAP = {normalize_text(lbl): lbl for lbl in ALL_BUTTON_LABELS}


def map_to_label(text: str) -> str:
    if text is None:
        return ""
    nt = normalize_text(text)
    return LABEL_MAP.get(nt, text)


def make_keyboard(rows):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for row in rows:
        buttons = [KeyboardButton(r) for r in row if r]
        if buttons:
            kb.add(*buttons)
    return kb


def get_start_keyboard():
    return make_keyboard([[LABEL_REGISTER, LABEL_LOGIN], [LABEL_HELP]])


def get_cancel_keyboard():
    return make_keyboard([[LABEL_CANCEL, LABEL_HELP]])


WELCOME_TEXT = "👋 سلام {name}!\nبرای شروع از منو استفاده کن یا «📝 ثبت‌نام»/«🔐 ورود» را بزن."
HELP_TEXT = (
    "📘 راهنما:\n"
    f"• ثبت آموزشگاه: {LABEL_CREATE_SCHOOL}\n"
    f"• پیوستن به آموزشگاه: {LABEL_JOIN_SCHOOL}\n"
    f"• ایجاد دانش‌آموز: {LABEL_ADD_STUDENT}\n"
    f"• ورود دانش‌آموز: {LABEL_STUDENT_LOGIN}\n"
    f"• لیست آموزشگاه‌ها: {LABEL_MY_SCHOOLS}\n"
    f"• خروج: {LABEL_LOGOUT}"
)


def load_users(): return db.load_users()


def save_users(u): return db.save_users(u)


def get_user_by_telegram(tid): return db.get_user_by_telegram(tid)


def bind_telegram_to_user(username, tid): return db.bind_telegram_to_user(username, tid)


def hash_password(password: str) -> str:
    return base64.b64encode(bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())).decode("utf-8")


def check_password(password: str, stored_base64: str) -> bool:
    try:
        hashed = base64.b64decode(stored_base64.encode("utf-8"))
        return bcrypt.checkpw(password.encode("utf-8"), hashed)
    except Exception:
        return False


def app_create_user(username: str, password_plain: str, telegram_id=None, role: str = "teacher") -> bool:
    h = hash_password(password_plain)
    return db.create_user(username, h, telegram_id, role)


def get_guest_keyboard():
    return get_start_keyboard()


def get_student_keyboard():
    rows = [
        [LABEL_VIEW_MY_SCORES],
        [LABEL_HELP, LABEL_BACK],
        [LABEL_LOGOUT]
    ]
    return make_keyboard(rows)


def get_teacher_keyboard(username=None):
    rows = [
        [LABEL_HELP, LABEL_BACK],
        [LABEL_ADD_STUDENT, LABEL_CHOOSE_STUDENT],
        [LABEL_LIST_STUDENTS, LABEL_CHOOSE_CLASS],
        [LABEL_ADD_CLASS, LABEL_MY_CLASSES],
        [LABEL_ADD_SCORE, LABEL_PN],
        [LABEL_JOIN_SCHOOL, LABEL_LOGOUT]
    ]
    return make_keyboard(rows)


def get_owner_keyboard(username=None):
    rows = [
        [LABEL_HELP, LABEL_BACK],
        [LABEL_CREATE_SCHOOL, LABEL_MY_SCHOOLS],
        [LABEL_LOGOUT]
    ]
    return make_keyboard(rows)


def get_keyboard_for_chat(chat_id):
    selected_student = sessions.get(chat_id, "selected_student")
    if selected_student:
        return get_student_keyboard()
    username = sessions.get(chat_id, "username")
    if username:
        role = db.get_user_role(username) or "teacher"
        if role == "owner":
            return get_owner_keyboard(username)
        else:
            return get_teacher_keyboard(username)
    return get_guest_keyboard()


def get_student_action_keyboard(chat_id, sid):
    username = sessions.get(chat_id, "username")
    srec = db.get_student_by_sid(sid) if sid else None
    allowed = False
    if username and srec:
        if srec.get('created_by') == username:
            allowed = True
        school_id = srec.get('school_id')
        if school_id and db.is_user_member_of_school(username, school_id, roles=["teacher", "owner"]):
            allowed = True
    if not allowed:
        return get_keyboard_for_chat(chat_id)
    rows = [
        [LABEL_ADD_SCORE, LABEL_PN, LABEL_DELETE_STUDENT],
        [LABEL_HELP, LABEL_BACK]
    ]
    return make_keyboard(rows)


def show_school_profile(chat_id, username, school_id):
    s = db.get_school(school_id)
    if not s:
        bot.send_message(chat_id, "⚠️ آموزشگاه یافت نشد.", reply_markup=get_keyboard_for_chat(chat_id))
        return

    sessions.set(chat_id, "selected_school", school_id)

    members = db.get_members_of_school(school_id) or []
    members_text = "\n".join([f"• {m['username']} — {m['role']}" for m in members]) if members else "(بدون عضو)"

    try:
        all_classes = db.list_classes_for_owner(username) if username else []
    except Exception:
        all_classes = []
    class_lines = "(بدون کلاس)"
    cls_for_school = [c for c in all_classes if (c.get('school_id') or '') == school_id]
    if cls_for_school:
        class_lines = "\n".join([f"• {c['name']} — id:{c['class_id']}" for c in cls_for_school])
    text = (
        f"🏫 آموزشگاه: {s.get('name','-')}\n"
        f"🆔: {s.get('school_id','-')}\n"
        f"👤 مالک: {s.get('owner','-')}\n"
        f"🕒 ثبت‌شده: {format_ts(s.get('created',0))}\n\n"
        f"👥 اعضا:\n{members_text}\n\n"
        f"📚 کلاس‌ها:\n{class_lines}"
    )
    owner = s.get("owner")
    if username == owner:
        
        kb = make_keyboard([[LABEL_ADD_CLASS, LABEL_DELETE_SCHOOL], [LABEL_ADD_TEACHER_BY_USERNAME, BUTTON_REMOVE_FROM_SCHOOL], [LABEL_BACK]])
    else:
        kb = make_keyboard([[LABEL_BACK]])
    bot.send_message(chat_id, text, reply_markup=kb)


def show_class_profile(chat_id, class_id):
    crec = db.get_class(class_id)
    if not crec:
        bot.send_message(chat_id, "⚠️ کلاس یافت نشد.", reply_markup=get_keyboard_for_chat(chat_id))
        return
  
    sessions.set(chat_id, "selected_class", class_id)
    members = db.list_members_of_class(class_id) or []
    members_text = "\n".join([f"• {m['name']} — id:{m['sid']}" for m in members]) if members else "(بدون عضو)"
    text = (
        f"🏷️ کلاس: {crec.get('name','-')}\n"
        f"🆔: {crec.get('class_id','-')}\n"
        f"🏫 آموزشگاه: {crec.get('school_id') or '-'}\n"
        f"👨‍💼 ایجادکننده: {crec.get('created_by') or '-'}\n"
        f"🕒 ثبت‌شده: {format_ts(crec.get('created',0))}\n\n"
        f"👥 اعضا:\n{members_text}"
    )
    kb = make_keyboard([[LABEL_ADD_STUDENT_TO_CLASS, LABEL_REMOVE_STUDENT_FROM_CLASS], [LABEL_REMOVE_CLASS, LABEL_BACK]])
    bot.send_message(chat_id, text, reply_markup=kb)


def show_student_profile(chat_id, sid):
    srec = db.get_student_by_sid(sid)
    if not srec:
        bot.send_message(chat_id, "⚠️ دانش‌آموز یافت نشد.", reply_markup=get_keyboard_for_chat(chat_id))
        return
  
    sessions.set(chat_id, "selected_student", sid)
    name = srec.get("name", "-")
    school_id = srec.get("school_id") or "-"
    created_by = srec.get("created_by") or "-"
    scores = srec.get("scores") or []
    score_lines = []
    if scores:
        for e in sorted(scores, key=lambda x: x.get("timestamp", 0), reverse=True):
            score_lines.append(f"{e.get('subject','-')}: {e.get('score','-')} ({e.get('term','-')}) — {format_ts(e.get('timestamp',0))}")
    else:
        score_lines.append("هیچ نمره‌ای ثبت نشده.")
    pn_list = srec.get("pn") or []
    plus = sum(1 for p in pn_list if p.get("type") == "plus")
    minus = sum(1 for p in pn_list if p.get("type") == "minus")
    text = (
        f"👤 دانش‌آموز: {name}\n"
        f"🆔: {sid}\n"
        f"🏫 آموزشگاه: {school_id}\n"
        f"👨‍🏫 ایجادکننده: {created_by}\n\n"
        f"📊 نمرات:\n" + "\n".join(score_lines) + f"\n\n👍 مثبت: {plus}  👎 منفی: {minus}"
    )
    kb = get_student_action_keyboard(chat_id, sid)
    bot.send_message(chat_id, text, reply_markup=kb)


def show_classes_for_user(chat_id, username):
    classes = db.list_classes_for_owner(username)
    if not classes:
        bot.send_message(chat_id, "هیچ کلاسی ثبت نکرده‌اید.", reply_markup=get_keyboard_for_chat(chat_id))
        return
    lines = [f"{i+1}. {c['name']} — id:{c['class_id']} — school:{c['school_id'] or '-'}" for i,c in enumerate(classes)]
    sessions.set(chat_id, "choose_class_list", [c['class_id'] for c in classes])
    sessions.set(chat_id, "choose_class_stage", "await_choice")
    bot.send_message(chat_id, "کلاس‌های شما:\n" + "\n".join(lines) + "\n\nشمارهٔ کلاس را ارسال کنید یا «انصراف».", reply_markup=get_cancel_keyboard())


def show_students_list_for_teacher(chat_id, username):
    items = db.list_students_for_teacher(username)
    if not items:
        bot.send_message(chat_id, "هیچ دانش‌آموزی ثبت نکرده‌اید.", reply_markup=get_keyboard_for_chat(chat_id))
        return
    text_lines = []
    ids = []
    for idx, it in enumerate(items, start=1):
        text_lines.append(f"{idx}. {it['name']} — id:{it['sid']} — school:{it['school_id'] or '-'}")
        ids.append(it['sid'])
    sessions.set(chat_id, "choose_student_list", ids)
    sessions.set(chat_id, "choose_student_stage", "await_choice")
    bot.send_message(chat_id, "فهرست دانش‌آموزان شما:\n" + "\n".join(text_lines) + "\n\nشمارهٔ دانش‌آموز را ارسال کنید یا «انصراف».", reply_markup=get_cancel_keyboard())


def to_english_digits(s):
    if s is None:
        return ""
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
    return s.translate(trans)


@bot.message_handler(content_types=['text'])
def main_handler(message):
    chat_id = message.chat.id
    raw = message.text or ""
    text = normalize_text(raw)
    btn = map_to_label(text)

  
    if text.startswith("/start"):
        tg_id = message.from_user.id
        bound = get_user_by_telegram(tg_id)
        if bound:
            sessions.set(chat_id, "username", bound)
            sessions.pop(chat_id, "selected_student", None)
            sessions.pop(chat_id, "selected_class", None)
            sessions.pop(chat_id, "selected_school", None)
            name = message.from_user.first_name or bound
            bot.send_message(chat_id, f"👋 سلام {name}!\nشما با حساب «{bound}» وارد شدید.", reply_markup=get_keyboard_for_chat(chat_id))
            return
        name = message.from_user.first_name or ""
        bot.send_message(chat_id, WELCOME_TEXT.format(name=name), reply_markup=get_start_keyboard())
        return

   
    if text.startswith("/help") or btn == LABEL_HELP:
        bot.send_message(chat_id, HELP_TEXT, reply_markup=get_keyboard_for_chat(chat_id))
        return

    
    if btn == LABEL_CANCEL:
        sessions.clear_interactive(chat_id)
        bot.send_message(chat_id, "❌ عملیات لغو شد.", reply_markup=get_keyboard_for_chat(chat_id))
        return

   
    if btn == LABEL_BACK:
        keys_to_clear = [
            "reg_stage", "login_stage", "pending_username", "reg_role", "pending_login_username",
            "create_school_stage", "pending_school_name",
            "create_class_stage",
            "add_student_stage", "pending_new_student_name", "pending_new_student_sid",
            "join_school_stage", "add_school_member_stage", "add_existing_student_list",
            "add_teacher_pending_username",
            "choose_school_stage", "choose_school_list",
            "choose_student_stage", "choose_student_list",
            "choose_class_stage", "choose_class_list",
            "score_stage", "score_choose_student_list", "score_subject", "score_value",
            "pn_stage", "pn_choose_student_list", "pn_type",
            "remove_school_member_stage", "remove_school_member_list",
            "confirm_delete_target",
            "selected_class", "selected_student",
            "add_student_to_class_stage", "class_add_student_list",
            "remove_student_from_class_stage", "class_remove_student_list",
            "view_student_stage", "pn_origin", "selected_school"
        ]
        for k in keys_to_clear:
            sessions.pop(chat_id, k, None)
        bot.send_message(chat_id, "🔙 برگشت انجام شد.", reply_markup=get_keyboard_for_chat(chat_id))
        return

    
    if sessions.get(chat_id, "reg_stage"):
        stage = sessions.get(chat_id, "reg_stage")
        if stage == "role":
            choice = btn
            if choice in (ROLE_TEACHER_LABEL, ROLE_OWNER_LABEL):
                selected_role = "owner" if choice == ROLE_OWNER_LABEL else "teacher"
                sessions.set(chat_id, "reg_role", selected_role)
                sessions.set(chat_id, "reg_stage", "username")
                bot.send_message(chat_id, "لطفاً نام کاربری مورد نظر را ارسال کنید.", reply_markup=get_cancel_keyboard())
                return
            else:
                bot.send_message(chat_id, "نقش نامعتبر است.", reply_markup=make_keyboard([[ROLE_TEACHER_LABEL, ROLE_OWNER_LABEL], [LABEL_CANCEL]]))
                return
        if stage == "username":
            username = text.split()[0] if text else ""
            USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,32}$")
            if not USERNAME_RE.match(username):
                bot.send_message(chat_id, "نام کاربری نامعتبر است. از حروف انگلیسی/اعداد/_ استفاده کن (۳-۳۲ کاراکتر).", reply_markup=get_cancel_keyboard())
                return
            users = load_users()
            if username in users:
                bot.send_message(chat_id, "این نام کاربری قبلاً وجود دارد. نام دیگری انتخاب کن.", reply_markup=get_cancel_keyboard())
                return
            sessions.set(chat_id, "pending_username", username)
            sessions.set(chat_id, "reg_stage", "password")
            bot.send_message(chat_id, "حالا رمز عبور را ارسال کنید (حداقل ۶ کاراکتر).", reply_markup=get_cancel_keyboard())
            return
        if stage == "password":
            username = sessions.get(chat_id, "pending_username")
            role = sessions.get(chat_id, "reg_role") or "teacher"
            if not username or not role:
                sessions.clear_interactive(chat_id)
                bot.send_message(chat_id, "خطا در روند ثبت‌نام. دوباره تلاش کنید.", reply_markup=get_start_keyboard())
                return
            password = raw
            if len(password) < 6:
                bot.send_message(chat_id, "رمز عبور خیلی کوتاه است. حداقل ۶ کاراکتر لازم است.", reply_markup=get_cancel_keyboard())
                return
            created = app_create_user(username, password, message.from_user.id, role)
            if not created:
                bot.send_message(chat_id, "خطا در ایجاد حساب. نام کاربری ممکن است قبلاً وجود داشته باشد.", reply_markup=get_keyboard_for_chat(chat_id))
                sessions.clear_interactive(chat_id)
                return
            sessions.clear_interactive(chat_id)
            sessions.set(chat_id, "username", username)
            sessions.pop(chat_id, "selected_student", None)
            bot.send_message(chat_id, f"✅ ثبت‌نام انجام شد و حساب به تلگرام شما متصل گردید. خوش آمدی {username}!", reply_markup=get_keyboard_for_chat(chat_id))
            return

  
    if sessions.get(chat_id, "login_stage"):
        stage = sessions.get(chat_id, "login_stage")
        if stage == "choose_type":
            choice = btn
            if choice == ROLE_TEACHER_LABEL:
                sessions.set(chat_id, "login_role", "teacher")
                sessions.set(chat_id, "login_stage", "username")
                bot.send_message(chat_id, "لطفاً نام کاربری خود را ارسال کنید.", reply_markup=get_cancel_keyboard())
                return
            elif choice == ROLE_OWNER_LABEL:
                sessions.set(chat_id, "login_role", "owner")
                sessions.set(chat_id, "login_stage", "username")
                bot.send_message(chat_id, "لطفاً نام کاربری خود را ارسال کنید.", reply_markup=get_cancel_keyboard())
                return
            elif choice == ROLE_STUDENT_LABEL:
                sessions.set(chat_id, "login_stage", "student_sid")
                bot.send_message(chat_id, "برای ورود به‌عنوان دانش‌آموز، شناسه و رمز را وارد کنید (مثال: a1b2c3 mypass).", reply_markup=get_cancel_keyboard())
                return
            else:
                bot.send_message(chat_id, "لطفاً نقش را انتخاب کنید.", reply_markup=make_keyboard([[ROLE_TEACHER_LABEL, ROLE_OWNER_LABEL, ROLE_STUDENT_LABEL], [LABEL_CANCEL]]))
                return
        if stage == "username":
            username = text.split()[0] if text else ""
            users = load_users()
            if username not in users:
                sessions.clear_interactive(chat_id)
                bot.send_message(chat_id, "نام کاربری یافت نشد. ابتدا ثبت‌نام کنید.", reply_markup=get_start_keyboard())
                return
            desired_role = sessions.get(chat_id, "login_role")
            stored_role = users.get(username, {}).get("role") or "teacher"
            if desired_role and desired_role != stored_role:
                sessions.clear_interactive(chat_id)
                bot.send_message(chat_id, f"⚠️ این حساب نقش «{stored_role}» دارد — شما نقش «{desired_role}» را انتخاب کرده‌اید. لطفاً با نقش درست وارد شوید.", reply_markup=get_keyboard_for_chat(chat_id))
                return
            stored_tid = users.get(username, {}).get("telegram_id")
            if stored_tid and stored_tid != message.from_user.id:
                sessions.clear_interactive(chat_id)
                bot.send_message(chat_id, "⚠️ این حساب قبلاً به یک تلگرام دیگر متصل شده است.", reply_markup=get_keyboard_for_chat(chat_id))
                return
            sessions.set(chat_id, "pending_login_username", username)
            sessions.set(chat_id, "login_stage", "password")
            bot.send_message(chat_id, "رمز عبور را ارسال کنید.", reply_markup=get_cancel_keyboard())
            return
        if stage == "password":
            username = sessions.get(chat_id, "pending_login_username")
            if not username:
                sessions.clear_interactive(chat_id)
                bot.send_message(chat_id, "خطا در ورود. دوباره تلاش کنید.", reply_markup=get_keyboard_for_chat(chat_id))
                return
            password = raw
            users = load_users()
            stored = users.get(username, {}).get("password")
            if not stored or not check_password(password, stored):
                sessions.clear_interactive(chat_id)
                bot.send_message(chat_id, "نام کاربری یا رمز اشتباه است.", reply_markup=get_keyboard_for_chat(chat_id))
                return
            if not users.get(username, {}).get("telegram_id"):
                users[username]["telegram_id"] = message.from_user.id
                save_users(users)
            sessions.clear_interactive(chat_id)
            sessions.set(chat_id, "username", username)
            sessions.pop(chat_id, "selected_student", None)
            bot.send_message(chat_id, f"✅ خوش آمدی {username}!", reply_markup=get_keyboard_for_chat(chat_id))
            return
        if stage == "student_sid":
            parts = raw.replace(",", " ").split()
            if len(parts) >= 2:
                sid = parts[0].strip()
                password = parts[1].strip()
                sessions.pop(chat_id, "login_stage", None)
                srec = db.get_student_by_sid(sid)
                if not srec:
                    bot.send_message(chat_id, "⚠️ دانش‌آموزی با این شناسه وجود ندارد.", reply_markup=get_keyboard_for_chat(chat_id))
                    return
                stored = db.get_student_password(sid)
                if not stored or not check_password(password, stored):
                    bot.send_message(chat_id, "⚠️ شناسه یا رمز اشتباه است.", reply_markup=get_keyboard_for_chat(chat_id))
                    return
                sessions.pop(chat_id, "username", None)
                sessions.set(chat_id, "selected_student", sid)
                bot.send_message(chat_id, "✅ ورود دانش‌آموز موفق — اکنون می‌توانید نمرات خود را مشاهده کنید.", reply_markup=get_student_action_keyboard(chat_id, sid))
                show_student_profile(chat_id, sid)
                return
            else:
                bot.send_message(chat_id, "لطفاً شناسه و رمز را وارد کنید (مثال: a1b2c3 mypass).", reply_markup=get_cancel_keyboard())
                return

   
    if sessions.get(chat_id, "create_school_stage"):
        stage = sessions.get(chat_id, "create_school_stage")
        if stage == "name":
            name = raw.strip()
            username = sessions.get(chat_id, "username")
            if not username:
                sessions.clear_interactive(chat_id)
                bot.send_message(chat_id, "⚠️ ابتدا وارد شوید.", reply_markup=get_start_keyboard())
                return
            try:
                count = db.count_schools_for_owner(username)
            except Exception:
                count = 0
            if count >= MAX_SCHOOLS_PER_OWNER:
                sessions.pop(chat_id, "create_school_stage", None)
                bot.send_message(chat_id, "⚠️ حداکثر تعداد آموزشگاه‌ها ثبت شده است.", reply_markup=get_keyboard_for_chat(chat_id))
                return
            sessions.set(chat_id, "pending_school_name", name)
            sessions.set(chat_id, "create_school_stage", "password")
            bot.send_message(chat_id, "رمز آموزشگاه را وارد کنید (حداقل ۶ کاراکتر).", reply_markup=get_cancel_keyboard())
            return
        if stage == "password":
            name = sessions.get(chat_id, "pending_school_name")
            username = sessions.get(chat_id, "username")
            if not name or not username:
                sessions.clear_interactive(chat_id)
                bot.send_message(chat_id, "خطا در ایجاد آموزشگاه.", reply_markup=get_keyboard_for_chat(chat_id))
                return
            password = raw
            if not password or len(password) < 6:
                bot.send_message(chat_id, "رمز خیلی کوتاه است. حداقل ۶ کاراکتر.", reply_markup=get_cancel_keyboard())
                return
            hashed_school_pw = hash_password(password)
            school_id = None
            try:
                school_id = db.create_school(username, name, password=hashed_school_pw)
            except Exception as e:
                logger.exception("error creating school: %s", e)
                try:
                    school_id = db.create_school(username, name)
                except Exception:
                    school_id = None
            sessions.pop(chat_id, "create_school_stage", None)
            sessions.pop(chat_id, "pending_school_name", None)
            if not school_id:
                bot.send_message(chat_id, "⚠️ خطا در ایجاد آموزشگاه. لطفاً دوباره تلاش کنید.", reply_markup=get_keyboard_for_chat(chat_id))
                return
            sessions.set(chat_id, "selected_school", school_id)
            bot.send_message(chat_id, f"✅ آموزشگاه ساخته شد.\nID: {school_id}", reply_markup=get_keyboard_for_chat(chat_id))
            show_school_profile(chat_id, username, school_id)
            return

    
    if sessions.get(chat_id, "create_class_stage"):
        stage = sessions.get(chat_id, "create_class_stage")
        if stage == "name":
            name = raw.strip()
            username = sessions.get(chat_id, "username")
            if not username:
                sessions.clear_interactive(chat_id)
                bot.send_message(chat_id, "⚠️ ابتدا وارد شوید.", reply_markup=get_start_keyboard())
                return
            school_id = sessions.get(chat_id, "selected_school")
            try:
                class_id = db.create_class(username, name, school_id)
            except TypeError:
                class_id = db.create_class(username, name)
            except Exception as e:
                logger.exception("error creating class: %s", e)
                bot.send_message(chat_id, "⚠️ خطا در ایجاد کلاس. لطفاً دوباره تلاش کنید.", reply_markup=get_keyboard_for_chat(chat_id))
                sessions.pop(chat_id, "create_class_stage", None)
                return
            sessions.pop(chat_id, "create_class_stage", None)
            bot.send_message(chat_id, f"✅ کلاس ساخته شد.\nID: {class_id}", reply_markup=get_keyboard_for_chat(chat_id))
          
            if school_id:
                username = sessions.get(chat_id, "username")
                show_school_profile(chat_id, username, school_id)
            return

   
    if sessions.get(chat_id, "join_school_stage"):
        stage = sessions.get(chat_id, "join_school_stage")
        if stage == "id":
            parts = raw.replace(",", " ").split()
            school_id = parts[0].strip() if parts else ""
            username = sessions.get(chat_id, "username")
            sessions.pop(chat_id, "join_school_stage", None)
            if not username:
                bot.send_message(chat_id, "⚠️ ابتدا وارد شوید.", reply_markup=get_start_keyboard())
                return
            s = db.get_school(school_id)
            if not s:
                bot.send_message(chat_id, "شناسهٔ آموزشگاه معتبر نیست.", reply_markup=get_keyboard_for_chat(chat_id))
                return
            if db.is_user_member_of_school(username, school_id):
                bot.send_message(chat_id, "🔔 شما قبلاً عضو این آموزشگاه هستید.", reply_markup=get_keyboard_for_chat(chat_id))
                sessions.set(chat_id, "selected_school", school_id)
                show_school_profile(chat_id, username, school_id)
                return
            added = db.add_member_to_school(school_id, username, role="teacher")
            if added:
                bot.send_message(chat_id, "✅ شما به‌عنوان معلم به آموزشگاه اضافه شدید.", reply_markup=get_keyboard_for_chat(chat_id))
                sessions.set(chat_id, "selected_school", school_id)
                show_school_profile(chat_id, username, school_id)
            else:
                bot.send_message(chat_id, "⚠️ عملیات افزودن موفق نبود (ممکن است قبلاً عضو باشید).", reply_markup=get_keyboard_for_chat(chat_id))
            return

  
    if sessions.get(chat_id, "add_student_stage"):
        sub = sessions.get(chat_id, "add_student_stage")
        username = sessions.get(chat_id, "username")
        if sub == "name":
            name = raw.strip()
            if not username:
                sessions.clear_interactive(chat_id)
                bot.send_message(chat_id, "⚠️ ابتدا وارد شوید.", reply_markup=get_start_keyboard())
                return
            try:
                count = db.count_students_by_teacher(username)
            except Exception:
                count = 0
            if count >= MAX_STUDENTS_PER_TEACHER:
                sessions.pop(chat_id, "add_student_stage", None)
                bot.send_message(chat_id, "⚠️ حداکثر تعداد دانش‌آموزان ثبت شده است.", reply_markup=get_keyboard_for_chat(chat_id))
                return
            sessions.set(chat_id, "pending_new_student_name", name)
            sessions.set(chat_id, "add_student_stage", "sid")
            bot.send_message(chat_id, "نام دانش‌آموز ثبت شد. حالا شناسه (sid) دانش‌آموز را وارد کنید (مثلاً a1b2c3).", reply_markup=get_cancel_keyboard())
            return
        if sub == "sid":
            sid = raw.strip()
            pending_name = sessions.get(chat_id, "pending_new_student_name")
            if not pending_name:
                sessions.clear_interactive(chat_id)
                bot.send_message(chat_id, "خطا در روند ایجاد دانش‌آموز.", reply_markup=get_keyboard_for_chat(chat_id))
                return
            existing = db.get_student_by_sid(sid)
            if existing:
                bot.send_message(chat_id, "این شناسه قبلاً وجود دارد. شناسهٔ دیگری وارد کنید.", reply_markup=get_cancel_keyboard())
                return
            sessions.set(chat_id, "pending_new_student_sid", sid)
            sessions.set(chat_id, "add_student_stage", "password")
            bot.send_message(chat_id, "رمز دانش‌آموز را وارد کنید (حداقل ۶ کاراکتر).", reply_markup=get_cancel_keyboard())
            return
        if sub == "password":
            password = raw
            sid = sessions.get(chat_id, "pending_new_student_sid")
            name = sessions.get(chat_id, "pending_new_student_name")
            school_id = sessions.get(chat_id, "selected_school")
            username = sessions.get(chat_id, "username")
            if not (sid and name and username):
                sessions.clear_interactive(chat_id)
                bot.send_message(chat_id, "خطا — اطلاعات ناقص.", reply_markup=get_keyboard_for_chat(chat_id))
                return
            if len(password) < 6:
                bot.send_message(chat_id, "رمز خیلی کوتاه است.", reply_markup=get_cancel_keyboard())
                return
            hashed = hash_password(password)
            try:
                created, code = db.create_student(username, school_id, name, sid, hashed)
            except Exception as e:
                logger.exception("error creating student: %s", e)
                created, code = False, None
            sessions.pop(chat_id, "add_student_stage", None)
            sessions.pop(chat_id, "pending_new_student_sid", None)
            sessions.pop(chat_id, "pending_new_student_name", None)
            if not created:
                bot.send_message(chat_id, "خطا در ایجاد دانش‌آموز (احتمالاً sid یا نام تکراری).", reply_markup=get_keyboard_for_chat(chat_id))
                return
            sessions.set(chat_id, "selected_student", sid)
            bot.send_message(chat_id, f"✅ دانش‌آموز ایجاد شد.\nشناسه: {sid}\nکد ورود داخلی: {code}", reply_markup=get_student_action_keyboard(chat_id, sid))
            show_student_profile(chat_id, sid)
            return

 
    if sessions.get(chat_id, "choose_student_stage"):
        if text.isdigit() or to_english_digits(text).isdigit():
            ids = sessions.get(chat_id, "choose_student_list") or []
            idx = int(to_english_digits(text))
            if idx < 1 or idx > len(ids):
                bot.send_message(chat_id, "شماره خارج از محدوده است.", reply_markup=get_cancel_keyboard())
                return
            sid = ids[idx-1]
            sessions.pop(chat_id, "choose_student_stage", None)
            sessions.pop(chat_id, "choose_student_list", None)
            sessions.set(chat_id, "selected_student", sid)
            bot.send_message(chat_id, "✅ دانش‌آموز انتخاب شد.", reply_markup=get_student_action_keyboard(chat_id, sid))
            show_student_profile(chat_id, sid)
            return

    if sessions.get(chat_id, "choose_class_stage"):
        if text.isdigit() or to_english_digits(text).isdigit():
            ids = sessions.get(chat_id, "choose_class_list") or []
            idx = int(to_english_digits(text))
            if idx < 1 or idx > len(ids):
                bot.send_message(chat_id, "شماره خارج از محدوده است.", reply_markup=get_cancel_keyboard())
                return
            class_id = ids[idx-1]
            sessions.pop(chat_id, "choose_class_stage", None)
            sessions.pop(chat_id, "choose_class_list", None)
            sessions.set(chat_id, "selected_class", class_id)
            show_class_profile(chat_id, class_id)
            return

   
    if sessions.get(chat_id, "choose_school_stage"):
        if text.isdigit() or to_english_digits(text).isdigit():
            ids = sessions.get(chat_id, "choose_school_list") or []
            idx = int(to_english_digits(text))
            if idx < 1 or idx > len(ids):
                bot.send_message(chat_id, "شماره خارج از محدوده است.", reply_markup=get_cancel_keyboard())
                return
            school_id = ids[idx-1]
            sessions.pop(chat_id, "choose_school_stage", None)
            sessions.pop(chat_id, "choose_school_list", None)
            sessions.set(chat_id, "selected_school", school_id)
            username = sessions.get(chat_id, "username")
            show_school_profile(chat_id, username, school_id)
            return

    
    if sessions.get(chat_id, "add_school_member_stage"):
        sub = sessions.get(chat_id, "add_school_member_stage")
        if sub == "select_existing_student":
            if text.isdigit() or to_english_digits(text).isdigit():
                ids = sessions.get(chat_id, "add_existing_student_list") or []
                idx = int(to_english_digits(text))
                if idx < 1 or idx > len(ids):
                    bot.send_message(chat_id, "شماره خارج از محدوده است.", reply_markup=get_cancel_keyboard())
                    return
                sid = ids[idx-1]
                school_id = sessions.get(chat_id, "selected_school")
                owner_username = sessions.get(chat_id, "username")
                sessions.pop(chat_id, "add_school_member_stage", None)
                sessions.pop(chat_id, "add_existing_student_list", None)
                if not (sid and school_id and owner_username):
                    bot.send_message(chat_id, "خطا — اطلاعات ناقص.", reply_markup=get_keyboard_for_chat(chat_id))
                    return
                try:
                    assigned = db.assign_student_to_school(sid, school_id)
                except Exception as e:
                    logger.exception("error assigning student to school: %s", e)
                    assigned = False
                if assigned:
                    bot.send_message(chat_id, f"✅ دانش‌آموز {sid} به آموزشگاه اضافه شد.", reply_markup=get_keyboard_for_chat(chat_id))
                else:
                    bot.send_message(chat_id, "⚠️ اضافه کردن دانش‌آموز موفق نبود.", reply_markup=get_keyboard_for_chat(chat_id))
                show_school_profile(chat_id, owner_username, school_id)
                return
        if sub == "add_teacher_username":
            target_username = text.split()[0] if text else ""
            school_id = sessions.get(chat_id, "selected_school")
            owner_username = sessions.get(chat_id, "username")
            if not target_username:
                bot.send_message(chat_id, "نام کاربری نامعتبر. دوباره ارسال کن.", reply_markup=get_cancel_keyboard())
                return
            sessions.set(chat_id, "add_school_member_stage", "add_teacher_password")
            sessions.set(chat_id, "add_teacher_pending_username", target_username)
            bot.send_message(chat_id, f"لطفاً رمزِ حسابِ {target_username} را ارسال کن. اگر حساب وجود ندارد، با همین رمز ایجاد خواهد شد.", reply_markup=get_cancel_keyboard())
            return
        if sub == "add_teacher_password":
            password = raw
            target_username = sessions.get(chat_id, "add_teacher_pending_username")
            school_id = sessions.get(chat_id, "selected_school")
            owner_username = sessions.get(chat_id, "username")
            sessions.pop(chat_id, "add_school_member_stage", None)
            sessions.pop(chat_id, "add_teacher_pending_username", None)
            if not (target_username and password and school_id and owner_username):
                bot.send_message(chat_id, "خطا — اطلاعات ناقص.", reply_markup=get_keyboard_for_chat(chat_id))
                return
            users = load_users()
            if target_username in users:
                stored = users.get(target_username, {}).get("password")
                if not stored or not check_password(password, stored):
                    bot.send_message(chat_id, "⚠️ رمز صحیح نیست — عملیات متوقف شد.", reply_markup=get_keyboard_for_chat(chat_id))
                    return
                try:
                    added = db.add_member_to_school(school_id, target_username, role="teacher")
                except Exception:
                    added = False
                if added:
                    bot.send_message(chat_id, f"✅ {target_username} به عنوان معلم اضافه شد.", reply_markup=get_keyboard_for_chat(chat_id))
                else:
                    bot.send_message(chat_id, "⚠️ عملیات موفق نبود (ممکن است عضو باشد).", reply_markup=get_keyboard_for_chat(chat_id))
                show_school_profile(chat_id, owner_username, school_id)
                return
            else:
                created = app_create_user(target_username, password)
                try:
                    added = db.add_member_to_school(school_id, target_username, role="teacher")
                except Exception:
                    added = False
                if created or added:
                    bot.send_message(chat_id, f"✅ معلم {target_username} ایجاد/افزوده شد.", reply_markup=get_keyboard_for_chat(chat_id))
                else:
                    bot.send_message(chat_id, "⚠️ عملیات موفق نبود.", reply_markup=get_keyboard_for_chat(chat_id))
                show_school_profile(chat_id, owner_username, school_id)
                return

    # score flow
    if sessions.get(chat_id, "score_stage"):
        stage = sessions.get(chat_id, "score_stage")
        if stage == "choose_student":
            if text.isdigit() or to_english_digits(text).isdigit():
                ids = sessions.get(chat_id, "score_choose_student_list") or []
                idx = int(to_english_digits(text))
                if idx < 1 or idx > len(ids):
                    bot.send_message(chat_id, "شماره خارج از محدوده است.", reply_markup=get_cancel_keyboard())
                    return
                sid = ids[idx-1]
                sessions.pop(chat_id, "score_stage", None)
                sessions.pop(chat_id, "score_choose_student_list", None)
                sessions.set(chat_id, "selected_student", sid)
                sessions.set(chat_id, "score_stage", "subject")
                bot.send_message(chat_id, "نام درس را وارد کنید.", reply_markup=get_cancel_keyboard())
                return
            else:
                bot.send_message(chat_id, "لطفاً شمارهٔ دانش‌آموز را ارسال کنید.", reply_markup=get_cancel_keyboard())
                return
        if stage == "subject":
            sessions.set(chat_id, "score_subject", raw.strip())
            sessions.set(chat_id, "score_stage", "value")
            bot.send_message(chat_id, "حال نمره را وارد کنید (عدد بین 0 تا 100).", reply_markup=get_cancel_keyboard())
            return
        if stage == "value":
            try:
                val = float(text.replace(",", "."))
            except Exception:
                bot.send_message(chat_id, "نمره نامعتبر است. عدد وارد کنید.", reply_markup=get_cancel_keyboard())
                return
            if val < 0 or val > 100:
                bot.send_message(chat_id, "نمره باید بین 0 تا 100 باشد.", reply_markup=get_cancel_keyboard())
                return
            sessions.set(chat_id, "score_value", val)
            sessions.set(chat_id, "score_stage", "term")
            bot.send_message(chat_id, "نام ماه/ترم را وارد کنید (مثلاً آذر).", reply_markup=get_cancel_keyboard())
            return
        if stage == "term":
            term = raw.strip()
            subject = sessions.get(chat_id, "score_subject")
            val = sessions.get(chat_id, "score_value")
            sid = sessions.get(chat_id, "selected_student")
            username = sessions.get(chat_id, "username")
            srec = db.get_student_by_sid(sid) if sid else None
            allowed = False
            if username and srec:
                if srec.get("created_by") == username:
                    allowed = True
                school_id = srec.get("school_id")
                if school_id and db.is_user_member_of_school(username, school_id, roles=["teacher", "owner"]):
                    allowed = True
            if not allowed:
                bot.send_message(chat_id, "⚠️ اجازه ثبت نمره را ندارید.", reply_markup=get_keyboard_for_chat(chat_id))
                sessions.pop(chat_id, "score_stage", None)
                sessions.pop(chat_id, "score_subject", None)
                sessions.pop(chat_id, "score_value", None)
                return
            try:
                db.add_score_to_student(sid, subject, val, term, username)
            except Exception as e:
                logger.exception("error adding score: %s", e)
                bot.send_message(chat_id, "⚠️ خطا در ثبت نمره.", reply_markup=get_keyboard_for_chat(chat_id))
                sessions.pop(chat_id, "score_stage", None)
                return
            sessions.pop(chat_id, "score_stage", None)
            sessions.pop(chat_id, "score_subject", None)
            sessions.pop(chat_id, "score_value", None)
            bot.send_message(chat_id, "✅ نمره ثبت شد.", reply_markup=get_keyboard_for_chat(chat_id))
            show_student_profile(chat_id, sid)
            return

    # PN (plus/minus)
    if btn == LABEL_PN:
        username = sessions.get(chat_id, "username")
        sid = sessions.get(chat_id, "selected_student")
        if sid:
            sessions.set(chat_id, "pn_stage", "type")
            bot.send_message(chat_id, "امتیاز: لطفاً نوع را انتخاب کنید.", reply_markup=make_keyboard([[BUTTON_PLUS, BUTTON_MINUS], [LABEL_CANCEL]]))
            return
        students = db.list_students_for_teacher(username) if username else []
        if not students:
            selected_school = sessions.get(chat_id, "selected_school")
            if selected_school:
                students = db.list_students_in_school(selected_school)
        if not students:
            bot.send_message(chat_id, "هیچ دانش‌آموزی برای انتخاب وجود ندارد.", reply_markup=get_keyboard_for_chat(chat_id))
            return
        text_lines = []
        ids = []
        for idx, it in enumerate(students, start=1):
            text_lines.append(f"{idx}. {it['name']} — id:{it['sid']} — school:{it.get('school_id') or '-'}")
            ids.append(it['sid'])
        sessions.set(chat_id, "pn_choose_student_list", ids)
        sessions.set(chat_id, "pn_stage", "choose_student")
        sessions.set(chat_id, "pn_origin", "pn_button")
        bot.send_message(chat_id, "دانش‌آموزان شما:\n" + "\n".join(text_lines) + "\n\nیک شماره انتخاب کنید تا امتیاز داده شود یا «انصراف».", reply_markup=get_cancel_keyboard())
        return

    if sessions.get(chat_id, "pn_stage"):
        stage = sessions.get(chat_id, "pn_stage")
        if stage == "choose_student":
            if text.isdigit() or to_english_digits(text).isdigit():
                ids = sessions.get(chat_id, "pn_choose_student_list") or []
                idx = int(to_english_digits(text))
                if idx < 1 or idx > len(ids):
                    bot.send_message(chat_id, "شماره خارج از محدوده است.", reply_markup=get_cancel_keyboard())
                    return
                sid = ids[idx-1]
                sessions.set(chat_id, "selected_student", sid)
                sessions.set(chat_id, "pn_stage", "type")
                bot.send_message(chat_id, "امتیاز: لطفاً نوع را انتخاب کنید.", reply_markup=make_keyboard([[BUTTON_PLUS, BUTTON_MINUS], [LABEL_CANCEL]]))
                return
            else:
                bot.send_message(chat_id, "لطفاً شمارهٔ دانش‌آموز را ارسال کنید یا «انصراف».", reply_markup=get_cancel_keyboard())
                return
        if stage == "type":
            if btn not in (BUTTON_PLUS, BUTTON_MINUS):
                bot.send_message(chat_id, "لطفاً یکی از دکمه‌های ➕ مثبت یا ➖ منفی را انتخاب کنید.", reply_markup=make_keyboard([[BUTTON_PLUS, BUTTON_MINUS], [LABEL_CANCEL]]))
                return
            pn_type = "plus" if btn == BUTTON_PLUS else "minus"
            sessions.set(chat_id, "pn_type", pn_type)
            sessions.set(chat_id, "pn_stage", "reason")
            bot.send_message(chat_id, "حالا دلیل یا توضیح امتیاز را ارسال کنید.", reply_markup=get_cancel_keyboard())
            return
        if stage == "reason":
            reason = raw.strip()
            pn_type = sessions.get(chat_id, "pn_type")
            sid = sessions.get(chat_id, "selected_student")
            username = sessions.get(chat_id, "username")
            srec = db.get_student_by_sid(sid) if sid else None
            allowed = False
            if username and srec:
                if srec.get("created_by") == username:
                    allowed = True
                school_id = srec.get("school_id")
                if school_id and db.is_user_member_of_school(username, school_id, roles=["teacher", "owner"]):
                    allowed = True
            if not allowed:
                bot.send_message(chat_id, "⚠️ اجازه ثبت امتیاز را ندارید.", reply_markup=get_keyboard_for_chat(chat_id))
                sessions.pop(chat_id, "pn_stage", None)
                sessions.pop(chat_id, "pn_type", None)
                return
            try:
                db.add_pn_to_student(sid, pn_type, reason, username)
            except Exception as e:
                logger.exception("error adding pn: %s", e)
                bot.send_message(chat_id, "⚠️ خطا در ثبت امتیاز.", reply_markup=get_keyboard_for_chat(chat_id))
                sessions.pop(chat_id, "pn_stage", None)
                sessions.pop(chat_id, "pn_type", None)
                return
            sessions.pop(chat_id, "pn_stage", None)
            sessions.pop(chat_id, "pn_type", None)
            bot.send_message(chat_id, "✅ امتیاز ثبت شد.", reply_markup=get_student_action_keyboard(chat_id, sid))
            show_student_profile(chat_id, sid)
            return

    
    if btn == LABEL_REGISTER:
        sessions.set(chat_id, "reg_stage", "role")
        bot.send_message(chat_id, "نقش خود را انتخاب کنید:", reply_markup=make_keyboard([[ROLE_TEACHER_LABEL, ROLE_OWNER_LABEL], [LABEL_CANCEL]]))
        return

    if btn == LABEL_LOGIN:
        sessions.set(chat_id, "login_stage", "choose_type")
        kb = make_keyboard([[ROLE_TEACHER_LABEL, ROLE_OWNER_LABEL, ROLE_STUDENT_LABEL], [LABEL_CANCEL]])
        bot.send_message(chat_id, "می‌خواهید با چه نقشی وارد شوید؟", reply_markup=kb)
        return

    if btn == LABEL_LOGOUT:
        sessions.clear_all(chat_id)
        bot.send_message(chat_id, "🚪 با موفقیت خارج شدید.", reply_markup=get_start_keyboard())
        return

    if btn == LABEL_CREATE_SCHOOL:
        username = sessions.get(chat_id, "username")
        if not username:
            bot.send_message(chat_id, "⚠️ ابتدا وارد شوید یا ثبت‌نام کنید.", reply_markup=get_start_keyboard())
            return
        role = db.get_user_role(username) or "teacher"
        if role != "owner":
            bot.send_message(chat_id, "⚠️ فقط مدیر می‌تواند آموزشگاه ثبت کند.", reply_markup=get_keyboard_for_chat(chat_id))
            return
        sessions.set(chat_id, "create_school_stage", "name")
        bot.send_message(chat_id, "نام آموزشگاه را وارد کنید (یا «انصراف»).", reply_markup=get_cancel_keyboard())
        return

    if btn == LABEL_JOIN_SCHOOL:
        username = sessions.get(chat_id, "username")
        if not username:
            bot.send_message(chat_id, "⚠️ ابتدا وارد شوید.", reply_markup=get_start_keyboard())
            return
        sessions.set(chat_id, "join_school_stage", "id")
        bot.send_message(chat_id, "شناسهٔ آموزشگاه را ارسال کنید.", reply_markup=get_cancel_keyboard())
        return

    if btn == LABEL_MY_SCHOOLS:
        username = sessions.get(chat_id, "username")
        if not username:
            bot.send_message(chat_id, "⚠️ ابتدا وارد شوید.", reply_markup=get_start_keyboard())
            return
        items = db.list_schools_for_member(username)
        if not items:
            bot.send_message(chat_id, "شما عضو هیچ آموزشگاهی نیستید.", reply_markup=get_keyboard_for_chat(chat_id))
            return
        text_lines = []
        ids = []
        for idx, it in enumerate(items, start=1):
            text_lines.append(f"{idx}. {it['name']} — id:{it['school_id']} — role:{it['role']}")
            ids.append(it['school_id'])
        sessions.set(chat_id, "choose_school_list", ids)
        sessions.set(chat_id, "choose_school_stage", "await_choice")
        bot.send_message(chat_id, "آموزشگاه‌های شما:\n" + "\n".join(text_lines) + "\n\nشمارهٔ آموزشگاه را ارسال کنید یا «انصراف».", reply_markup=get_cancel_keyboard())
        return

    if btn == LABEL_MY_CLASSES or btn == LABEL_CHOOSE_CLASS:
        username = sessions.get(chat_id, "username")
        if not username:
            bot.send_message(chat_id, "⚠️ ابتدا وارد شوید.", reply_markup=get_start_keyboard())
            return
        show_classes_for_user(chat_id, username)
        return

    if btn == LABEL_ADD_EXISTING_STUDENT:
        school_id = sessions.get(chat_id, "selected_school")
        owner_username = sessions.get(chat_id, "username")
        if not (school_id and owner_username):
            bot.send_message(chat_id, "⚠️ ابتدا یک آموزشگاه را انتخاب کنید.", reply_markup=get_keyboard_for_chat(chat_id))
            return
        students = db.list_students_for_teacher(owner_username)
        choices = [s for s in students if (s.get('school_id') or '') != school_id]
        if not choices:
            bot.send_message(chat_id, "هیچ دانش‌آموز قابل افزودنی در فهرست شما وجود ندارد.", reply_markup=get_keyboard_for_chat(chat_id))
            return
        text_lines = []
        ids = []
        for idx, it in enumerate(choices, start=1):
            text_lines.append(f"{idx}. {it['name']} — id:{it['sid']} — school:{it['school_id'] or '-'}")
            ids.append(it['sid'])
        sessions.set(chat_id, "add_existing_student_list", ids)
        sessions.set(chat_id, "add_school_member_stage", "select_existing_student")
        bot.send_message(chat_id, "دانش‌آموز مورد نظر را با شماره انتخاب کنید یا «انصراف».\n" + "\n".join(text_lines), reply_markup=get_cancel_keyboard())
        return

    if btn == LABEL_ADD_TEACHER_BY_USERNAME:
        school_id = sessions.get(chat_id, "selected_school")
        owner_username = sessions.get(chat_id, "username")
        if not (school_id and owner_username):
            bot.send_message(chat_id, "⚠️ ابتدا یک آموزشگاه را انتخاب کنید.", reply_markup=get_keyboard_for_chat(chat_id))
            return
        sessions.set(chat_id, "add_school_member_stage", "add_teacher_username")
        bot.send_message(chat_id, "نام کاربریِ معلم را وارد کنید. سپس از شما خواسته می‌شود رمز را وارد نمایید.", reply_markup=get_cancel_keyboard())
        return

    if btn == BUTTON_REMOVE_FROM_SCHOOL:
        school_id = sessions.get(chat_id, "selected_school")
        username = sessions.get(chat_id, "username")
        if not (school_id and username):
            bot.send_message(chat_id, "⚠️ ابتدا یک آموزشگاه را انتخاب کنید.", reply_markup=get_keyboard_for_chat(chat_id))
            return
        s = db.get_school(school_id)
        if not s:
            bot.send_message(chat_id, "⚠️ آموزشگاه پیدا نشد.", reply_markup=get_keyboard_for_chat(chat_id))
            return
        if s.get("owner") != username:
            bot.send_message(chat_id, "⚠️ فقط مالک آموزشگاه می‌تواند اعضا را حذف کند.", reply_markup=get_keyboard_for_chat(chat_id))
            return
        members = db.get_members_of_school(school_id)
        if not members:
            bot.send_message(chat_id, "هیچ عضوی برای حذف وجود ندارد.", reply_markup=get_keyboard_for_chat(chat_id))
            return
        text_lines = []
        ids = []
        for idx, m in enumerate(members, start=1):
            text_lines.append(f"{idx}. {m['username']} — role:{m['role']}")
            ids.append(m['username'])
        sessions.set(chat_id, "remove_school_member_list", ids)
        sessions.set(chat_id, "remove_school_member_stage", "await_choice")
        bot.send_message(chat_id, "اعضای آموزشگاه:\n" + "\n".join(text_lines) + "\n\nشمارهٔ عضو را ارسال کنید تا حذف شود یا «انصراف».", reply_markup=get_cancel_keyboard())
        return

    if btn == LABEL_ADD_STUDENT:
        username = sessions.get(chat_id, "username")
        if not username:
            bot.send_message(chat_id, "⚠️ ابتدا وارد شوید.", reply_markup=get_start_keyboard())
            return
        sessions.set(chat_id, "add_student_stage", "name")
        bot.send_message(chat_id, "نام دانش‌آموز را وارد کنید (یا «انصراف»).", reply_markup=get_cancel_keyboard())
        return

    if btn == LABEL_CHOOSE_STUDENT:
        username = sessions.get(chat_id, "username")
        if not username:
            bot.send_message(chat_id, "⚠️ ابتدا وارد شوید.", reply_markup=get_start_keyboard())
            return
        show_students_list_for_teacher(chat_id, username)
        return

    if btn == LABEL_LIST_STUDENTS:
        username = sessions.get(chat_id, "username")
        if not username:
            bot.send_message(chat_id, "⚠️ ابتدا وارد شوید.", reply_markup=get_start_keyboard())
            return
        items = db.list_students_for_teacher(username)
        if not items:
            bot.send_message(chat_id, "هیچ دانش‌آموزی ثبت نکرده‌اید.", reply_markup=get_keyboard_for_chat(chat_id))
            return
        lines = [f"• {it['name']} — id:{it['sid']} — school:{it['school_id'] or '-'}" for it in items]
        bot.send_message(chat_id, "📚 دانش‌آموزهای شما:\n" + "\n".join(lines), reply_markup=get_keyboard_for_chat(chat_id))
        return

    if btn == LABEL_STUDENT_LOGIN:
        sessions.set(chat_id, "login_stage", "student_sid")
        bot.send_message(chat_id, "برای ورود دانش‌آموز، شناسه و رمز را وارد کنید (مثال: a1b2c3 mypass).", reply_markup=get_cancel_keyboard())
        return

    if btn == LABEL_VIEW_MY_SCORES:
        if sessions.get(chat_id, "selected_student"):
            sid = sessions.get(chat_id, "selected_student")
            show_student_profile(chat_id, sid)
            return
        sessions.set(chat_id, "view_student_stage", "await")
        bot.send_message(chat_id, "برای دیدن نمرات خود، شناسه و رمز را وارد کنید (مثال: a1b2c3 mypass).", reply_markup=get_cancel_keyboard())
        return

    if btn == LABEL_ADD_SCORE:
        sid = sessions.get(chat_id, "selected_student")
        username = sessions.get(chat_id, "username")
        if not sid:
            my_students = db.list_students_for_teacher(username) if username else []
            if my_students:
                text_lines = []
                ids = []
                for idx, it in enumerate(my_students, start=1):
                    text_lines.append(f"{idx}. {it['name']} — id:{it['sid']} — school:{it['school_id'] or '-'}")
                    ids.append(it['sid'])
                sessions.set(chat_id, "score_choose_student_list", ids)
                sessions.set(chat_id, "score_stage", "choose_student")
                bot.send_message(chat_id, "کدام دانش‌آموز؟ (شماره را ارسال کن)\n" + "\n".join(text_lines), reply_markup=get_cancel_keyboard())
                return
            selected_school = sessions.get(chat_id, "selected_school")
            if selected_school:
                school_students = db.list_students_in_school(selected_school)
                if school_students:
                    text_lines = []
                    ids = []
                    for idx, it in enumerate(school_students, start=1):
                        text_lines.append(f"{idx}. {it['name']} — id:{it['sid']}")
                        ids.append(it['sid'])
                    sessions.set(chat_id, "score_choose_student_list", ids)
                    sessions.set(chat_id, "score_stage", "choose_student")
                    bot.send_message(chat_id, "کدام دانش‌آموز؟ (شماره را ارسال کن)\n" + "\n".join(text_lines), reply_markup=get_cancel_keyboard())
                    return
            bot.send_message(chat_id, "ابتدا یک دانش‌آموز انتخاب کنید یا ابتدا دانش‌آموز ایجاد کنید.", reply_markup=get_keyboard_for_chat(chat_id))
            return
        sessions.set(chat_id, "score_stage", "subject")
        bot.send_message(chat_id, "نام درس را وارد کنید (یا «انصراف»).", reply_markup=get_cancel_keyboard())
        return

   
    if btn == LABEL_DELETE_STUDENT:
        sid = sessions.get(chat_id, "selected_student")
        if not sid:
            username = sessions.get(chat_id, "username")
            if not username:
                bot.send_message(chat_id, "⚠️ ابتدا وارد شوید.", reply_markup=get_start_keyboard())
                return
            show_students_list_for_teacher(chat_id, username)
            return
        sessions.set(chat_id, "confirm_delete_target", ("student", sid))
        bot.send_message(chat_id, f"آیا از حذف دانش‌آموز با شناسه {sid} مطمئنی؟", reply_markup=make_keyboard([[LABEL_CONFIRM_DELETE, LABEL_CANCEL]]))
        return

   
    if btn == LABEL_REMOVE_CLASS:
        class_id = sessions.get(chat_id, "selected_class")
        if not class_id:
            username = sessions.get(chat_id, "username")
            if not username:
                bot.send_message(chat_id, "⚠️ ابتدا وارد شوید.", reply_markup=get_start_keyboard())
                return
            show_classes_for_user(chat_id, username)
            return
        sessions.set(chat_id, "confirm_delete_target", ("class", class_id))
        bot.send_message(chat_id, f"آیا از حذف کلاس با شناسه {class_id} مطمئنی؟", reply_markup=make_keyboard([[LABEL_CONFIRM_DELETE, LABEL_CANCEL]]))
        return

   
    if btn == LABEL_ADD_STUDENT_TO_CLASS:
        username = sessions.get(chat_id, "username")
        class_id = sessions.get(chat_id, "selected_class")
        if not username:
            bot.send_message(chat_id, "⚠️ ابتدا وارد شوید.", reply_markup=get_start_keyboard())
            return
        if not class_id:
            bot.send_message(chat_id, "⚠️ ابتدا یک کلاس انتخاب کنید (از «کلاس‌های من»).", reply_markup=get_keyboard_for_chat(chat_id))
            return
        my_students = db.list_students_for_teacher(username)
        if not my_students:
            bot.send_message(chat_id, "هیچ دانش‌آموزی ندارید که اضافه کنید.", reply_markup=get_keyboard_for_chat(chat_id))
            return
        members = db.list_members_of_class(class_id) or []
        member_sids = {m['sid'] for m in members}
        choices = [s for s in my_students if s['sid'] not in member_sids]
        if not choices:
            bot.send_message(chat_id, "هیچ دانش‌آموزی در فهرست شما وجود ندارد که قبلاً عضو این کلاس نباشد.", reply_markup=get_keyboard_for_chat(chat_id))
            return
        text_lines = []
        ids = []
        for idx, it in enumerate(choices, start=1):
            text_lines.append(f"{idx}. {it['name']} — id:{it['sid']} — school:{it.get('school_id') or '-'}")
            ids.append(it['sid'])
        sessions.set(chat_id, "class_add_student_list", ids)
        sessions.set(chat_id, "add_student_to_class_stage", "await_choice")
        bot.send_message(chat_id, "دانش‌آموزی که می‌خواهی به کلاس اضافه کنی را با شماره انتخاب کن (بدون تأیید اضافی):\n" + "\n".join(text_lines), reply_markup=get_cancel_keyboard())
        return

    if sessions.get(chat_id, "add_student_to_class_stage"):
        stage = sessions.get(chat_id, "add_student_to_class_stage")
        if stage == "await_choice":
            if text.isdigit() or to_english_digits(text).isdigit():
                ids = sessions.get(chat_id, "class_add_student_list") or []
                idx = int(to_english_digits(text))
                if idx < 1 or idx > len(ids):
                    bot.send_message(chat_id, "شماره خارج از محدوده است.", reply_markup=get_cancel_keyboard())
                    return
                sid = ids[idx-1]
                class_id = sessions.get(chat_id, "selected_class")
                username = sessions.get(chat_id, "username")
                try:
                    added = db.add_member_to_class(class_id, sid, added_by=username)
                except Exception as e:
                    logger.exception("error adding member to class: %s", e)
                    added = False
                sessions.pop(chat_id, "add_student_to_class_stage", None)
                sessions.pop(chat_id, "class_add_student_list", None)
                if added:
                    bot.send_message(chat_id, f"✅ دانش‌آموز {sid} به کلاس اضافه شد.", reply_markup=get_keyboard_for_chat(chat_id))
                    show_class_profile(chat_id, class_id)
                else:
                    bot.send_message(chat_id, "⚠️ اضافه کردن به کلاس موفق نبود.", reply_markup=get_keyboard_for_chat(chat_id))
                    show_class_profile(chat_id, class_id)
                return
            else:
                bot.send_message(chat_id, "لطفاً شمارهٔ دانش‌آموز را ارسال کنید یا «انصراف».", reply_markup=get_cancel_keyboard())
                return

    if btn == LABEL_REMOVE_STUDENT_FROM_CLASS:
        class_id = sessions.get(chat_id, "selected_class")
        username = sessions.get(chat_id, "username")
        if not username:
            bot.send_message(chat_id, "⚠️ ابتدا وارد شوید.", reply_markup=get_start_keyboard())
            return
        if not class_id:
            bot.send_message(chat_id, "⚠️ ابتدا یک کلاس انتخاب کنید.", reply_markup=get_keyboard_for_chat(chat_id))
            return
        members = db.list_members_of_class(class_id)
        if not members:
            bot.send_message(chat_id, "هیچ دانش‌آموزی در این کلاس وجود ندارد.", reply_markup=get_keyboard_for_chat(chat_id))
            return
        text_lines = []
        ids = []
        for idx, m in enumerate(members, start=1):
            text_lines.append(f"{idx}. {m['name']} — id:{m['sid']}")
            ids.append(m['sid'])
        sessions.set(chat_id, "class_remove_student_list", ids)
        sessions.set(chat_id, "remove_student_from_class_stage", "await_choice")
        bot.send_message(chat_id, "دانش‌آموزی که می‌خواهی حذف کنی را با شماره انتخاب کن (بعد تأیید می‌پذیرد):\n" + "\n".join(text_lines), reply_markup=get_cancel_keyboard())
        return

    if sessions.get(chat_id, "remove_student_from_class_stage"):
        stage = sessions.get(chat_id, "remove_student_from_class_stage")
        if stage == "await_choice":
            if text.isdigit() or to_english_digits(text).isdigit():
                ids = sessions.get(chat_id, "class_remove_student_list") or []
                idx = int(to_english_digits(text))
                if idx < 1 or idx > len(ids):
                    bot.send_message(chat_id, "شماره خارج از محدوده است.", reply_markup=get_cancel_keyboard())
                    return
                sid = ids[idx-1]
                class_id = sessions.get(chat_id, "selected_class")
                sessions.pop(chat_id, "remove_student_from_class_stage", None)
                sessions.pop(chat_id, "class_remove_student_list", None)
                sessions.set(chat_id, "confirm_delete_target", ("class_member", class_id, sid))
                bot.send_message(chat_id, f"آیا از حذف دانش‌آموز {sid} از این کلاس مطمئنی؟", reply_markup=make_keyboard([[LABEL_CONFIRM_DELETE, LABEL_CANCEL]]))
                return
            else:
                bot.send_message(chat_id, "لطفاً شمارهٔ دانش‌آموز را ارسال کنید یا «انصراف».", reply_markup=get_cancel_keyboard())
                return

 
    if sessions.get(chat_id, "remove_school_member_stage"):
        if text.isdigit() or to_english_digits(text).isdigit():
            ids = sessions.get(chat_id, "remove_school_member_list") or []
            idx = int(to_english_digits(text))
            if idx < 1 or idx > len(ids):
                bot.send_message(chat_id, "شماره خارج از محدوده است.", reply_markup=get_cancel_keyboard())
                return
            member_username = ids[idx-1]
            school_id = sessions.get(chat_id, "selected_school")
            owner_username = sessions.get(chat_id, "username")
            sessions.pop(chat_id, "remove_school_member_stage", None)
            sessions.pop(chat_id, "remove_school_member_list", None)
            if not (school_id and owner_username):
                bot.send_message(chat_id, "خطا — اطلاعات ناقص.", reply_markup=get_keyboard_for_chat(chat_id))
                return
            target_school = db.get_school(school_id)
            if target_school and target_school.get("owner") == member_username:
                bot.send_message(chat_id, "نمی‌توانید مالک آموزشگاه را حذف کنید.", reply_markup=get_keyboard_for_chat(chat_id))
                return
            sessions.set(chat_id, "confirm_delete_target", ("school_member", school_id, member_username))
            bot.send_message(chat_id, f"آیا از حذف {member_username} از آموزشگاه مطمئنی؟", reply_markup=make_keyboard([[LABEL_CONFIRM_DELETE, LABEL_CANCEL]]))
            return

   
    if btn == LABEL_CONFIRM_DELETE:
        target = sessions.get(chat_id, "confirm_delete_target")
        if not target:
            bot.send_message(chat_id, "چیزی برای حذف انتخاب نشده است.", reply_markup=get_keyboard_for_chat(chat_id))
            return
        ttype = target[0]
        try:
            if ttype == "student":
                sid = target[1]
                deleted = db.delete_student(sid)
                sessions.pop(chat_id, "confirm_delete_target", None)
                if sessions.get(chat_id, "selected_student") == sid:
                    sessions.pop(chat_id, "selected_student", None)
                if deleted:
                    bot.send_message(chat_id, f"✅ دانش‌آموز {sid} حذف شد.", reply_markup=get_keyboard_for_chat(chat_id))
                else:
                    bot.send_message(chat_id, "⚠️ حذف موفق نبود.", reply_markup=get_keyboard_for_chat(chat_id))
                return
            if ttype == "class":
                class_id = target[1]
                deleted = db.delete_class(class_id)
                sessions.pop(chat_id, "confirm_delete_target", None)
                if sessions.get(chat_id, "selected_class") == class_id:
                    sessions.pop(chat_id, "selected_class", None)
                if deleted:
                    bot.send_message(chat_id, f"✅ کلاس {class_id} حذف شد.", reply_markup=get_keyboard_for_chat(chat_id))
                else:
                    bot.send_message(chat_id, "⚠️ حذف کلاس موفق نبود.", reply_markup=get_keyboard_for_chat(chat_id))
                return
            if ttype == "school_member":
                _, school_id, member_username = target
                removed = db.remove_member_from_school(school_id, member_username)
                sessions.pop(chat_id, "confirm_delete_target", None)
                if removed:
                    bot.send_message(chat_id, f"✅ {member_username} از آموزشگاه حذف شد.", reply_markup=get_keyboard_for_chat(chat_id))
                else:
                    bot.send_message(chat_id, "⚠️ حذف عضو موفق نبود.", reply_markup=get_keyboard_for_chat(chat_id))
                return
            if ttype == "class_member":
                _, class_id, sid = target
                removed = db.remove_member_from_class(class_id, sid)
                sessions.pop(chat_id, "confirm_delete_target", None)
                if removed:
                    bot.send_message(chat_id, f"✅ دانش‌آموز {sid} از کلاس حذف شد.", reply_markup=get_keyboard_for_chat(chat_id))
                    show_class_profile(chat_id, class_id)
                else:
                    bot.send_message(chat_id, "⚠️ حذف از کلاس موفق نبود.", reply_markup=get_keyboard_for_chat(chat_id))
                    show_class_profile(chat_id, class_id)
                return
            if ttype == "school":
                _, school_id = target
                deleted = db.delete_school(school_id)
                sessions.pop(chat_id, "confirm_delete_target", None)
                if sessions.get(chat_id, "selected_school") == school_id:
                    sessions.pop(chat_id, "selected_school", None)
                if deleted:
                    bot.send_message(chat_id, f"✅ آموزشگاه {school_id} حذف شد.", reply_markup=get_keyboard_for_chat(chat_id))
                else:
                    bot.send_message(chat_id, "⚠️ حذف آموزشگاه موفق نبود.", reply_markup=get_keyboard_for_chat(chat_id))
                return
        except Exception as e:
            logger.exception("error in confirm delete: %s", e)
            bot.send_message(chat_id, "⚠️ خطا در اجرای حذف.", reply_markup=get_keyboard_for_chat(chat_id))
            sessions.pop(chat_id, "confirm_delete_target", None)
            return

  
    if btn == LABEL_DELETE_SCHOOL:
        school_id = sessions.get(chat_id, "selected_school")
        username = sessions.get(chat_id, "username")
        if not (school_id and username):
            bot.send_message(chat_id, "⚠️ ابتدا یک آموزشگاه انتخاب کنید.", reply_markup=get_keyboard_for_chat(chat_id))
            return
        s = db.get_school(school_id)
        if not s:
            bot.send_message(chat_id, "⚠️ آموزشگاه پیدا نشد.", reply_markup=get_keyboard_for_chat(chat_id))
            return
        if s.get("owner") != username:
            bot.send_message(chat_id, "⚠️ فقط مالک آموزشگاه می‌تواند آن را حذف کند.", reply_markup=get_keyboard_for_chat(chat_id))
            return
        sessions.set(chat_id, "confirm_delete_target", ("school", school_id))
        bot.send_message(chat_id, f"آیا از حذف کامل آموزشگاه «{s.get('name')}» (ID: {school_id}) مطمئنی؟ این کار همهٔ اعضا را حذف می‌کند.", reply_markup=make_keyboard([[LABEL_CONFIRM_DELETE, LABEL_CANCEL]]))
        return

    
    bot.send_message(chat_id, "❗️ دستور ناشناخته — لطفاً از منو استفاده کنید یا «انصراف» را بزنید.", reply_markup=get_keyboard_for_chat(chat_id))
    return


def run_polling():
    backoff = 1
    while True:
        try:
            logger.info("شروع polling...")
            bot.polling(none_stop=True)
        except Exception as e:
            logger.exception("خطا در polling: %s", e)
            time.sleep(backoff)
            backoff = min(30, backoff * 2)


if __name__ == "__main__":
    run_polling()
