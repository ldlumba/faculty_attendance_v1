from datetime import datetime, timedelta
from hmac import compare_digest

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

from config import ADMIN_PASSWORD, SECRET_KEY
from routes.attendance import attendance_bp

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.permanent_session_lifetime = timedelta(hours=8)

app.register_blueprint(attendance_bp)

admin_attempts = {}
MAX_ADMIN_ATTEMPTS = 5
ADMIN_COOLDOWN_SECONDS = 30


def get_client_key():
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.remote_addr or "unknown"


def get_attempt_state(client_key):
    now = datetime.utcnow()
    state = admin_attempts.get(client_key)

    if not state:
        state = {"count": 0, "cooldown_until": None}
        admin_attempts[client_key] = state

    cooldown_until = state["cooldown_until"]
    if cooldown_until and cooldown_until <= now:
        state["count"] = 0
        state["cooldown_until"] = None

    return state


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/admin")
def admin():
    if not session.get("admin_authenticated"):
        return redirect(url_for("home"))
    return render_template("admin.html")


@app.route("/admin/login", methods=["POST"])
def admin_login():
    client_key = get_client_key()
    state = get_attempt_state(client_key)
    now = datetime.utcnow()

    cooldown_until = state["cooldown_until"]
    if cooldown_until and cooldown_until > now:
        remaining = int((cooldown_until - now).total_seconds())
        return jsonify({
            "error": f"Too many failed attempts. Try again in {remaining} seconds.",
            "cooldown_remaining": remaining,
        }), 429

    data = request.json or {}
    password = str(data.get("password", ""))

    if compare_digest(password, ADMIN_PASSWORD):
        session.permanent = True
        session["admin_authenticated"] = True
        state["count"] = 0
        state["cooldown_until"] = None
        return jsonify({"message": "Admin access granted."}), 200

    state["count"] += 1
    attempts_left = MAX_ADMIN_ATTEMPTS - state["count"]

    if state["count"] >= MAX_ADMIN_ATTEMPTS:
        state["cooldown_until"] = now + timedelta(seconds=ADMIN_COOLDOWN_SECONDS)
        return jsonify({
            "error": f"Too many failed attempts. Try again in {ADMIN_COOLDOWN_SECONDS} seconds.",
            "cooldown_remaining": ADMIN_COOLDOWN_SECONDS,
        }), 429

    return jsonify({
        "error": f"Incorrect password. {attempts_left} attempt(s) remaining.",
        "attempts_left": attempts_left,
    }), 401


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
