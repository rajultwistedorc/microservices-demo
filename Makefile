.PHONY: help build up down logs test smoke k8s-apply k8s-delete lint clean

COMPOSE := docker compose
K8S_DIR := kubernetes

help:
	@echo "Targets:"
	@echo "  build       Build all Docker images"
	@echo "  up          Start the full stack"
	@echo "  down        Stop and remove containers"
	@echo "  logs        Follow compose logs"
	@echo "  test        Run smoke test against running stack"
	@echo "  smoke       Alias for test"
	@echo "  lint        Run flake8 on Python services"
	@echo "  k8s-apply   Apply Kubernetes manifests"
	@echo "  k8s-delete  Delete Kubernetes resources"
	@echo "  clean       Remove compose volumes"

build:
	$(COMPOSE) build

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

lint:
	@for svc in user-service order-service notification-service; do \
		echo "Linting $$svc..."; \
		python -m flake8 services/$$svc/main.py --max-line-length=120 --extend-ignore=E501 || exit 1; \
	done

test smoke:
	@echo "Creating user..."
	@curl -sf -X POST http://localhost:8080/api/users \
		-H "Content-Type: application/json" \
		-d '{"email":"demo@example.com","name":"Demo User"}' | python -m json.tool
	@echo "Creating order..."
	@USER_ID=$$(curl -sf http://localhost:8080/api/users | python -c "import sys,json; print(json.load(sys.stdin)[0]['id'])"); \
	curl -sf -X POST http://localhost:8080/api/orders \
		-H "Content-Type: application/json" \
		-d "{\"user_id\":$$USER_ID,\"product\":\"Laptop\",\"quantity\":1}" | python -m json.tool
	@echo "Notifications:"
	@curl -sf http://localhost:8080/api/notifications | python -m json.tool

k8s-apply:
	kubectl apply -f $(K8S_DIR)/configmaps.yml
	kubectl apply -f $(K8S_DIR)/deployments.yml
	kubectl apply -f $(K8S_DIR)/services.yml

k8s-delete:
	kubectl delete -f $(K8S_DIR)/services.yml --ignore-not-found
	kubectl delete -f $(K8S_DIR)/deployments.yml --ignore-not-found
	kubectl delete -f $(K8S_DIR)/configmaps.yml --ignore-not-found

clean:
	$(COMPOSE) down -v
