from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
from datetime import date
import time

app = Flask(__name__)
CORS(app)

DB_NAME = "users.db"

MAX_TASKS_PER_DAY = 30
COOLDOWN_SECONDS = 15
REF_BONUS = 10
MAX_REF_PER_DAY = 20

def db():
    return sqlite3.connect(DB_NAME)

def today_str():
    return date.today().isoformat()

def ensure_column(cur, table, column, definition):
    cur.execute(f"PRAGMA table_info({table})")
    columns = [c[1] for c in cur.fetchall()]
    if column not in columns:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        coins INTEGER DEFAULT 0
    )
    """)

    ensure_column(cur, "users", "username", "TEXT DEFAULT ''")
    ensure_column(cur, "users", "tasks_done", "INTEGER DEFAULT 0")
    ensure_column(cur, "users", "task_date", "TEXT DEFAULT ''")
    ensure_column(cur, "users", "last_task_time", "INTEGER DEFAULT 0")
    ensure_column(cur, "users", "referrer_id", "TEXT DEFAULT NULL")
    ensure_column(cur, "users", "ref_count", "INTEGER DEFAULT 0")
    ensure_column(cur, "users", "ref_date", "TEXT DEFAULT ''")

    conn.commit()
    conn.close()

def add_user(user_id, username=None):
    conn = db()
    cur = conn.cursor()

    cur.execute(
        "INSERT OR IGNORE INTO users (user_id, coins) VALUES (?, 0)",
        (str(user_id),)
    )

    if username:
        cur.execute(
            "UPDATE users SET username=? WHERE user_id=?",
            (str(username), str(user_id))
        )

    cur.execute("""
        UPDATE users
        SET task_date = CASE WHEN task_date='' THEN ? ELSE task_date END,
            ref_date = CASE WHEN ref_date='' THEN ? ELSE ref_date END
        WHERE user_id=?
    """, (today_str(), today_str(), str(user_id)))

    conn.commit()
    conn.close()

def reset_daily(user_id):
    conn = db()
    cur = conn.cursor()

    cur.execute("SELECT task_date, ref_date FROM users WHERE user_id=?", (str(user_id),))
    row = cur.fetchone()

    if row:
        task_date, ref_date = row

        if task_date != today_str():
            cur.execute("""
                UPDATE users
                SET tasks_done=0, task_date=?, last_task_time=0
                WHERE user_id=?
            """, (today_str(), str(user_id)))

        if ref_date != today_str():
            cur.execute("""
                UPDATE users
                SET ref_count=0, ref_date=?
                WHERE user_id=?
            """, (today_str(), str(user_id)))

    conn.commit()
    conn.close()

@app.route("/")
def home():
    return jsonify({"status": "server alive"})

@app.route("/start_user", methods=["POST"])
def start_user():
    data = request.get_json()
    user_id = str(data.get("user_id"))
    username = data.get("username")
    ref = data.get("ref")

    if not user_id or user_id == "None":
        return jsonify({"error": "no user_id"}), 400

    add_user(user_id, username)
    reset_daily(user_id)

    bonus_given = False
    message = "no_ref"

    if ref:
        ref = str(ref)

        if ref == user_id:
            return jsonify({"status": "ok", "message": "self_ref_blocked"})

        conn = db()
        cur = conn.cursor()

        cur.execute("SELECT user_id, coins, ref_count FROM users WHERE user_id=?", (ref,))
        referrer = cur.fetchone()

        if not referrer:
            conn.close()
            return jsonify({"status": "ok", "message": "referrer_not_found"})

        cur.execute("SELECT referrer_id FROM users WHERE user_id=?", (user_id,))
        user_row = cur.fetchone()

        if user_row and user_row[0]:
            conn.close()
            return jsonify({"status": "ok", "message": "already_referred"})

        ref_user_id, ref_coins, ref_count = referrer

        if ref_count >= MAX_REF_PER_DAY:
            cur.execute("UPDATE users SET referrer_id=? WHERE user_id=?", (ref, user_id))
            conn.commit()
            conn.close()
            return jsonify({"status": "ok", "message": "ref_limit_reached"})

        ref_coins += REF_BONUS
        ref_count += 1

        cur.execute("UPDATE users SET referrer_id=? WHERE user_id=?", (ref, user_id))
        cur.execute("""
            UPDATE users
            SET coins=?, ref_count=?, ref_date=?
            WHERE user_id=?
        """, (ref_coins, ref_count, today_str(), ref))

        conn.commit()
        conn.close()

        bonus_given = True
        message = "ref_bonus_given"

    return jsonify({
        "status": "ok",
        "message": message,
        "bonus_given": bonus_given
    })

@app.route("/add_coin", methods=["POST"])
def add_coin():
    data = request.get_json()
    user_id = str(data.get("user_id"))
    amount = int(data.get("amount", 1))

    if not user_id or user_id == "None":
        return jsonify({"error": "no user_id"}), 400

    add_user(user_id)
    reset_daily(user_id)

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT coins, tasks_done, last_task_time, ref_count
        FROM users
        WHERE user_id=?
    """, (user_id,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return jsonify({"error": "user_not_found"}), 400

    coins, tasks_done, last_time, ref_count = row
    now = int(time.time())

    if amount == 0:
        conn.close()
        return jsonify({
            "status": "sync",
            "coins": coins,
            "tasks_done": tasks_done,
            "remaining_tasks": MAX_TASKS_PER_DAY - tasks_done,
            "ref_count": ref_count
        })

    if tasks_done >= MAX_TASKS_PER_DAY:
        conn.close()
        return jsonify({
            "status": "blocked",
            "reason": "daily_limit",
            "coins": coins,
            "tasks_done": tasks_done,
            "remaining_tasks": 0,
            "ref_count": ref_count
        })

    if now - last_time < COOLDOWN_SECONDS:
        wait = COOLDOWN_SECONDS - (now - last_time)
        conn.close()
        return jsonify({
            "status": "blocked",
            "reason": "cooldown",
            "wait": wait,
            "coins": coins,
            "tasks_done": tasks_done,
            "remaining_tasks": MAX_TASKS_PER_DAY - tasks_done,
            "ref_count": ref_count
        })

    coins += amount
    tasks_done += 1

    cur.execute("""
        UPDATE users
        SET coins=?, tasks_done=?, task_date=?, last_task_time=?
        WHERE user_id=?
    """, (coins, tasks_done, today_str(), now, user_id))

    conn.commit()
    conn.close()

    return jsonify({
        "status": "success",
        "coins": coins,
        "tasks_done": tasks_done,
        "remaining_tasks": MAX_TASKS_PER_DAY - tasks_done,
        "ref_count": ref_count
    })

@app.route("/leaderboard")
def leaderboard():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT user_id, username, coins
        FROM users
        ORDER BY coins DESC
        LIMIT 10
    """)

    rows = cur.fetchall()
    conn.close()

    result = []
    for i, r in enumerate(rows):
        user_id, username, coins = r
        name = username if username else f"User {user_id}"

        result.append({
            "rank": i + 1,
            "name": name,
            "user_id": user_id,
            "coins": coins
        })

    return jsonify(result)

@app.route("/debug_users")
def debug_users():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT user_id, username, coins, tasks_done, task_date, referrer_id, ref_count, ref_date, last_task_time
        FROM users
    """)

    rows = cur.fetchall()
    conn.close()

    return jsonify([
        {
            "user_id": r[0],
            "username": r[1],
            "coins": r[2],
            "tasks_done": r[3],
            "task_date": r[4],
            "referrer_id": r[5],
            "ref_count": r[6],
            "ref_date": r[7],
            "last_task_time": r[8]
        }
        for r in rows
    ])

init_db()

if __name__ == "__main__":
    app.run(port=5000)