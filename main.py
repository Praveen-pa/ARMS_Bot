import os
import time
import json
import requests
from bs4 import BeautifulSoup
from flask import Flask
from threading import Thread

# Load Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# State storage
user_states = {}

# Slot ID mapping
slot_map = {
    'O': '15',
    'P': '16',
    'Q': '17',
    'R': '18',
    'S': '19',
    'T': '20'
}

def send_telegram(chat_id, text):
    requests.post(f"{TELEGRAM_API}/sendMessage", data={"chat_id": chat_id, "text": text})

def check_for_updates():
    global last_update_id
    try:
        res = requests.get(f"{TELEGRAM_API}/getUpdates", timeout=5)
        updates = res.json().get("result", [])
        for update in updates:
            message = update.get("message", {})
            chat_id = str(message.get("chat", {}).get("id"))
            text = message.get("text", "").strip()
            update_id = update["update_id"]

            if "last_update_id" not in user_states:
                user_states["last_update_id"] = 0

            if update_id <= user_states["last_update_id"]:
                continue

            user_states["last_update_id"] = update_id
            handle_message(chat_id, text)

    except Exception as e:
        print(f"Update check error: {e}")

def handle_message(chat_id, text):
    state = user_states.get(chat_id, {
        "monitoring": False,
        "step": None,
        "username": None,
        "password": None,
        "course": None
    })

    if text.lower() == "/start":
        if not state["username"]:
            state["step"] = "awaiting_password"
            send_telegram(chat_id, "🔐 Please enter your ARMS password:")
        else:
            state["step"] = "awaiting_course"
            send_telegram(chat_id, "🤖 Monitoring started. Please enter the course code (e.g. ECA20):")
        state["monitoring"] = True

    elif text.lower() == "/stop":
        state["monitoring"] = False
        state["course"] = None
        state["step"] = None
        send_telegram(chat_id, "🛑 Monitoring stopped.")

    elif text.lower() == "/logout":
        user_states.pop(chat_id, None)
        send_telegram(chat_id, "🔓 Logged out. Send /start to begin again.")

    elif text.lower() == "/empty":
        send_telegram(chat_id, "🧹 Chat cleared.")

    elif state["step"] == "awaiting_password":
        state["password"] = text
        state["step"] = "awaiting_course"
        send_telegram(chat_id, "📘 Please enter the course code to monitor:")

    elif state["step"] == "awaiting_course":
        state["course"] = text.upper()
        send_telegram(chat_id, f"📌 Monitoring course: {state['course']}")

    user_states[chat_id] = state

def check_course(chat_id):
    state = user_states[chat_id]
    course_code = state["course"]
    username = state["username"]
    password = state["password"]

    session = requests.Session()
    try:
        login_url = "https://arms.sse.saveetha.com/"
        enrollment_url = "https://arms.sse.saveetha.com/StudentPortal/Enrollment.aspx"
        api_base = "https://arms.sse.saveetha.com/Handler/Student.ashx?Page=StudentInfobyId&Mode=GetCourseBySlot&Id="

        soup = BeautifulSoup(session.get(login_url).text, "html.parser")
        payload = {
            '__VIEWSTATE': soup.find('input', {'name': '__VIEWSTATE'}).get('value'),
            '__VIEWSTATEGENERATOR': soup.find('input', {'name': '__VIEWSTATEGENERATOR'}).get('value'),
            '__EVENTVALIDATION': soup.find('input', {'name': '__EVENTVALIDATION'}).get('value'),
            'txtusername': username,
            'txtpassword': password,
            'btnlogin': 'Login'
        }

        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': login_url
        }

        login_resp = session.post(login_url, data=payload, headers=headers)
        if "Logout" not in login_resp.text:
            send_telegram(chat_id, "❌ Login failed.")
            return

        enroll_resp = session.get(enrollment_url)
        if "Enrollment" not in enroll_resp.text:
            send_telegram(chat_id, "❌ Enrollment page failed.")
            return

        found = False
        for slot, slot_id in slot_map.items():
            r = session.get(api_base + slot_id)
            if course_code in r.text:
                send_telegram(chat_id, f"🔄 Checking course: {course_code}\n🎯 Found in Slot {slot}!")
                found = True
                break

        if not found:
            send_telegram(chat_id, f"🔄 Checking course: {course_code}\n❌ Not found in any slot.")

        if found:
            send_telegram(chat_id, f"✅ Monitoring complete for {course_code}. Send a new course or /stop.")
            user_states[chat_id]["course"] = None
            user_states[chat_id]["step"] = "awaiting_course"

    except Exception as e:
        send_telegram(chat_id, f"⚠️ Error occurred: {e}")

def monitor_loop():
    while True:
        check_for_updates()
        for chat_id, state in list(user_states.items()):
            if isinstance(state, dict) and state.get("monitoring") and state.get("course") and state.get("username") and state.get("password"):
                check_course(chat_id)
        time.sleep(900)  # 15 minutes

# Flask for Railway health check
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot is alive"

def run_web():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    Thread(target=run_web).start()

keep_alive()
send_telegram(os.getenv("ADMIN_CHAT_ID", ""), "🤖 Bot deployed. Send /start to begin.")
monitor_loop()
