# Microservices Demo

A small Flask-based microservices stack for learning Docker, Kubernetes, and CI/CD patterns.

## Architecture

```
                    ┌─────────────┐
                    │ API Gateway │  :8080 (nginx)
                    └──────┬──────┘
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌────────────┐  ┌────────────┐  ┌──────────────────┐
    │User Service│  │Order Service│  │Notification Svc │
    │   :5001    │  │   :5002     │  │      :5003      │
    └─────┬──────┘  └──────┬──────┘  └────────┬─────────┘
          │               │                     │
          └───────┬───────┴─────────────────────┘
                  ▼
         ┌────────────────┐
         │ Postgres + Redis│
         └────────────────┘
```

- **user-service**: CRUD users in PostgreSQL with Redis caching
- **order-service**: Creates orders, validates users via HTTP, publishes events to Redis
- **notification-service**: Subscribes to Redis pub/sub and exposes recent notifications
- **api-gateway**: Nginx reverse proxy with `/api/*` routes

## Quick Start

```bash
# Start everything
make up

# Smoke test
make test

# View logs
make logs

# Stop
make down
```

Gateway: http://localhost:8080

## API Examples

```bash
# Health
curl http://localhost:8080/health

# Create user
curl -X POST http://localhost:8080/api/users \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","name":"Alice"}'

# List users
curl http://localhost:8080/api/users

# Create order (replace USER_ID)
curl -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"user_id":1,"product":"Keyboard","quantity":2}'

# List notifications
curl http://localhost:8080/api/notifications
```

Direct service ports (without gateway): 5001, 5002, 5003.

## Kubernetes

Build images locally, then apply manifests:

```bash
docker build -t microservices-demo/user-service:latest services/user-service
docker build -t microservices-demo/order-service:latest services/order-service
docker build -t microservices-demo/notification-service:latest services/notification-service

make k8s-apply
```

API gateway NodePort: **30080**

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs lint, Docker builds, and a compose smoke test on push/PR.

## Project Layout

```
microservices-demo/
├── docker-compose.yml
├── Makefile
├── README.md
├── .github/workflows/ci.yml
├── kubernetes/
│   ├── configmaps.yml
│   ├── deployments.yml
│   └── services.yml
└── services/
    ├── api-gateway/
    ├── user-service/
    ├── order-service/
    └── notification-service/
```

## Environment Variables

| Variable | Default | Used by |
|----------|---------|---------|
| `DATABASE_URL` | `postgresql://postgres:postgres@postgres:5432/microservices` | user, order |
| `REDIS_URL` | `redis://redis:6379/0` | all |
| `USER_SERVICE_URL` | `http://user-service:5001` | order |
| `NOTIFICATION_CHANNEL` | `notifications` | order, notification |
