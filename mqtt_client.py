"""
MQTT Client untuk SIKAKAO
Sesuai Flowchart MQTT (Gambar 3.5) dan Tabel 3.9 Mekanisme Pengiriman Data

Arsitektur: ESP32 (Publisher) -> MQTT Broker -> Web App (Subscriber)
                                  MQTT Broker <- Web App (Publisher) -> ESP32 (Subscriber)
"""

import json
import threading
import time

import paho.mqtt.client as mqtt

from config import Config


class SIKAKAOMQTTClient:
    """MQTT Client untuk komunikasi antara Web App dan ESP32"""

    def __init__(self, app=None):
        self.app = app
        self.client = None
        self.connected = False
        self.latest_data = {
            "suhu_aktual": 0.0,
            "kelembaban": 0.0,
            "output_pid": 0.0,
            "setpoint_suhu": 50.0,
            "status_heater": "OFF",
            "status_kipas": "OFF",
            "esp32_connected": False,
            "last_update": None,
        }
        self._callbacks = []
        self._lock = threading.Lock()

    def init_app(self, app):
        """Inisialisasi MQTT client dengan Flask app"""
        self.app = app
        self.client = mqtt.Client(
            client_id="sikakao-web-" + str(int(time.time())),
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        # Start connection in background thread
        thread = threading.Thread(target=self._connect, daemon=True)
        thread.start()

    def _connect(self):
        """Koneksi ke MQTT Broker - sesuai Flowchart MQTT step 6-7"""
        try:
            self.client.connect(
                Config.MQTT_BROKER_HOST,
                Config.MQTT_BROKER_PORT,
                Config.MQTT_KEEPALIVE,
            )
            self.client.loop_forever()
        except Exception as e:
            print(f"[MQTT] Connection error: {e}")
            # Auto-reconnect sesuai skenario gangguan jaringan (3.12.5)
            time.sleep(5)
            self._connect()

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        """Callback saat berhasil terhubung ke broker"""
        if reason_code == 0:
            self.connected = True
            print("[MQTT] Connected to broker successfully")

            # Subscribe ke semua topik dari ESP32 (Tabel 3.9)
            client.subscribe(Config.MQTT_TOPIC_SUHU)
            client.subscribe(Config.MQTT_TOPIC_KELEMBABAN)
            client.subscribe(Config.MQTT_TOPIC_OUTPUT_PID)
            client.subscribe(Config.MQTT_TOPIC_STATUS_HEATER)
            client.subscribe(Config.MQTT_TOPIC_STATUS_KIPAS)

            print("[MQTT] Subscribed to all sensor topics")
        else:
            print(f"[MQTT] Connection failed with code: {reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        """Callback saat terputus - auto reconnect (sesuai skenario 3.12.5)"""
        self.connected = False
        with self._lock:
            self.latest_data["esp32_connected"] = False
        print(f"[MQTT] Disconnected. Reason: {reason_code}")

    def _on_message(self, client, userdata, msg):
        """
        Callback saat menerima data dari ESP32
        Data disimpan ke latest_data dan di-forward ke callback
        """
        try:
            topic = msg.topic
            payload = msg.payload.decode("utf-8")

            with self._lock:
                self.latest_data["esp32_connected"] = True
                self.latest_data["last_update"] = time.strftime("%Y-%m-%d %H:%M:%S")

                if topic == Config.MQTT_TOPIC_SUHU:
                    self.latest_data["suhu_aktual"] = float(payload)
                elif topic == Config.MQTT_TOPIC_KELEMBABAN:
                    self.latest_data["kelembaban"] = float(payload)
                elif topic == Config.MQTT_TOPIC_OUTPUT_PID:
                    self.latest_data["output_pid"] = float(payload)
                elif topic == Config.MQTT_TOPIC_STATUS_HEATER:
                    self.latest_data["status_heater"] = payload.upper()
                elif topic == Config.MQTT_TOPIC_STATUS_KIPAS:
                    self.latest_data["status_kipas"] = payload.upper()

            # Notify semua callback (untuk SSE dan database saving)
            for callback in self._callbacks:
                try:
                    callback(self.latest_data.copy())
                except Exception as e:
                    print(f"[MQTT] Callback error: {e}")

        except Exception as e:
            print(f"[MQTT] Message processing error: {e}")

    def register_callback(self, callback):
        """Register callback untuk menerima update data"""
        self._callbacks.append(callback)

    def get_latest_data(self):
        """Ambil data terbaru"""
        with self._lock:
            return self.latest_data.copy()

    def publish_setpoint(self, setpoint):
        """
        Publish setpoint suhu ke ESP32
        Topic: sikakao/setpoint
        """
        if self.client and self.connected:
            self.client.publish(Config.MQTT_TOPIC_SETPOINT, str(setpoint), qos=1)
            with self._lock:
                self.latest_data["setpoint_suhu"] = setpoint
            print(f"[MQTT] Published setpoint: {setpoint}°C")
            return True
        return False

    def publish_command(self, command):
        """
        Publish perintah start/stop ke ESP32
        Topic: sikakao/command
        """
        if self.client and self.connected:
            self.client.publish(Config.MQTT_TOPIC_COMMAND, command, qos=1)
            print(f"[MQTT] Published command: {command}")
            return True
        return False

    def is_connected(self):
        """Cek status koneksi MQTT"""
        return self.connected


# Singleton instance
mqtt_client = SIKAKAOMQTTClient()
