MAKEFILE_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
COMPOSE = docker compose -f $(MAKEFILE_DIR)docker-compose.yml

.PHONY: nano super down status logs help

help:
	@echo "Available models:"
	@echo "  make nano    — Nemotron-3 Nano 30B NVFP4  (port 8002, ctx 170k)"
	@echo "  make super   — Nemotron-3 Super 120B NVFP4 (port 8002, ctx 32k)"
	@echo ""
	@echo "Operations:"
	@echo "  make down    — Stop the container"
	@echo "  make status  — Show which model is running"
	@echo "  make logs    — Follow container logs"

nano:
	VLLM_MODEL=nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-NVFP4 \
	VLLM_MAX_MODEL_LEN=170000 \
	VLLM_GPU_MEM_UTIL=0.70 \
	$(COMPOSE) up -d

super:
	VLLM_MODEL=nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4 \
	VLLM_MAX_MODEL_LEN=32768 \
	VLLM_GPU_MEM_UTIL=0.82 \
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

status:
	@curl -s http://localhost:8002/v1/models | python3 -m json.tool 2>/dev/null || echo "No model running on port 8002"

logs:
	$(COMPOSE) logs -f
