"""
Model database SIKAKAO - sesuai Class Diagram (Gambar 3.11)
Kelas: User, DataMonitoring, HistoryPengeringan
"""

from datetime import datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """
    Kelas User - sesuai Class Diagram
    Atribut: userId, username, password
    Metode: login(), logout(), lihatDashboard()
    """

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relasi ke history pengeringan
    history = db.relationship("HistoryPengeringan", backref="user", lazy=True)

    def __repr__(self):
        return f"<User {self.username}>"


class HistoryPengeringan(db.Model):
    """
    Kelas HistoryPengeringan - sesuai Class Diagram
    Menyimpan riwayat proses pengeringan
    """

    __tablename__ = "history_pengeringan"

    id = db.Column(db.Integer, primary_key=True)
    nama_proses = db.Column(db.String(100), nullable=False)
    tanggal_mulai = db.Column(db.DateTime, default=datetime.utcnow)
    tanggal_selesai = db.Column(db.DateTime, nullable=True)
    setpoint_suhu = db.Column(db.Float, nullable=False, default=50.0)
    status = db.Column(db.String(20), default="Berjalan")  # Berjalan / Selesai
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    # Relasi ke data monitoring
    data_monitoring = db.relationship(
        "DataMonitoring", backref="session", lazy=True, order_by="DataMonitoring.timestamp"
    )

    def __repr__(self):
        return f"<HistoryPengeringan {self.nama_proses}>"


class DataMonitoring(db.Model):
    """
    Kelas DataMonitoring - sesuai Class Diagram
    Menyimpan data sensor secara real-time
    """

    __tablename__ = "data_monitoring"

    id = db.Column(db.Integer, primary_key=True)
    suhu_aktual = db.Column(db.Float, nullable=False)
    kelembaban = db.Column(db.Float, nullable=False)
    setpoint_suhu = db.Column(db.Float, nullable=False)
    output_pid = db.Column(db.Float, default=0.0)
    status_heater = db.Column(db.String(10), default="OFF")  # ON / OFF
    status_kipas = db.Column(db.String(10), default="OFF")  # ON / OFF
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    session_id = db.Column(
        db.Integer, db.ForeignKey("history_pengeringan.id"), nullable=True
    )

    def to_dict(self):
        """Konversi ke dictionary untuk API response"""
        return {
            "id": self.id,
            "suhu_aktual": self.suhu_aktual,
            "kelembaban": self.kelembaban,
            "setpoint_suhu": self.setpoint_suhu,
            "output_pid": self.output_pid,
            "status_heater": self.status_heater,
            "status_kipas": self.status_kipas,
            "timestamp": self.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "session_id": self.session_id,
        }

    def __repr__(self):
        return f"<DataMonitoring Suhu={self.suhu_aktual} RH={self.kelembaban}>"
