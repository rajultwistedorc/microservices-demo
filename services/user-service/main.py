import json
import os
import time

import psycopg2
import psycopg2.extras
import redis
from flask import Flask, jsonify, request

app = Flask(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@postgres:5432/microservices",
)
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
CACHE_TTL = int(os.getenv("CACHE_TTL", "60"))


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
                        CREATE TABLE IF NOT EXISTS users (
                            id SERIAL PRIMARY KEY,
                            email VARCHAR(255) UNIQUE NOT NULL,
                            name VARCHAR(255) NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                        """
                    )
                conn.commit()
            return
        except psycopg2.OperationalError:
            time.sleep(1)
    raise RuntimeError("Could not connect to PostgreSQL")


@app.route("/health", methods=["GET"])
def health():
    status = {"service": "user-service", "status": "ok"}
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


@app.route("/users", methods=["GET"])
def list_users():
    cache = get_redis()
    cached = cache.get("users:all")
    if cached:
        return jsonify(json.loads(cached))

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, email, name, created_at FROM users ORDER BY id")
            users = [dict(row) for row in cur.fetchall()]
            for user in users:
                if user.get("created_at"):
                    user["created_at"] = user["created_at"].isoformat()

    cache.setex("users:all", CACHE_TTL, json.dumps(users))
    return jsonify(users)


@app.route("/users/<int:user_id>", methods=["GET"])
def get_user(user_id):
    cache = get_redis()
    key = f"user:{user_id}"
    cached = cache.get(key)
    if cached:
        return jsonify(json.loads(cached))

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, name, created_at FROM users WHERE id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "User not found"}), 404
            user = dict(row)
            if user.get("created_at"):
                user["created_at"] = user["created_at"].isoformat()

    cache.setex(key, CACHE_TTL, json.dumps(user))
    return jsonify(user)


@app.route("/users", methods=["POST"])
def create_user():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()
    name = data.get("name", "").strip()
    if not email or not name:
        return jsonify({"error": "email and name are required"}), 400

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (email, name) VALUES (%s, %s) RETURNING id, email, name, created_at",
                    (email, name),
                )
                user = dict(cur.fetchone())
                conn.commit()
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "Email already exists"}), 409

    if user.get("created_at"):
        user["created_at"] = user["created_at"].isoformat()

    cache = get_redis()
    cache.delete("users:all")
    cache.setex(f"user:{user['id']}", CACHE_TTL, json.dumps(user))
    return jsonify(user), 201


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5001")))
