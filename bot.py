# main.py
import os
import json
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# -----------------------
# Config (set these in repl secrets / env vars)
# -----------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")  # توکن بات بله
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))  # آیدی تلگرامت/باله اونری که پنل داره
BASE_URL = f"https://tapi.bale.ai/bot{BOT_TOKEN}/"  # نمونه endpoint طبق مثال قبلی

DATA_FILE = "data.json"

# -----------------------
# In-memory caches / state
# -----------------------
# کاربران و کدها و فایل‌ها و گایدها در data.json ذخیره میشن
data = {
    "activation_codes": {
        # نمونه اولیه؛ میتونی از پنل ادمین حذف/اضافه کنی
        "12345": {"org": "ORG1", "role": "STUDENT", "used": False},
        "99999": {"org": "ORG1", "role": "ADMIN", "used": False}
    },
    "users": {
        # "123456": {"user_id": 123456, "org": "ORG1", "role": "STUDENT", "name": "Amir"}
    },
    "guides": [
        # {"id": 1, "title": "نحوه دانلود", "content": "روی لینک کلیک کنید ..."}
    ],
    "files": [
        # {"id":1, "title":"ریاضی فصل ۱", "url":"https://...", "org":"ORG1", "role":"STUDENT"}
    ],
    "states": {
        # "123456": {"action":"adding_guide_title", "temp":{}}
    },
    "next_ids": {"guide": 1, "file": 1}
}

# -----------------------
# Helpers: load/save
# -----------------------
def load_data():
    global data
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print("load_data error:", e)
            # keep defaults
    else:
        save_data()

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# initially load
load_data()

# -----------------------
# Bale API helpers (basic)
# -----------------------
def api_post(method, payload):
    url = BASE_URL + method
    try:
        res = requests.post(url, data=payload, timeout=15)
        return res
    except Exception as e:
        print("api_post error:", e)
        return None

def send_message(chat_id, text, keyboard=None):
    payload = {"chat_id": chat_id, "text": text}
    if keyboard:
        payload["reply_markup"] = json.dumps(keyboard, ensure_ascii=False)
    return api_post("sendMessage", payload)

def edit_message_text(chat_id, message_id, text, keyboard=None):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text}
    if keyboard:
        payload["reply_markup"] = json.dumps(keyboard, ensure_ascii=False)
    return api_post("editMessageText", payload)

def answer_callback(callback_id, text=None):
    payload = {"callback_query_id": callback_id}
    if text:
        payload["text"] = text
    return api_post("answerCallbackQuery", payload)

# -----------------------
# Keyboards
# -----------------------
def main_menu_keyboard(is_admin=False):
    kb = {
        "inline_keyboard": [
            [{"text": "📂 فایل‌ها", "callback_data": "files"}],
            [{"text": "📘 راهنما", "callback_data": "guides"}],
            [{"text": "👤 پروفایل من", "callback_data": "profile"}]
        ]
    }
    if is_admin:
        kb["inline_keyboard"].append([{"text": "🛠 پنل ادمین", "callback_data": "admin_panel"}])
    return kb

def files_list_keyboard(files):
    kb = {"inline_keyboard": []}
    for f in files:
        kb["inline_keyboard"].append([{"text": f["title"], "url": f["url"]}])
    kb["inline_keyboard"].append([{"text": "🔙 بازگشت", "callback_data": "main"}])
    return kb

def guides_list_keyboard(guides):
    kb = {"inline_keyboard": []}
    for g in guides:
        kb["inline_keyboard"].append([{"text": g["title"], "callback_data": f"guide_{g['id']}"}])
    kb["inline_keyboard"].append([{"text": "🔙 بازگشت", "callback_data": "main"}])
    return kb

def admin_panel_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "➕ افزودن راهنما", "callback_data": "admin_add_guide"}],
            [{"text": "➕ افزودن فایل", "callback_data": "admin_add_file"}],
            [{"text": "📋 لیست راهنماها", "callback_data": "admin_list_guides"}],
            [{"text": "📂 لیست فایل‌ها", "callback_data": "admin_list_files"}],
            [{"text": "🔙 بازگشت", "callback_data": "main"}]
        ]
    }

# -----------------------
# Utility
# -----------------------
def is_owner(user_id):
    try:
        return int(user_id) == int(OWNER_ID)
    except:
        return False

def register_user(user_id, name, org, role):
    uid = str(user_id)
    data["users"][uid] = {"user_id": user_id, "name": name, "org": org, "role": role}
    save_data()

def find_files_for_user(user):
    res = []
    for f in data["files"]:
        if f.get("org") == user.get("org"):
            # if role matches or role is None (public)
            if (f.get("role") is None) or (f.get("role") == user.get("role")):
                res.append(f)
    return res

