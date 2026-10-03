import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify
from shared.infrastructure.queue import RedisQueue
from shared.infrastructure.queue_config import (
    WHATSAPP_IN,
    WHATSAPP_IN_TOPIC,
    WHATSAPP_OUT,
    WHATSAPP_OUT_TOPIC,
)
from shared.infrastructure.telemetry import setup_telemetry, attach_otel_to_loggers
from opentelemetry.instrumentation.flask import FlaskInstrumentor

setup_telemetry("whatsapp_api", "1.0.0")
attach_otel_to_loggers("werkzeug", "flask")

app = Flask(__name__)
FlaskInstrumentor().instrument_app(app)
queue = RedisQueue()

@app.route("/", methods=["GET"])
def health_check():
    return jsonify({"status": "ok"}), 200

@app.route("/messages", methods=["POST"])
def send_message():
    data = request.json
    if not data or "cellphone" not in data or "message" not in data:
        return jsonify({"error": "Missing 'cellphone' or 'message' in request body."}), 400
    
    queue.enqueue(WHATSAPP_OUT, data, WHATSAPP_OUT_TOPIC)
    return jsonify({"status": "Message enqueued successfully.", "queue": WHATSAPP_OUT}), 202

@app.route("/incoming-whatsapp", methods=["POST"])
def incoming_whatsapp():
    data = request.json
    queue.enqueue(WHATSAPP_IN, data, WHATSAPP_IN_TOPIC)
    return jsonify({"status": "received", "enqueued": True}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
