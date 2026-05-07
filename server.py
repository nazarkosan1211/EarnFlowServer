import os
from flask import Flask, jsonify, request
from flask_cors import CORS

# ========================
# CONFIG
# ========================
PORT = int(os.environ.get("PORT", 5000))
DEBUG = False  # Production
app = Flask(__name__)
CORS(app)  # Allow cross-origin (untuk Netlify WebApp)

# ========================
# In-Memory Database (contoh sederhana)
# ========================
users = {}
tasks = {}

# ========================
# Routes
# ========================
@app.route("/")
def home():
    return jsonify({"status": "server alive"})

@app.route("/user/<user_id>", methods=["GET"])
def get_user(user_id):
    user = users.get(user_id, {"points": 0, "tasks": []})
    return jsonify(user)

@app.route("/task/add", methods=["POST"])
def add_task():
    data = request.json
    user_id = data.get("user_id")
    task_name = data.get("task_name")
    if not user_id or not task_name:
        return jsonify({"error": "user_id and task_name required"}), 400

    if user_id not in tasks:
        tasks[user_id] = []

    tasks[user_id].append({"name": task_name, "completed": False})
    return jsonify({"success": True, "tasks": tasks[user_id]})

@app.route("/task/complete", methods=["POST"])
def complete_task():
    data = request.json
    user_id = data.get("user_id")
    task_index = data.get("task_index")
    if user_id not in tasks or task_index is None or task_index >= len(tasks[user_id]):
        return jsonify({"error": "Invalid request"}), 400

    tasks[user_id][task_index]["completed"] = True
    if user_id not in users:
        users[user_id] = {"points": 0, "tasks": []}
    users[user_id]["points"] += 1
    return jsonify({"success": True, "user": users[user_id]})

@app.route("/leaderboard", methods=["GET"])
def leaderboard():
    lb = sorted(users.items(), key=lambda x: x[1]["points"], reverse=True)
    return jsonify({"leaderboard": lb})

# ========================
# RUN WITH GUNICORN (Production)
# ========================
if __name__ == "__main__":
    print(f"Server ready on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