# -----------------------
# Webhook / Routes
# -----------------------
@app.route("/", methods=["GET"])
def home():
    return "پل bot is alive"

@app.route("/ping", methods=["GET"])
def ping():
    return "pong"

@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.get_json(force=True)
    # handle message
    if "message" in payload:
        msg = payload["message"]
        chat_id = msg["chat"]["id"]
        from_user = msg.get("from", {})
        user_id = from_user.get("id")
        name = from_user.get("first_name", "") + (" " + from_user.get("last_name", "") if from_user.get("last_name") else "")
        text = msg.get("text", "")

        uid = str(user_id)

        # If user is in a state (admin flows)
        state = data["states"].get(uid)
        if state:
            action = state.get("action")
            if action == "adding_guide_title" and is_owner(user_id):
                # store title temporarily
                data["states"][uid] = {"action": "adding_guide_content", "temp": {"title": text}}
                save_data()
                send_message(chat_id, "عنوان راهنما ثبت شد. حالا محتوای راهنما را ارسال کنید (متن).")
                return jsonify({"ok": True})
            if action == "adding_guide_content" and is_owner(user_id):
                title = state["temp"].get("title")
                content = text
                gid = data["next_ids"]["guide"]
                data["guides"].append({"id": gid, "title": title, "content": content})
                data["next_ids"]["guide"] += 1
                data["states"].pop(uid, None)
                save_data()
                send_message(chat_id, f"راهنما با عنوان «{title}» اضافه شد.", keyboard=main_menu_keyboard(is_admin=True))
                return jsonify({"ok": True})
            if action == "adding_file_title" and is_owner(user_id):
                data["states"][uid] = {"action": "adding_file_url", "temp": {"title": text}}
                save_data()
                send_message(chat_id, "عنوان فایل ثبت شد. حالا لینک مستقیم فایل (URL) را ارسال کنید.")
                return jsonify({"ok": True})
            if action == "adding_file_url" and is_owner(user_id):
                temp = state["temp"]
                title = temp.get("title")
                url = text.strip()
                fid = data["next_ids"]["file"]
                # default org and role - owner can later edit if you add UI
                data["files"].append({"id": fid, "title": title, "url": url, "org": "ORG1", "role": None})
                data["next_ids"]["file"] += 1
                data["states"].pop(uid, None)
                save_data()
                send_message(chat_id, f"فایل «{title}» با لینک اضافه شد.", keyboard=main_menu_keyboard(is_admin=True))
                return jsonify({"ok": True})

        # Normal flows:
        # /start param (activation via link)
        if text and text.strip().startswith("/start"):
            parts = text.strip().split()
            # sometimes start param after /start=CODE or /start CODE
            code = None
            if len(parts) > 1:
                code = parts[1].strip()
            else:
                # try /startCODE
                t = text.strip()
                if t.startswith("/start="):
                    code = t.split("=",1)[1]
            if code:
                ac = data["activation_codes"].get(code)
                if ac and not ac.get("used"):
                    register_user(user_id, name or "کاربر", ac["org"], ac["role"])
                    data["activation_codes"][code]["used"] = True
                    save_data()
                    send_message(chat_id, f"اکانت فعال شد. سازمان: {ac['org']} | رول: {ac['role']}", keyboard=main_menu_keyboard(is_admin=is_owner(user_id)))
                else:
                    send_message(chat_id, "کد فعالسازی نامعتبر یا قبلاً استفاده شده است.\nاگر کد دارید، آن را تایپ کنید یا از پنل ادمین کمک بگیرید.", keyboard=main_menu_keyboard(is_admin=is_owner(user_id)))
                return jsonify({"ok": True})

        # If user sent a code directly (allowed)
        if text and text.strip() in data["activation_codes"]:
            code = text.strip()
            ac = data["activation_codes"].get(code)
            if ac and not ac.get("used"):
                register_user(user_id, name or "کاربر", ac["org"], ac["role"])
                data["activation_codes"][code]["used"] = True
                save_data()
                send_message(chat_id, f"اکانت فعال شد. سازمان: {ac['org']} | رول: {ac['role']}", keyboard=main_menu_keyboard(is_admin=is_owner(user_id)))
            else:
                send_message(chat_id, "کد فعالسازی نامعتبر یا قبلاً استفاده شده است.", keyboard=main_menu_keyboard(is_admin=is_owner(user_id)))
            return jsonify({"ok": True})

        # else: show main menu
        user = data["users"].get(uid)
        is_admin_flag = (user and user.get("role") == "ADMIN") or is_owner(user_id)
        send_message(chat_id, f"سلام {name or ''} — خوش آمدی به پل.", keyboard=main_menu_keyboard(is_admin=is_admin_flag))
        return jsonify({"ok": True})

    # handle callback_query (دکمه شیشه‌ای)
    if "callback_query" in payload:
        cq = payload["callback_query"]
        callback_id = cq.get("id")
        from_user = cq.get("from", {})
        user_id = from_user.get("id")
        uid = str(user_id)
        data_payload = cq.get("data", "")
        message = cq.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        message_id = message.get("message_id")

        # answer to remove loading
        answer_callback(callback_id)

        # main
        if data_payload == "main":
            user = data["users"].get(uid)
            is_admin_flag = (user and user.get("role") == "ADMIN") or is_owner(user_id)
            edit_message_text(chat_id, message_id, "منوی اصلی:", keyboard=main_menu_keyboard(is_admin=is_admin_flag))
            return jsonify({"ok": True})

        if data_payload == "files":
            user = data["users"].get(uid)
            if not user:
                send_message(chat_id, "ابتدا باید با کد فعالسازی وارد شوید.", keyboard=main_menu_keyboard(is_admin=is_owner(user_id)))
                return jsonify({"ok": True})
            files = find_files_for_user(user)
            if not files:
                edit_message_text(chat_id, message_id, "فایلی برای شما موجود نیست.", keyboard=main_menu_keyboard(is_admin=is_owner(user_id)))
                return jsonify({"ok": True})
            kb = files_list_keyboard(files)
            edit_message_text(chat_id, message_id, "فایل‌های در دسترس:", keyboard=kb)
            return jsonify({"ok": True})

        if data_payload == "guides":
            if not data["guides"]:
                edit_message_text(chat_id, message_id, "راهنمایی موجود نیست.", keyboard=main_menu_keyboard(is_admin=is_owner(user_id)))
                return jsonify({"ok": True})
            kb = guides_list_keyboard(data["guides"])
            edit_message_text(chat_id, message_id, "راهنماها:", keyboard=kb)
            return jsonify({"ok": True})

        if data_payload.startswith("guide_"):
            gid = int(data_payload.split("_",1)[1])
            g = next((x for x in data["guides"] if x["id"] == gid), None)
            if g:
                edit_message_text(chat_id, message_id, f"📘 {g['title']}\n\n{g['content']}", keyboard={"inline_keyboard":[[{"text":"🔙 بازگشت","callback_data":"guides"}]]})
            else:
                answer_callback(callback_id, "راهنما پیدا نشد.")
            return jsonify({"ok": True})

        # admin panel
        if data_payload == "admin_panel" and is_owner(user_id):
            edit_message_text(chat_id, message_id, "پنل ادمین:", keyboard=admin_panel_keyboard())
            return jsonify({"ok": True})

        if data_payload == "admin_add_guide" and is_owner(user_id):
            data["states"][uid] = {"action": "adding_guide_title", "temp": {}}
            save_data()
            send_message(chat_id, "لطفاً عنوان راهنما را ارسال کنید (این پیام را تایپ کنید).")
            return jsonify({"ok": True})

        if data_payload == "admin_add_file" and is_owner(user_id):
            data["states"][uid] = {"action": "adding_file_title", "temp": {}}
            save_data()
            send_message(chat_id, "لطفاً عنوان فایل را ارسال کنید.")
            return jsonify({"ok": True})

        if data_payload == "admin_list_guides" and is_owner(user_id):
            if not data["guides"]:
                edit_message_text(chat_id, message_id, "راهنمایی موجود نیست.", keyboard=admin_panel_keyboard())
                return jsonify({"ok": True})
            text = "لیست راهنماها:\n" + "\n".join([f"- {g['id']}: {g['title']}" for g in data["guides"]])
            edit_message_text(chat_id, message_id, text, keyboard=admin_panel_keyboard())
            return jsonify({"ok": True})

        if data_payload == "admin_list_files" and is_owner(user_id):
            if not data["files"]:
                edit_message_text(chat_id, message_id, "فایلی موجود نیست.", keyboard=admin_panel_keyboard())
                return jsonify({"ok": True})
            text = "لیست فایل‌ها:\n" + "\n".join([f"- {f['id']}: {f['title']} ({f['url']})" for f in data["files"]])
            edit_message_text(chat_id, message_id, text, keyboard=admin_panel_keyboard())
            return jsonify({"ok": True})

        # default fallback
        answer_callback(callback_id, "عملیات نامشخص.")
        return jsonify({"ok": True})

    return jsonify({"ok": True})

# -----------------------
# Run (for Replit default)
# -----------------------
if __name__ == "__main__":
    # port = int(os.environ.get("PORT", 5000))
    # app.run(host="0.0.0.0", port=port)
    app.run(host="0.0.0.0", port=8080)
