import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "sikakao-secret-key-2026")

    # SQLite Database
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "sikakao.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # MQTT Broker Configuration
    MQTT_BROKER_HOST = os.environ.get("MQTT_BROKER_HOST", "broker.hivemq.com")
    MQTT_BROKER_PORT = int(os.environ.get("MQTT_BROKER_PORT", 1883))
    MQTT_KEEPALIVE = 60

    # MQTT Topics (Mekanisme Pengiriman Data)
    MQTT_TOPIC_SUHU = "sikakao/suhu"
    MQTT_TOPIC_KELEMBABAN = "sikakao/kelembaban"
    MQTT_TOPIC_OUTPUT_PID = "sikakao/outputpid"
    MQTT_TOPIC_STATUS_HEATER = "sikakao/status/heater"
    MQTT_TOPIC_STATUS_KIPAS = "sikakao/status/kipas"
    MQTT_TOPIC_SETPOINT = "sikakao/setpoint"
    MQTT_TOPIC_COMMAND = "sikakao/command"

    # PID Parameters (sesuai skenario sistem pada skripsi)
    PID_KP = 5.0
    PID_KI = 0.5
    PID_KD = 2.0
    PID_SETPOINT_MIN = 40  # °C
    PID_SETPOINT_MAX = 60  # °C
    PID_OUTPUT_MIN = 0     # %
    PID_OUTPUT_MAX = 100   # %
    TPC_PERIOD = 10        # detik (Time Proportioning Control period)

    # Threshold pengeringan selesai
    RH_THRESHOLD = 40  # Kelembaban ≤ 40% = selesai
