
import os
import re
import sqlite3
import threading
import time
import requests
import telebot

from http.server import HTTPServer, BaseHTTPRequestHandler
from telebot.apihelper import ApiTelegramException


# ==========================================
# CONFIGURATION
# ==========================================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")

ADMIN_ID = 5989928539

APP_URL = "https://osint-kblt.onrender.com"

BROADCAST_DELAY = 0.1
MAX_RETRIES = 5

bot = telebot.TeleBot(BOT_TOKEN)


# ==========================================
# DATABASE SETUP
# ==========================================

def init_db():

    conn = sqlite3.connect("users.db", timeout=30)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            status TEXT DEFAULT 'active'
        )
    """)

    conn.commit()
    conn.close()

    print("DATABASE INITIALIZED")


def add_user(user_id, first_name):

    conn = sqlite3.connect("users.db", timeout=30)

    try:
        c = conn.cursor()

        c.execute("""
            INSERT OR IGNORE INTO users
            (user_id, first_name, status)
            VALUES (?, ?, 'active')
        """, (user_id, first_name))

        c.execute("""
            UPDATE users
            SET first_name = ?, status = 'active'
            WHERE user_id = ?
        """, (first_name, user_id))

        conn.commit()

    finally:
        conn.close()


def get_all_users():

    conn = sqlite3.connect("users.db", timeout=30)

    try:
        c = conn.cursor()

        c.execute("""
            SELECT user_id
            FROM users
            WHERE status = 'active'
        """)

        return [row[0] for row in c.fetchall()]

    finally:
        conn.close()


def mark_user_blocked(user_id):

    conn = sqlite3.connect("users.db", timeout=30)

    try:
        c = conn.cursor()

        c.execute("""
            UPDATE users
            SET status = 'blocked'
            WHERE user_id = ?
        """, (user_id,))

        conn.commit()

    finally:
        conn.close()


def get_database_stats():

    conn = sqlite3.connect("users.db", timeout=30)

    try:
        c = conn.cursor()

        c.execute("SELECT COUNT(*) FROM users")
        total = c.fetchone()[0]

        c.execute("""
            SELECT COUNT(*) FROM users
            WHERE status = 'active'
        """)
        active = c.fetchone()[0]

        c.execute("""
            SELECT COUNT(*) FROM users
            WHERE status = 'blocked'
        """)
        blocked = c.fetchone()[0]

        return total, active, blocked

    finally:
        conn.close()


# ==========================================
# KEEPALIVE SERVER
# ==========================================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        self.send_response(200)

        self.send_header(
            "Content-Type",
            "text/plain"
        )

        self.end_headers()

        self.wfile.write(
            b"Bot is running successfully!"
        )

    def log_message(self, format, *args):
        pass


def start_keepalive_server():

    port = int(os.environ.get("PORT", 10000))

    server = HTTPServer(
        ("0.0.0.0", port),
        HealthHandler
    )

    print(f"KEEPALIVE SERVER RUNNING ON PORT {port}")

    server.serve_forever()


def run_keepalive_in_thread():

    threading.Thread(
        target=start_keepalive_server,
        daemon=True
    ).start()


# ==========================================
# SELF PING
# ==========================================

def self_ping():

    while True:

        try:

            time.sleep(300)

            response = requests.get(
                APP_URL,
                timeout=20
            )

            print(
                f"SELF PING: {response.status_code}"
            )

        except Exception as e:

            print(f"SELF PING ERROR: {e}")


def run_self_ping_in_thread():

    threading.Thread(
        target=self_ping,
        daemon=True
    ).start()


# ==========================================
# SILENT JOIN REQUEST HANDLER
# ==========================================

@bot.chat_join_request_handler()
def accept_join_request(message):

    try:

        user_id = message.from_user.id

        first_name = (
            message.from_user.first_name or "User"
        )

        # Only save user information
        add_user(user_id, first_name)

        # No approval
        # No rejection
        # No welcome message

        print(
            f"JOIN REQUEST SAVED: {user_id}"
        )

    except Exception as e:

        print(
            f"JOIN REQUEST SAVE ERROR: {e}"
        )


# ==========================================
# START COMMAND
# ==========================================

@bot.message_handler(commands=["start"])
def send_welcome(message):

    user_id = message.from_user.id

    first_name = (
        message.from_user.first_name or "User"
    )

    try:

        add_user(user_id, first_name)

        if user_id == ADMIN_ID:

            bot.reply_to(
                message,
                "Hello Admin! ✅\n\n"
                "Bot is working successfully!\n\n"
                "Available Commands:\n\n"
                "/start - Start Bot\n"
                "/status - Database Status\n"
                "/broadcast - Send Broadcast\n"
                "/myid - Check Telegram ID"
            )

            print(
                f"ADMIN START COMMAND: {user_id}"
            )

        else:

            bot.reply_to(
                message,
                "👋 Hey! Welcome!\n"
                "Bot is working successfully."
            )

    except Exception as e:

        print(f"START COMMAND ERROR: {e}")


# ==========================================
# MY ID COMMAND
# ==========================================

@bot.message_handler(commands=["myid"])
def my_id_command(message):

    bot.reply_to(
        message,
        f"Your Telegram ID: {message.from_user.id}"
    )


# ==========================================
# STATUS COMMAND
# ==========================================

@bot.message_handler(commands=["status", "stats"])
def status_command(message):

    if message.from_user.id != ADMIN_ID:

        bot.reply_to(
            message,
            "❌ Access Denied!\n"
            f"Your ID: {message.from_user.id}"
        )

        return

    try:

        total, active, blocked = get_database_stats()

        if os.path.exists("users.db"):

            file_size = (
                os.path.getsize("users.db") / 1024
            )

        else:

            file_size = 0

        status_text = (
            "📊 BOT & DATABASE STATUS\n\n"
            "🟢 Bot Status: WORKING\n"
            "✅ Database Status: CONNECTED\n\n"
            f"👥 Total Users: {total}\n"
            f"🟢 Active Users: {active}\n"
            f"🚫 Blocked Users: {blocked}\n\n"
            f"💾 Database Size: {file_size:.2f} KB\n"
            "📁 Database: users.db\n\n"
            "🤖 Join Request: SILENT MODE\n"
            "📩 Welcome Message: DISABLED\n"
            "✅ Auto Approve: DISABLED\n"
            "❌ Auto Reject: DISABLED"
        )

        bot.reply_to(
            message,
            status_text
        )

        print("STATUS COMMAND EXECUTED")

    except Exception as e:

        print(f"STATUS ERROR: {e}")

        bot.reply_to(
            message,
            f"❌ Status Error: {e}"
        )


# ==========================================
# RETRY AFTER HELPER
# ==========================================

def get_retry_after(error):

    try:

        result = getattr(
            error,
            "result_json",
            {}
        ) or {}

        parameters = result.get(
            "parameters",
            {}
        ) or {}

        retry_after = parameters.get(
            "retry_after"
        )

        if retry_after is not None:

            return max(1, int(retry_after))

    except Exception:
        pass

    match = re.search(
        r"retry after (\d+)",
        str(error),
        re.IGNORECASE
    )

    if match:

        return max(1, int(match.group(1)))

    return 5


# ==========================================
# BROADCAST ERROR CHECK
# ==========================================

def is_user_blocked(error):

    description = str(error).lower()

    return (
        "bot was blocked by the user" in description
        or "user is deactivated" in description
    )


# ==========================================
# SAFE BROADCAST SENDER
# ==========================================

def safe_copy_message(user_id, message):

    for attempt in range(MAX_RETRIES):

        try:

            bot.copy_message(
                chat_id=user_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )

            return "success"

        except ApiTelegramException as e:

            error_code = getattr(
                e,
                "error_code",
                0
            )

            # Telegram Rate Limit
            if error_code == 429:

                wait_time = get_retry_after(e)

                print(
                    f"RATE LIMIT: Waiting {wait_time}s "
                    f"for user {user_id}"
                )

                time.sleep(wait_time + 1)

                continue

            # Only actual blocked users
            if error_code == 403 and is_user_blocked(e):

                mark_user_blocked(user_id)

                return "blocked"

            print(
                f"API ERROR for {user_id}: {e}"
            )

            return "failed"

        except Exception as e:

            print(
                f"SEND ERROR for {user_id}: {e}"
            )

            return "failed"

    print(
        f"MAX RETRIES REACHED: {user_id}"
    )

    return "failed"


# ==========================================
# BROADCAST COMMAND
# ==========================================

@bot.message_handler(commands=["broadcast"])
def broadcast_command(message):

    if message.from_user.id != ADMIN_ID:

        bot.reply_to(
            message,
            "❌ Admin Only Command!"
        )

        return

    msg = bot.reply_to(
        message,
        "📢 BROADCAST MODE ON!\n\n"
        "Ab apna Text, Photo, Video ya Link bhejein."
    )

    bot.register_next_step_handler(
        msg,
        process_broadcast
    )


# ==========================================
# BROADCAST PROCESSOR
# ==========================================

def process_broadcast(message):

    if message.from_user.id != ADMIN_ID:
        return

    users = get_all_users()

    success = 0
    failed = 0
    blocked = 0

    status_msg = bot.reply_to(
        message,
        f"📢 Broadcasting to {len(users)} users...\n"
        "Please wait."
    )

    for index, user_id in enumerate(users):

        result = safe_copy_message(
            user_id,
            message
        )

        if result == "success":

            success += 1

        elif result == "blocked":

            blocked += 1

        else:

            failed += 1

        if index < len(users) - 1:

            time.sleep(BROADCAST_DELAY)

        if (index + 1) % 50 == 0:

            try:

                bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id,
                    text=(
                        "📢 BROADCAST IN PROGRESS\n\n"
                        f"Processed: {index + 1}/{len(users)}\n"
                        f"Success: {success}\n"
                        f"Failed: {failed}\n"
                        f"Blocked: {blocked}"
                    )
                )

            except Exception as e:

                print(
                    f"PROGRESS UPDATE ERROR: {e}"
                )

    try:

        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            text=(
                "✅ BROADCAST COMPLETED!\n\n"
                f"👥 Total Users: {len(users)}\n"
                f"✅ Successfully Sent: {success}\n"
                f"❌ Failed: {failed}\n"
                f"🚫 Actually Blocked: {blocked}"
            )
        )

    except Exception as e:

        print(
            f"FINAL BROADCAST STATUS ERROR: {e}"
        )


# ==========================================
# MAIN STARTUP
# ==========================================

if __name__ == "__main__":

    print("INITIALIZING BOT...")

    init_db()

    run_keepalive_in_thread()

    run_self_ping_in_thread()

    try:

        # Remove previous webhook before polling
        bot.delete_webhook(
            drop_pending_updates=False
        )

        print("OLD WEBHOOK REMOVED")

        # Verify bot token and connection
        bot_info = bot.get_me()

        print("================================")
        print("BOT STARTED SUCCESSFULLY")
        print(f"BOT NAME: {bot_info.first_name}")
        print(f"BOT USERNAME: @{bot_info.username}")
        print(f"ADMIN ID: {ADMIN_ID}")
        print("JOIN REQUEST: SILENT")
        print("AUTO APPROVE: OFF")
        print("AUTO REJECT: OFF")
        print("WELCOME MESSAGE: OFF")
        print("POLLING: STARTING")
        print("================================")

        bot.infinity_polling(
            skip_pending=False,
            timeout=30,
            long_polling_timeout=30
        )

    except Exception as e:

        print(
            f"FATAL BOT ERROR: {e}"
        )

        raise
        
