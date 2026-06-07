MAKEFILE_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
COMPOSE = docker compose -f $(MAKEFILE_DIR)docker-compose.yml

.PHONY: nano super llamarine down status logs help

help:
	@echo "Tilgængelige modeller:"
	@echo "  make nano      — Nemotron-3 Nano 30B NVFP4  (port 8002, ctx 170k)"
	@echo "  make super     — Nemotron-3 Super 120B NVFP4 (port 8002, ctx 32k)"
	@echo "  make llamarine — Llama-3.1-70B maritim, FP8 on-the-fly (port 8002, ctx 32k)"
	@echo ""
	@echo "Drift:"
	@echo "  make down    — Stop containeren"
	@echo "  make status  — Vis hvilken model der kører"
	@echo "  make logs    — Følg container-logs"

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

llamarine:
	VLLM_MODEL=pentagoniac/llamarine \
	VLLM_MAX_MODEL_LEN=32768 \
	VLLM_GPU_MEM_UTIL=0.80 \
	VLLM_EXTRA_ARGS="--quantization fp8 --enforce-eager" \
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

status:
	@curl -s http://localhost:8002/v1/models | python3 -m json.tool 2>/dev/null || echo "Ingen model kører på port 8002"

logs:
	$(COMPOSE) logs -f
