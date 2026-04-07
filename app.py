from flask import Flask, render_template
from routes.attendance import attendance_bp

app = Flask(__name__)

app.register_blueprint(attendance_bp)

@app.route('/')
def home():
    return render_template("index.html")

@app.route('/admin')
def admin():
    return render_template("admin.html")

if __name__ == "__main__":
    app.run(debug=True)