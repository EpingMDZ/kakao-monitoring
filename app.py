"""
SIKAKAO - Sistem Pengering Biji Kakao Otomatis
Aplikasi Web Monitoring berbasis Flask

Sesuai dengan:
- Use Case Diagram 
- Activity Diagram 
- Class Diagram 
- Perancangan Interface 
"""

import json
import queue
import threading
import time
from datetime import datetime

from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from models import DataMonitoring, HistoryPengeringan, User, db
from mqtt_client import mqtt_client

# ============================================================
# Flask Application Setup
# ============================================================
app = Flask(__name__)
app.config.from_object(Config)

# Initialize database
db.init_app(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Silakan login untuk mengakses SIKAKAO."

# SSE clients for real-time updates
sse_clients = []
sse_lock = threading.Lock()

# Active drying session tracking
active_session_id = None
active_session_lock = threading.Lock()


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ============================================================
# MQTT Data Handler - Saves incoming data to database
# ============================================================
def on_mqtt_data(data):
    """Callback: simpan data MQTT ke database dan broadcast ke SSE"""
    global active_session_id

    with app.app_context():
        try:
            with active_session_lock:
                session_id = active_session_id

            if session_id:
                record = DataMonitoring(
                    suhu_aktual=data.get("suhu_aktual", 0),
                    kelembaban=data.get("kelembaban", 0),
                    setpoint_suhu=data.get("setpoint_suhu", 50),
                    output_pid=data.get("output_pid", 0),
                    status_heater=data.get("status_heater", "OFF"),
                    status_kipas=data.get("status_kipas", "OFF"),
                    session_id=session_id,
                )
                db.session.add(record)
                db.session.commit()

                # Cek apakah pengeringan selesai (RH ≤ 40%)
                if data.get("kelembaban", 100) <= Config.RH_THRESHOLD:
                    session = db.session.get(HistoryPengeringan, session_id)
                    if session and session.status == "Berjalan":
                        session.status = "Selesai"
                        session.tanggal_selesai = datetime.utcnow()
                        db.session.commit()
                        with active_session_lock:
                            active_session_id = None

            # Broadcast ke semua SSE clients
            event_data = json.dumps(data)
            with sse_lock:
                dead_clients = []
                for q in sse_clients:
                    try:
                        q.put_nowait(event_data)
                    except Exception:
                        dead_clients.append(q)
                for q in dead_clients:
                    sse_clients.remove(q)

        except Exception as e:
            print(f"[DB] Error saving data: {e}")
            db.session.rollback()


# ============================================================
# Authentication Routes - sesuai Use Case Diagram (Gambar 3.9)
# ============================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash("Login berhasil! Selamat datang di SIKAKAO.", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Username atau password salah.", "error")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not username or not password:
            flash("Username dan password harus diisi.", "error")
        elif len(password) < 6:
            flash("Password minimal 6 karakter.", "error")
        elif password != confirm:
            flash("Password tidak cocok.", "error")
        elif User.query.filter_by(username=username).first():
            flash("Username sudah digunakan.", "error")
        else:
            user = User(
                username=username,
                password=generate_password_hash(password),
            )
            db.session.add(user)
            db.session.commit()
            flash("Registrasi berhasil! Silakan login.", "success")
            return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Anda telah keluar.", "info")
    return redirect(url_for("login"))


# ============================================================
# Page Routes - sesuai Perancangan Interface (Gambar 3.12-3.17)
# ============================================================
@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    """Halaman Dashboard - Gambar 3.12"""
    data = mqtt_client.get_latest_data()
    return render_template("dashboard.html", data=data, active_page="dashboard")


@app.route("/kontrol")
@login_required
def kontrol():
    """Halaman Kontrol - Gambar 3.13"""
    data = mqtt_client.get_latest_data()
    with active_session_lock:
        is_running = active_session_id is not None
    return render_template(
        "kontrol.html", data=data, is_running=is_running, active_page="kontrol"
    )


@app.route("/grafik")
@login_required
def grafik():
    """Halaman Grafik - Gambar 3.14"""
    return render_template("grafik.html", active_page="grafik")


@app.route("/status")
@login_required
def status():
    """Halaman Status - Gambar 3.15"""
    data = mqtt_client.get_latest_data()
    data["mqtt_connected"] = mqtt_client.is_connected()
    return render_template("status.html", data=data, active_page="status")


@app.route("/history")
@login_required
def history():
    """Halaman History - Gambar 3.16"""
    sessions = (
        HistoryPengeringan.query.filter_by(user_id=current_user.id)
        .order_by(HistoryPengeringan.tanggal_mulai.desc())
        .all()
    )
    return render_template("history.html", sessions=sessions, active_page="history")


@app.route("/history/<int:session_id>")
@login_required
def history_detail(session_id):
    """Detail History Pengeringan"""
    session = HistoryPengeringan.query.filter_by(
        id=session_id, user_id=current_user.id
    ).first_or_404()
    data_points = (
        DataMonitoring.query.filter_by(session_id=session_id)
        .order_by(DataMonitoring.timestamp.asc())
        .all()
    )
    return render_template(
        "history_detail.html",
        session=session,
        data_points=data_points,
        active_page="history",
    )


@app.route("/tentang")
@login_required
def tentang():
    """Halaman Tentang - Gambar 3.17"""
    return render_template("tentang.html", active_page="tentang")


# ============================================================
# API Endpoints
# ============================================================
@app.route("/api/sensor-data")
@login_required
def api_sensor_data():
    """API: Data sensor terbaru"""
    data = mqtt_client.get_latest_data()
    data["mqtt_connected"] = mqtt_client.is_connected()
    with active_session_lock:
        data["is_running"] = active_session_id is not None
    return jsonify(data)


@app.route("/api/set-setpoint", methods=["POST"])
@login_required
def api_set_setpoint():
    """API: Ubah setpoint suhu (publish ke MQTT)"""
    setpoint = request.json.get("setpoint", 50)

    if setpoint < Config.PID_SETPOINT_MIN or setpoint > Config.PID_SETPOINT_MAX:
        return jsonify(
            {
                "success": False,
                "message": f"Setpoint harus antara {Config.PID_SETPOINT_MIN}°C dan {Config.PID_SETPOINT_MAX}°C",
            }
        ), 400

    mqtt_client.publish_setpoint(setpoint)
    return jsonify({"success": True, "setpoint": setpoint})


@app.route("/api/start-drying", methods=["POST"])
@login_required
def api_start_drying():
    """API: Mulai proses pengeringan"""
    global active_session_id

    setpoint = request.json.get("setpoint", 50)

    with active_session_lock:
        if active_session_id is not None:
            return jsonify(
                {"success": False, "message": "Proses pengeringan sedang berjalan."}
            ), 400

    # Hitung nomor pengeringan berikutnya
    count = HistoryPengeringan.query.filter_by(user_id=current_user.id).count()
    nama_proses = f"Pengeringan {count + 1}"

    # Buat sesi baru
    session_record = HistoryPengeringan(
        nama_proses=nama_proses,
        setpoint_suhu=setpoint,
        status="Berjalan",
        user_id=current_user.id,
    )
    db.session.add(session_record)
    db.session.commit()

    with active_session_lock:
        active_session_id = session_record.id

    # Kirim perintah ke ESP32
    mqtt_client.publish_setpoint(setpoint)
    mqtt_client.publish_command("START")

    return jsonify(
        {
            "success": True,
            "message": f"{nama_proses} dimulai dengan setpoint {setpoint}°C",
            "session_id": session_record.id,
        }
    )


@app.route("/api/stop-drying", methods=["POST"])
@login_required
def api_stop_drying():
    """API: Hentikan proses pengeringan"""
    global active_session_id

    with active_session_lock:
        if active_session_id is None:
            return jsonify(
                {
                    "success": False,
                    "message": "Tidak ada proses pengeringan yang berjalan.",
                }
            ), 400

        session_record = db.session.get(HistoryPengeringan, active_session_id)
        if session_record:
            session_record.status = "Selesai"
            session_record.tanggal_selesai = datetime.utcnow()
            db.session.commit()

        active_session_id = None

    mqtt_client.publish_command("STOP")

    return jsonify({"success": True, "message": "Proses pengeringan dihentikan."})


@app.route("/api/grafik-data")
@login_required
def api_grafik_data():
    """API: Data grafik suhu & kelembaban"""
    limit = request.args.get("limit", 50, type=int)

    records = (
        DataMonitoring.query.order_by(DataMonitoring.timestamp.desc())
        .limit(limit)
        .all()
    )
    records.reverse()

    return jsonify(
        {
            "labels": [r.timestamp.strftime("%H:%M:%S") for r in records],
            "suhu": [r.suhu_aktual for r in records],
            "kelembaban": [r.kelembaban for r in records],
            "setpoint": [r.setpoint_suhu for r in records],
            "output_pid": [r.output_pid for r in records],
        }
    )


@app.route("/api/device-status")
@login_required
def api_device_status():
    """API: Status perangkat"""
    data = mqtt_client.get_latest_data()
    return jsonify(
        {
            "esp32": "Connected" if data.get("esp32_connected") else "Disconnected",
            "sensor_dht22": "Normal" if data.get("esp32_connected") else "Tidak Terhubung",
            "heater": "Aktif" if data.get("status_heater") == "ON" else "Nonaktif",
            "kipas": "Aktif" if data.get("status_kipas") == "ON" else "Nonaktif",
            "mqtt_broker": "Connected" if mqtt_client.is_connected() else "Disconnected",
            "last_update": data.get("last_update", "-"),
        }
    )


@app.route("/api/history/<int:session_id>/data")
@login_required
def api_history_data(session_id):
    """API: Data monitoring untuk sesi tertentu"""
    session_record = HistoryPengeringan.query.filter_by(
        id=session_id, user_id=current_user.id
    ).first_or_404()

    records = (
        DataMonitoring.query.filter_by(session_id=session_id)
        .order_by(DataMonitoring.timestamp.asc())
        .all()
    )

    return jsonify(
        {
            "session": {
                "nama_proses": session_record.nama_proses,
                "tanggal_mulai": session_record.tanggal_mulai.strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "tanggal_selesai": session_record.tanggal_selesai.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                if session_record.tanggal_selesai
                else None,
                "setpoint_suhu": session_record.setpoint_suhu,
                "status": session_record.status,
            },
            "data": [r.to_dict() for r in records],
        }
    )


# ============================================================
# Server-Sent Events (SSE) for real-time updates
# ============================================================
@app.route("/api/stream")
@login_required
def stream():
    """SSE endpoint for real-time sensor data updates"""

    def event_stream():
        q = queue.Queue(maxsize=100)
        with sse_lock:
            sse_clients.append(q)
        try:
            while True:
                try:
                    data = q.get(timeout=30)
                    yield f"data: {data}\n\n"
                except queue.Empty:
                    # Send keepalive
                    yield f": keepalive\n\n"
        except GeneratorExit:
            with sse_lock:
                if q in sse_clients:
                    sse_clients.remove(q)

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ============================================================
# Application Entry Point
# ============================================================
if __name__ == "__main__":
    with app.app_context():
        # Create all database tables
        db.create_all()
        print("[DB] Database tables created successfully.")

    # Initialize MQTT client
    mqtt_client.init_app(app)
    mqtt_client.register_callback(on_mqtt_data)
    print("[MQTT] MQTT client initialized.")

    print("\n" + "=" * 60)
    print("  SIKAKAO - Sistem Pengering Biji Kakao Otomatis")
    print("  Monitoring Dashboard")
    print("=" * 60)
    print(f"  Web App     : http://localhost:5000")
    print(f"  MQTT Broker : {Config.MQTT_BROKER_HOST}:{Config.MQTT_BROKER_PORT}")
    print("=" * 60 + "\n")

    app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)
