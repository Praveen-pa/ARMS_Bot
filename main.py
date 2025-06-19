import os
import time
import requests
from bs4 import BeautifulSoup
from flask import Flask
from threading import Thread

# ENV VARIABLES
BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
SEND_MSG_URL = f"{TELEGRAM_URL}/sendMessage"
GET_UPDATES_URL = f"{TELEGRAM_URL}/getUpdates"

# TRACK USERS: chat_id => user_data
users = {}
last_update_id = None

slot_map = {
    'O': '15',
    'P': '16',
    'Q': '17',
    'R': '18',
    'S': '19',
    'T': '20'
}

# Telegram send message
def send_telegram(chat_id, text):
    requests.post(SEND_MSG_URL, data={"chat_id": chat_id, "text": text})

# Check Telegram messages
def check_for_commands():
    global last_update_id

    try:
        resp = requests.get(GET_UPDATES_URL).json()
        updates = resp.get("result", [])

        for update in reversed(updates):
            msg = update.get("message", {})
            chat_id = msg.get("chat", {}).get("id")
            text = msg.get("text", "").strip()
            update_id = update["update_id"]

            if last_update_id is None or update_id > last_update_id:
                last_update_id = update_id
                handle_user_input(chat_id, text)

    except Exception as e:
        print(f"[Error] Telegram polling failed: {e}")

# Handle user commands and input flow
def handle_user_input(chat_id, text):
    user = users.get(chat_id)

    if text.lower() == "/start":
        if not user:
            users[chat_id] = {"step": "awaiting_username", "monitoring": False}
            send_telegram(chat_id, "🔐 Please enter your ARMS username:")
        else:
            users[chat_id]["monitoring"] = True
            users[chat_id]["step"] = "awaiting_course"
            send_telegram(chat_id, "🤖 Monitoring started. Please enter the course code (e.g. ECA20):")

    elif text.lower() == "/stop":
        if user:
            user["monitoring"] = False
        send_telegram(chat_id, "🛑 Monitoring stopped.")

    elif text.lower() == "/logout":
        users.pop(chat_id, None)
        send_telegram(chat_id, "🔓 You have been logged out. Send /start to begin again.")

    elif text.lower() == "/empty":
        send_telegram(chat_id, "🧹 Chat cleared.")
        # Optional: Add command to delete messages via Telegram Bot API if needed

    elif user:
        step = user.get("step")
        if step == "awaiting_username":
            user["username"] = text
            user["step"] = "awaiting_password"
            send_telegram(chat_id, "🔐 Now enter your ARMS password:")
        elif step == "awaiting_password":
            user["password"] = text
            user["step"] = "awaiting_course"
            send_telegram(chat_id, "✅ Login saved. Now enter the course code:")
        elif step == "awaiting_course":
            user["course"] = text.upper()
            user["monitoring"] = True
            send_telegram(chat_id, f"📌 Monitoring course: {user['course']}")
        else:
            # Ignore extra input
            pass

# Check course for all users
def check_courses_for_all_users():
    for chat_id, user in users.items():
        if user.get("monitoring") and all(k in user for k in ["username", "password", "course"]):
            found = check_course(user["username"], user["password"], user["course"])
            if found:
                send_telegram(chat_id, f"🎯 Found {user['course']} in Slot {found}!")
                user["monitoring"] = True
                user["step"] = "awaiting_course"
                send_telegram(chat_id, "✅ Monitoring complete. Send next course or /stop.")
            else:
                send_telegram(chat_id, f"❌ {user['course']} not found in any slot.")

# Course checking logic (reusable)
def check_course(username, password, course_code):
    session = requests.Session()
    try:
        login_url = "https://arms.sse.saveetha.com/"
        enroll_url = "https://arms.sse.saveetha.com/StudentPortal/Enrollment.aspx"
        api_base = "https://arms.sse.saveetha.com/Handler/Student.ashx?Page=StudentInfobyId&Mode=GetCourseBySlot&Id="

        # Login
        login_page = session.get(login_url)
        soup = BeautifulSoup(login_page.text, 'html.parser')
        payload = {
            '__VIEWSTATE': soup.find('input', {'name': '__VIEWSTATE'}).get('value'),
            '__VIEWSTATEGENERATOR': soup.find('input', {'name': '__VIEWSTATEGENERATOR'}).get('value'),
            '__EVENTVALIDATION': soup.find('input', {'name': '__EVENTVALIDATION'}).get('value'),
            'txtusername': username,
            'txtpassword': password,
            'btnlogin': 'Login'
        }

        headers = {'User-Agent': 'Mozilla/5.0'}
        login_resp = session.post(login_url, data=payload, headers=headers)
        if "Logout" not in login_resp.text:
            return False

        session.get(enroll_url)  # Go to enrollment page

        for slot_name, slot_id in slot_map.items():
            api_url = api_base + slot_id
            resp = session.get(api_url)
            if course_code in resp.text:
                return slot_name
        return False
    except Exception as e:
        print(f"[Course Check Error] {e}")
        return False

# Flask Keep-Alive
app = Flask('')

@app.route('/')
def home():
    return "✅ Multi-User ARMS Bot Running"

def run_web():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# Main loop
keep_alive()
send_telegram(os.getenv("CHAT_ID"), "🤖 Multi-user ARMS bot is live. Send /start to begin.")

while True:
    check_for_commands()
    check_courses_for_all_users()
    time.sleep(900)  # Every 15 minutes
