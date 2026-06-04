import json
import os
import threading
import time
from collections import deque

import redis
from flask import Flask, jsonify, request

app = Flask(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
NOTIFICATION_CHANNEL = os.getenv("NOTIFICATION_CHANNEL", "notifications")
MAX_NOTIFICATIONS = int(os.getenv("MAX_NOTIFICATIONS", "100"))

notifications = deque(maxlen=MAX_NOTIFICATIONS)
_listener_started = False


def get_redis():
    return redis.from_url(REDIS_URL, decode_responses=True)


def listen_for_notifications():
    r = get_redis()
    pubsub = r.pubsub()
    pubsub.subscribe(NOTIFICATION_CHANNEL)
    for message in pubsub.listen():
        if message["type"] != "message":
            continue
        try:
            payload = json.loads(message["data"])
        except json.JSONDecodeError:
            payload = {"raw": message["data"]}
        payload["received_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        notifications.appendleft(payload)


def start_listener():
    global _listener_started
    if _listener_started:
        return
    _listener_started = True
    thread = threading.Thread(target=listen_for_notifications, daemon=True)
    thread.start()


@app.route("/health", methods=["GET"])
def health():
    status = {"service": "notification-service", "status": "ok", "listener": _listener_started}
    try:
        get_redis().ping()
        status["redis"] = "ok"
    except Exception as exc:
        status["redis"] = str(exc)
        status["status"] = "degraded"
    code = 200 if status["status"] == "ok" else 503
    return jsonify(status), code


@app.route("/notifications", methods=["GET"])
def list_notifications():
    limit = request.args.get("limit", default=20, type=int)
    limit = max(1, min(limit, MAX_NOTIFICATIONS))
    return jsonify(list(notifications)[:limit])


@app.route("/notifications", methods=["POST"])
def send_notification():
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"error": "JSON body required"}), 400
    data["received_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    get_redis().publish(NOTIFICATION_CHANNEL, json.dumps(data))
    notifications.appendleft(data)
    return jsonify(data), 201


start_listener()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5003")))
