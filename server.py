import os
from flask import Flask, request, jsonify
from flask_cors import CORS

# ========================
# CONFIG
# ========================
app = Flask(__name__)
CORS(app)

# Gunakan environment variable atau default
PORT = int(os.environ.get("PORT", 5000))

# ========================
# IN-MEMORY STORAGE SEMENTARA
# ========================
# nanti bisa ganti ke DB jika mau persistence
users = {}
tasks = [
    {"id": 1, "name": "Daily Check-in", "coin": 10},
    {"id": 2, "name": "Watch Video", "coin": 5},
]

# ========================
# ROUTES
# ========================

@app.route("/")
def index():
    return jsonify({"status": "server alive"})

@app.route("/add_coin", methods=["POST"])
def add_coin():
    data = request.json
    user_id = data.get("user_id")
    coin = data.get("coin", 0)
    if not user_id:
        return jsonify({"error": "user_id required"}), 400

    users.setdefault(user_id, 0)
    users[user_id] += coin
    return jsonify({"user_id": user_id, "total_coin": users[user_id]})

@app.route("/leaderboard", methods=["GET"])
def leaderboard():
    sorted_users = sorted(users.items(), key=lambda x: x[1], reverse=True)
    top10 = [{"user_id": uid, "coin": coin} for uid, coin in sorted_users[:10]]
    return jsonify(top10)

@app.route("/tasks", methods=["GET"])
def get_tasks():
    return jsonify(tasks)

# ========================
# RUN SERVER
# ========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
