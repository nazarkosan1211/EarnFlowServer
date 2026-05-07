import os
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

# ---------- DATABASE HELPERS ----------
def db(): 
    return sqlite3.connect(DB_NAME)

def today_str(): 
    return date.today().isoformat()

def init_db():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            coins INTEGER DEFAULT 0,
            tasks_done INTEGER DEFAULT 0,
            task_date TEXT DEFAULT '',
            last_task_time INTEGER DEFAULT 0,
            referrer_id TEXT DEFAULT NULL,
            ref_count INTEGER DEFAULT 0,
            ref_date TEXT DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()

def add_user(user_id):
    conn = db()
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id, coins) VALUES (?,0)", (str(user_id),))
    cur.execute("""
        UPDATE users 
        SET task_date=CASE WHEN task_date='' THEN ? ELSE task_date END,
            ref_date=CASE WHEN ref_date='' THEN ? ELSE ref_date END
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

# ---------- ROUTES ----------
@app.route("/")
def home():
    return jsonify({"status": "server alive"})

@app.route("/start_user", methods=["POST"])
def start_user():
    data = request.get_json()
    user_id = str(data.get("user_id"))
    ref = data.get("ref")
    if not user_id or user_id=="None":
        return jsonify({"error":"no user_id"}),400

    add_user(user_id)
    reset_daily(user_id)
    
    message="no_ref"
    bonus_given=False

    if ref:
        ref=str(ref)
        if ref==user_id:
            return jsonify({"status":"ok","message":"self_ref_blocked"})
        
        conn=db(); cur=conn.cursor()
        cur.execute("SELECT user_id, coins, ref_count FROM users WHERE user_id=?", (ref,))
        referrer = cur.fetchone()
        if not referrer: conn.close(); return jsonify({"status":"ok","message":"referrer_not_found"})

        cur.execute("SELECT referrer_id FROM users WHERE user_id=?", (user_id,))
        user_row = cur.fetchone()
        if user_row and user_row[0]:
            conn.close()
            return jsonify({"status":"ok","message":"already_referred"})

        ref_user_id, ref_coins, ref_count = referrer
        if ref_count < MAX_REF_PER_DAY:
            ref_coins += REF_BONUS
            ref_count += 1
            cur.execute("""
                UPDATE users 
                SET coins=?, ref_count=?, ref_date=? 
                WHERE user_id=?
            """, (ref_coins, ref_count, today_str(), ref_user_id))

        cur.execute("UPDATE users SET referrer_id=? WHERE user_id=?", (ref,user_id))
        conn.commit(); conn.close()
        bonus_given=True
        message="ref_bonus_given"

    return jsonify({"status":"ok","message":message,"bonus_given":bonus_given})

@app.route("/add_coin", methods=["POST"])
def add_coin():
    data=request.get_json()
    user_id=str(data.get("user_id"))
    amount=int(data.get("amount",1))
    if not user_id or user_id=="None":
        return jsonify({"error":"no user_id"}),400

    add_user(user_id)
    reset_daily(user_id)

    conn=db(); cur=conn.cursor()
    cur.execute("SELECT coins,tasks_done,last_task_time,ref_count FROM users WHERE user_id=?",(user_id,))
    row = cur.fetchone()
    coins,tasks_done,last_time,ref_count = row
    now=int(time.time())

    if amount==0:
        conn.close()
        return jsonify({
            "status":"sync",
            "coins":coins,
            "tasks_done":tasks_done,
            "remaining_tasks":MAX_TASKS_PER_DAY-tasks_done,
            "ref_count":ref_count
        })

    if tasks_done >= MAX_TASKS_PER_DAY:
        conn.close()
        return jsonify({
            "status":"blocked",
            "reason":"daily_limit",
            "coins":coins,
            "tasks_done":tasks_done,
            "remaining_tasks":0,
            "ref_count":ref_count
        })

    if now - last_time < COOLDOWN_SECONDS:
        wait=COOLDOWN_SECONDS-(now-last_time)
        conn.close()
        return jsonify({
            "status":"blocked",
            "reason":"cooldown",
            "wait":wait,
            "coins":coins,
            "tasks_done":tasks_done,
            "remaining_tasks":MAX_TASKS_PER_DAY-tasks_done,
            "ref_count":ref_count
        })

    coins+=amount
    tasks_done+=1
    cur.execute("""
        UPDATE users 
        SET coins=?, tasks_done=?, task_date=?, last_task_time=? 
        WHERE user_id=?
    """, (coins, tasks_done, today_str(), now, user_id))
    conn.commit(); conn.close()
    return jsonify({
        "status":"success",
        "coins":coins,
        "tasks_done":tasks_done,
        "remaining_tasks":MAX_TASKS_PER_DAY-tasks_done,
        "ref_count":ref_count
    })

@app.route("/leaderboard")
def leaderboard():
    conn=db(); cur=conn.cursor()
    cur.execute("SELECT user_id, coins FROM users ORDER BY coins DESC LIMIT 10")
    rows = cur.fetchall(); conn.close()
    result = []
    rank=1
    for r in rows:
        result.append({"rank":rank,"user_id":r[0],"coins":r[1],"name":f"User {r[0]}"})
        rank+=1
    return jsonify(result)

# ---------- INIT ----------
init_db()
if __name__=="__main__":
    app.run(port=int(os.environ.get("PORT",5000)))
