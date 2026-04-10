from datetime import datetime, timedelta, timezone
from hmac import compare_digest

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

from config import ADMIN_PASSWORD, SECRET_KEY
from routes.attendance import attendance_bp

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.permanent_session_lifetime = timedelta(hours=8)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

# Connects the attendance routes to the main Flask app.
app.register_blueprint(attendance_bp)

MAX_ADMIN_ATTEMPTS = 5
ADMIN_COOLDOWN_SECONDS = 30


def get_admin_attempt_state():
    # Reads the current admin login cooldown from the session.
    now = datetime.now(timezone.utc)
    state = session.get("admin_attempts", {})
    count = int(state.get("count", 0))
    cooldown_until_raw = state.get("cooldown_until")
    cooldown_until = None

    if cooldown_until_raw:
        try:
            cooldown_until = datetime.fromisoformat(cooldown_until_raw)
        except ValueError:
            cooldown_until = None

    if cooldown_until and cooldown_until <= now:
        count = 0
        cooldown_until = None

    return {
        "count": count,
        "cooldown_until": cooldown_until,
    }


def save_admin_attempt_state(count, cooldown_until):
    # Saves failed login count and cooldown expiry for admin access.
    session["admin_attempts"] = {
        "count": count,
        "cooldown_until": cooldown_until.isoformat() if cooldown_until else None,
    }


@app.route("/")
def home():
    # Returns the user to the front page and clears admin access.
    session.pop("admin_authenticated", None)
    return render_template("index.html")


@app.route("/admin")
def admin():
    # Redirects unauthorized users away from the admin dashboard.
    if not session.get("admin_authenticated"):
        return redirect(url_for("home"))
    return render_template("admin.html")


@app.route("/admin/login", methods=["POST"])
def admin_login():
    # Validates the admin password and applies login cooldown rules.
    state = get_admin_attempt_state()
    now = datetime.now(timezone.utc)
    cooldown_until = state["cooldown_until"]

    if cooldown_until and cooldown_until > now:
        remaining = max(1, int((cooldown_until - now).total_seconds()))
        return jsonify({
            "error": f"Too many failed attempts. Try again in {remaining} seconds.",
            "cooldown_remaining": remaining,
        }), 429

    data = request.json or {}
    password = str(data.get("password", ""))

    if compare_digest(password, ADMIN_PASSWORD):
        session.permanent = True
        session["admin_authenticated"] = True
        save_admin_attempt_state(0, None)
        return jsonify({"message": "Admin access granted."}), 200

    failed_count = state["count"] + 1
    attempts_left = MAX_ADMIN_ATTEMPTS - failed_count

    if failed_count >= MAX_ADMIN_ATTEMPTS:
        cooldown_until = now + timedelta(seconds=ADMIN_COOLDOWN_SECONDS)
        save_admin_attempt_state(failed_count, cooldown_until)
        return jsonify({
            "error": f"Too many failed attempts. Try again in {ADMIN_COOLDOWN_SECONDS} seconds.",
            "cooldown_remaining": ADMIN_COOLDOWN_SECONDS,
        }), 429

    save_admin_attempt_state(failed_count, None)
    return jsonify({
        "error": f"Incorrect password. {attempts_left} attempt(s) remaining.",
        "attempts_left": attempts_left,
    }), 401


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    # Ends the active admin session.
    session.pop("admin_authenticated", None)
    return jsonify({"message": "Logged out."}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
