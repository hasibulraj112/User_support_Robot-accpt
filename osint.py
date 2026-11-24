
import os
import re
import sqlite3
import threading
import time
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot


# ============ CONFIGURATION ============

BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
ADMIN_ID = 5989928539
APP_URL = "https://osint-kblt.onrender.com"

bot = telebot.TeleBot(BOT_TOKEN)

# Broadcast settings
BROADCAST_DELAY = 0.1
MAX_RETRIES = 5


# ============ DATABASE SETUP ============

def init_db():
    conn = sqlite3.connect('users.db', timeout=30)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            status TEXT DEFAULT 'active'
        )
    ''')

    conn.commit()
    conn.close()


def add_user(user_id, first_name):
    conn = sqlite3.connect('users.db', timeout=30)
    c = conn.cursor()

    c.execute(
        """
        INSERT OR IGNORE INTO users
        (user_id, first_name, status)
        VALUES (?, ?, 'active')
        """,
        (user_id, first_name)
    )

    c.execute(
        """
        UPDATE users
        SET first_name = ?, status = 'active'
        WHERE user_id = ?
        """,
        (first_name, user_id)
    )

    conn.commit()
    conn.close()


def get_all_users():
    conn = sqlite3.connect('users.db', timeout=30)
    c = conn.cursor()

    c.execute(
        "SELECT user_id FROM users WHERE status = 'active'"
    )

    users = c.fetchall()
    conn.close()

    return [user[0] for user in users]


def mark_user_blocked(user_id):
    conn = sqlite3.connect('users.db', timeout=30)
    c = conn.cursor()

    c.execute(
        "UPDATE users SET status = 'blocked' WHERE user_id = ?",
        (user_id,)
    )

    conn.commit()
    conn.close()


# ============ KEEPALIVE SERVER ============

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
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

    server.serve_forever()


def run_keepalive_in_thread():
    threading.Thread(
        target=start_keepalive_server,
        daemon=True
    ).start()


# ============ SELF PING SYSTEM ============

def self_ping():
    while True:
        try:
            time.sleep(300)

            response = requests.get(
                APP_URL,
                timeout=20
            )

            print(
                f"Self-ping successful: {response.status_code}"
            )

        except Exception as e:
            print(f"Self-ping error: {e}")


def run_self_ping_in_thread():
    threading.Thread(
        target=self_ping,
        daemon=True
    ).start()


# ============ JOIN REQUEST HANDLER ============

@bot.chat_join_request_handler()
def accept_join_request(message):

    try:
        user_id = message.from_user.id

        first_name = (
            message.from_user.first_name or "User"
        )

        # Save user ID and name
        add_user(user_id, first_name)

        # IMPORTANT:
        # Do not approve request.
        # Do not decline request.
        # Do not send welcome message.
        # Request remains pending.

        print(
            f"JOIN REQUEST SAVED: {user_id} | PENDING"
        )

    except Exception as e:

        print(
            f"Join request database error: {e}"
        )


# ============ START COMMAND ============

@bot.message_handler(commands=['start'])
def send_welcome(message):

    user_id = message.from_user.id

    first_name = (
        message.from_user.first_name or "User"
    )

    add_user(user_id, first_name)

    if user_id == ADMIN_ID:

        bot.reply_to(
            message,
            "Hello Admin! ✅\n\n"
            "Commands available:\n"
            "👉 /broadcast - Send broadcast\n"
            "👉 /status - Database stats",
        )

    else:

        bot.reply_to(
            message,
            "👋 Hey! Add me to your group & channel "
            "to accept join request automatically! 😊"
        )


# ============ STATUS COMMAND ============

@bot.message_handler(commands=['status', 'stats'])
def status_command(message):

    if message.from_user.id != ADMIN_ID:
        return

    try:

        if os.path.exists('users.db'):

            file_size_bytes = os.path.getsize(
                'users.db'
            )

            file_size_kb = file_size_bytes / 1024

        else:
            file_size_kb = 0

        conn = sqlite3.connect(
            'users.db',
            timeout=30
        )

        c = conn.cursor()

        c.execute(
            "SELECT COUNT(*) FROM users"
        )
        total_users = c.fetchone()[0]

        c.execute(
            "SELECT COUNT(*) FROM users WHERE status = 'active'"
        )
        active_users = c.fetchone()[0]

        c.execute(
            "SELECT COUNT(*) FROM users WHERE status = 'blocked'"
        )
        blocked_users = c.fetchone()[0]

        conn.close()

        status_text = (
            "📊 **Bot & Database Status:**\n\n"
            f"👥 Total Users: `{total_users}`\n"
            f"🟢 Active Users: `{active_users}`\n"
            f"❌ Blocked Users: `{blocked_users}`\n"
            f"💾 Database Size: `{file_size_kb:.2f} KB`\n"
            "📁 File: `users.db`"
        )

        bot.reply_to(
            message,
            status_text,
            parse_mode='Markdown'
        )

    except Exception as e:

        bot.reply_to(
            message,
            f"Error getting status: {e}"
        )


# ============ ERROR HELPERS ============

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


def is_user_blocked(error):

    description = str(error).lower()

    return (
        "bot was blocked by the user" in description
        or "user is deactivated" in description
    )


# ============ SAFE BROADCAST COPY ============

def safe_copy_message(user_id, message):

    for attempt in range(MAX_RETRIES):

        try:

            bot.copy_message(
                chat_id=user_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )

            return "success"

        except telebot.apihelper.ApiTelegramException as e:

            error_code = getattr(
                e,
                "error_code",
                None
            )

            # Telegram rate limit
            if error_code == 429:

                wait_time = get_retry_after(e)

                print(
                    f"429 RATE LIMIT | Waiting {wait_time}s"
                    f" | User: {user_id}"
                )

                time.sleep(wait_time + 1)

                continue

            # Actual blocked user
            if error_code == 403 and is_user_blocked(e):

                mark_user_blocked(user_id)

                print(
                    f"USER BLOCKED BOT: {user_id}"
                )

                return "blocked"

            # Other API errors
            print(
                f"Telegram API error for {user_id}: {e}"
            )

            return "failed"

        except Exception as e:

            print(
                f"Broadcast error for {user_id}: {e}"
            )

            return "failed"

    print(
        f"MAX RETRIES EXCEEDED: {user_id}"
    )

    return "failed"


# ============ BROADCAST COMMAND ============

@bot.message_handler(commands=['broadcast'])
def broadcast_command(message):

    if message.from_user.id != ADMIN_ID:
        return

    msg = bot.reply_to(
        message,
        "📢 **Broadcast Mode On!**\n\n"
        "Ab aap jo bhi bhejna chahte hain "
        "(Text, Image + Caption, Video, Link), "
        "wo yahan send ya forward karein:"
    )

    bot.register_next_step_handler(
        msg,
        process_broadcast
    )


# ============ BROADCAST PROCESSOR ============

def process_broadcast(message):

    if message.from_user.id != ADMIN_ID:
        return

    users = get_all_users()

    success = 0
    failed = 0
    blocked = 0

    status_msg = bot.reply_to(
        message,
        f"📢 Broadcasting to {len(users)} active users..."
        "\nPlease wait ⏳"
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

        # Safe delay between messages
        if index < len(users) - 1:
            time.sleep(BROADCAST_DELAY)

        # Update progress occasionally
        if (index + 1) % 50 == 0:

            try:

                bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id,
                    text=(
                        "📢 **Broadcast In Progress**\n\n"
                        f"Processed: `{index + 1}/{len(users)}`\n"
                        f"Success: `{success}`\n"
                        f"Failed: `{failed}`\n"
                        f"Blocked: `{blocked}`"
                    ),
                    parse_mode='Markdown'
                )

            except Exception as e:

                print(
                    f"Progress update error: {e}"
                )

    # Final report
    try:

        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            text=(
                "✅ **Broadcast Completed!**\n\n"
                f"👥 Total Users: `{len(users)}`\n"
                f"✅ Successfully Sent: `{success}`\n"
                f"❌ Failed: `{failed}`\n"
                f"🚫 Actually Blocked: `{blocked}`"
            ),
            parse_mode='Markdown'
        )

    except Exception as e:

        print(
            f"Final status update error: {e}"
        )


# ============ MAIN ============

if __name__ == "__main__":

    init_db()

    run_keepalive_in_thread()

    run_self_ping_in_thread()

    print(
        "Bot Started Successfully!"
    )

    print(
        "Pending Join Request + ID Collection "
        "+ Safe Broadcast + 429 Retry System"
    )

    bot.infinity_polling(
        skip_pending=False
    )
    
