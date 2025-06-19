import requests
from bs4 import BeautifulSoup
import time
import os
from flask import Flask
from threading import Thread
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_CHAT_ID = os.getenv("OWNER_CHAT_ID")

TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
SEND_MSG_URL = f"{TELEGRAM_URL}/sendMessage"
GET_UPDATES_URL = f"{TELEGRAM_URL}/getUpdates"

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

app = Flask('')

@app.route('/')
def home():
    return "✅ Bot is running."

def run_web():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

def send_telegram(chat_id, text):
    requests.post(SEND_MSG_URL, data={"chat_id": chat_id, "text": text})

def extract_hidden_fields(html):
    soup = BeautifulSoup(html, 'html.parser')
    return {
        '__VIEWSTATE': soup.find('input', {'name': '__VIEWSTATE'}).get('value'),
        '__VIEWSTATEGENERATOR': soup.find('input', {'name': '__VIEWSTATEGENERATOR'}).get('value'),
        '__EVENTVALIDATION': soup.find('input', {'name': '__EVENTVALIDATION'}).get('value')
    }

def check_for_commands():
    global last_update_id
    try:
        resp = requests.get(GET_UPDATES_URL).json()
        updates = resp.get("result", [])
        for update in reversed(updates):
            msg = update.get("message", {})
            text = msg.get("text", "").strip()
            chat_id = str(msg.get("chat", {}).get("id"))
            update_id = update["update_id"]

            if last_update_id is None or update_id > last_update_id:
                last_update_id = update_id
                if chat_id not in users:
                    users[chat_id] = {'username': None, 'password': None, 'course': None, 'monitoring': False}

                user = users[chat_id]

                if text.lower() == "/start":
                    user['monitoring'] = True
                    if not user['username']:
                        send_telegram(chat_id, "🔐 Please enter your ARMS username:")
                    elif not user['password']:
                        send_telegram(chat_id, "🔐 Please enter your ARMS password:")
                    elif not user['course']:
                        send_telegram(chat_id, "📘 Please enter the course code to monitor:")
                    else:
                        send_telegram(chat_id, f"📌 Monitoring course: {user['course']}")

                elif text.lower() == "/stop":
                    user['monitoring'] = False
                    send_telegram(chat_id, "🛑 Monitoring stopped.")

                elif text.lower() == "/logout":
                    users.pop(chat_id)
                    send_telegram(chat_id, "🔒 You have been logged out. Send /start to login again.")

                elif text.lower() == "/empty":
                    send_telegram(chat_id, "🧹 Chat cleared.")

                elif user['monitoring']:
                    if not user['username']:
                        user['username'] = text
                        send_telegram(chat_id, "🔐 Please enter your ARMS password:")
                    elif not user['password']:
                        user['password'] = text
                        send_telegram(chat_id, "📘 Please enter the course code to monitor:")
                    elif not user['course']:
                        user['course'] = text.upper()
                        send_telegram(chat_id, f"📌 Monitoring course: {user['course']}")

    except Exception as e:
        print("Error checking commands:", e)

def check_course(user, chat_id):
    session = requests.Session()
    login_url = "https://arms.sse.saveetha.com/"
    enrollment_url = "https://arms.sse.saveetha.com/StudentPortal/Enrollment.aspx"
    api_base = "https://arms.sse.saveetha.com/Handler/Student.ashx?Page=StudentInfobyId&Mode=GetCourseBySlot&Id="

    try:
        resp = session.get(login_url)
        fields = extract_hidden_fields(resp.text)

        payload = {
            **fields,
            'txtusername': user['username'],
            'txtpassword': user['password'],
            'btnlogin': 'Login'
        }

        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': login_url
        }

        login_resp = session.post(login_url, data=payload, headers=headers)
        if "Logout" not in login_resp.text:
            send_telegram(chat_id, "❌ Login failed. Please check your credentials and send /logout.")
            return False

        enroll_resp = session.get(enrollment_url)
        if "Enrollment" not in enroll_resp.text:
            send_telegram(chat_id, "❌ Failed to load enrollment page.")
            return False

        found_slot = None
        for slot_name, slot_id in slot_map.items():
            api_url = api_base + slot_id
            response = session.get(api_url)
            if response.status_code == 200 and user['course'] in response.text:
                found_slot = slot_name
                break

        if found_slot:
            send_telegram(chat_id, f"🔄 Checking course: {user['course']}")
            send_telegram(chat_id, f"🎯 Found in Slot {found_slot}!")
            return True
        else:
            send_telegram(chat_id, f"🔄 Checking course: {user['course']}")
            send_telegram(chat_id, "❌ Not found in any slot.")
            return False


    except Exception as e:
        send_telegram(chat_id, f"⚠️ Error: {e}")
        return False

send_telegram(OWNER_CHAT_ID, "🤖 Bot deployed. Send /start to begin.")
keep_alive()

while True:
    check_for_commands()
    for chat_id, user in users.items():
        if user['monitoring'] and user['username'] and user['password'] and user['course']:
            result = check_course(user, chat_id)
            if result:
                user['course'] = None
    time.sleep(900)
