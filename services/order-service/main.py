import json
import os
import time

import psycopg2
import psycopg2.extras
import redis
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@postgres:5432/microservices",
)
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://user-service:5001")
NOTIFICATION_CHANNEL = os.getenv("NOTIFICATION_CHANNEL", "notifications")


def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def get_redis():
    return redis.from_url(REDIS_URL, decode_responses=True)


def init_db():
    for attempt in range(30):
        try:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS orders (
                            id SERIAL PRIMARY KEY,
                            user_id INTEGER NOT NULL,
                            product VARCHAR(255) NOT NULL,
                            quantity INTEGER NOT NULL DEFAULT 1,
                            status VARCHAR(50) NOT NULL DEFAULT 'pending',
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                        """
                    )
                conn.commit()
            return
        except psycopg2.OperationalError:
            time.sleep(1)
    raise RuntimeError("Could not connect to PostgreSQL")


def publish_notification(event):
    get_redis().publish(NOTIFICATION_CHANNEL, json.dumps(event))


def verify_user(user_id):
    try:
        resp = requests.get(f"{USER_SERVICE_URL}/users/{user_id}", timeout=5)
        return resp.status_code == 200
    except requests.RequestException:
        return False


@app.route("/health", methods=["GET"])
def health():
    status = {"service": "order-service", "status": "ok"}
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        status["postgres"] = "ok"
    except Exception as exc:
        status["postgres"] = str(exc)
        status["status"] = "degraded"
    try:
        get_redis().ping()
        status["redis"] = "ok"
    except Exception as exc:
        status["redis"] = str(exc)
        status["status"] = "degraded"
    code = 200 if status["status"] == "ok" else 503
    return jsonify(status), code


@app.route("/orders", methods=["GET"])
def list_orders():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, user_id, product, quantity, status, created_at FROM orders ORDER BY id"
            )
            orders = [dict(row) for row in cur.fetchall()]
            for order in orders:
                if order.get("created_at"):
                    order["created_at"] = order["created_at"].isoformat()
    return jsonify(orders)


@app.route("/orders/<int:order_id>", methods=["GET"])
def get_order(order_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, user_id, product, quantity, status, created_at FROM orders WHERE id = %s",
                (order_id,),
            )
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Order not found"}), 404
            order = dict(row)
            if order.get("created_at"):
                order["created_at"] = order["created_at"].isoformat()
    return jsonify(order)


@app.route("/orders", methods=["POST"])
def create_order():
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    product = (data.get("product") or "").strip()
    quantity = data.get("quantity", 1)

    if user_id is None or not product:
        return jsonify({"error": "user_id and product are required"}), 400

    try:
        user_id = int(user_id)
        quantity = int(quantity)
    except (TypeError, ValueError):
        return jsonify({"error": "user_id and quantity must be integers"}), 400

    if quantity < 1:
        return jsonify({"error": "quantity must be at least 1"}), 400

    if not verify_user(user_id):
        return jsonify({"error": "User not found"}), 404

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO orders (user_id, product, quantity, status)
                VALUES (%s, %s, %s, 'confirmed')
                RETURNING id, user_id, product, quantity, status, created_at
                """,
                (user_id, product, quantity),
            )
            order = dict(cur.fetchone())
            conn.commit()

    if order.get("created_at"):
        order["created_at"] = order["created_at"].isoformat()

    publish_notification(
        {
            "type": "order_created",
            "order_id": order["id"],
            "user_id": order["user_id"],
            "product": order["product"],
            "quantity": order["quantity"],
        }
    )
    return jsonify(order), 201


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5002")))
