IMAGE_NAME ?= daindragon2/experimental-metrics
PLATFORMS ?= linux/amd64,linux/arm64
PROJECT_FOLDER ?= $(CURDIR)/..
NETWORK_PLAN ?=

.PHONY: build
build:
	docker build -t $(IMAGE_NAME):latest .

.PHONY: push
push:
	docker buildx build \
		--platform $(PLATFORMS) \
		-t $(IMAGE_NAME):latest \
		--push .

.PHONY: run
# Previous implementation:
# run:
# 	@if [ -z "$(PROJECT_FOLDER)" ]; then echo "PROJECT_FOLDER is required"; exit 1; fi
# 	docker run --rm \
# 		--net=host \
# 		--privileged \
# 		-v /var/run/docker.sock:/var/run/docker.sock \
# 		-v $(PROJECT_FOLDER):/workspace/project \
# 		-w /workspace/project \
# 		$(IMAGE_NAME):latest deployment-times --dir /workspace/project
# Updated implementation:
# Rebuild image before execution to avoid stale CLI/runtime mismatches.
run: build
	@if [ -z "$(PROJECT_FOLDER)" ]; then echo "PROJECT_FOLDER is required"; exit 1; fi
	# Previous implementation:
	# docker run ... -v $(PROJECT_FOLDER):/workspace/project -w /workspace/project ...
	# Updated implementation:
	# Mount the parent directory to preserve relative includes like `include ../metrics.mk`.
	@PROJECT_ABS="$$(realpath "$(PROJECT_FOLDER)")"; \
	PROJECT_PARENT="$$(dirname "$$PROJECT_ABS")"; \
	PROJECT_BASENAME="$$(basename "$$PROJECT_ABS")"; \
	echo "[metrics-collector] project=$$PROJECT_ABS parent=$$PROJECT_PARENT"; \
	docker run --rm \
		--net=host \
		--privileged \
		-v /var/run/docker.sock:/var/run/docker.sock \
		-v "$$PROJECT_PARENT":/workspace \
		-w /workspace/$$PROJECT_BASENAME \
		$(IMAGE_NAME):latest deployment-times --dir=/workspace/$$PROJECT_BASENAME

.PHONY: run-cpu-memory
# Previous implementation:
# run-cpu-memory:
# 	@if [ -z "$(PROJECT_FOLDER)" ]; then echo "PROJECT_FOLDER is required"; exit 1; fi
# 	docker run --rm \
# 		--net=host \
# 		-v /var/run/docker.sock:/var/run/docker.sock \
# 		-v $(PROJECT_FOLDER):/workspace/project \
# 		-w /workspace/project \
# 		$(IMAGE_NAME):latest cpu-memory-utilization --dir /workspace/project
# Updated implementation:
# Rebuild image before execution to avoid stale CLI/runtime mismatches.
run-cpu-memory: build
	@if [ -z "$(PROJECT_FOLDER)" ]; then echo "PROJECT_FOLDER is required"; exit 1; fi
	# Previous implementation:
	# docker run ... -v $(PROJECT_FOLDER):/workspace/project -w /workspace/project ...
	# Updated implementation:
	# Mount the parent directory to preserve relative includes like `include ../metrics.mk`.
	@PROJECT_ABS="$$(realpath "$(PROJECT_FOLDER)")"; \
	PROJECT_PARENT="$$(dirname "$$PROJECT_ABS")"; \
	PROJECT_BASENAME="$$(basename "$$PROJECT_ABS")"; \
	echo "[metrics-collector] project=$$PROJECT_ABS parent=$$PROJECT_PARENT"; \
	docker run --rm \
		--net=host \
		-v /var/run/docker.sock:/var/run/docker.sock \
		-v "$$PROJECT_PARENT":/workspace \
		-w /workspace/$$PROJECT_BASENAME \
		$(IMAGE_NAME):latest cpu-memory-utilization --dir=/workspace/$$PROJECT_BASENAME

.PHONY: run-network
# Previous implementation:
# run-network:
# 	@if [ -z "$(PROJECT_FOLDER)" ]; then echo "PROJECT_FOLDER is required"; exit 1; fi
# 	docker run --rm \
# 		--net=host \
# 		-v /var/run/docker.sock:/var/run/docker.sock \
# 		-v $(PROJECT_FOLDER):/workspace/project \
# 		-w /workspace/project \
# 		$(if $(NETWORK_PLAN),-v $(NETWORK_PLAN):/workspace/network-plan.json,) \
# 		$(IMAGE_NAME):latest network-latency-overhead --dir /workspace/project $(if $(NETWORK_PLAN),--network-plan /workspace/network-plan.json,)
# Updated implementation:
# Rebuild image before execution to avoid stale CLI/runtime mismatches.
run-network: build
	@if [ -z "$(PROJECT_FOLDER)" ]; then echo "PROJECT_FOLDER is required"; exit 1; fi
	# Previous implementation:
	# docker run ... -v $(PROJECT_FOLDER):/workspace/project -w /workspace/project ...
	# Updated implementation:
	# Mount the parent directory to preserve relative includes like `include ../metrics.mk`.
	@PROJECT_ABS="$$(realpath "$(PROJECT_FOLDER)")"; \
	PROJECT_PARENT="$$(dirname "$$PROJECT_ABS")"; \
	PROJECT_BASENAME="$$(basename "$$PROJECT_ABS")"; \
	echo "[metrics-collector] project=$$PROJECT_ABS parent=$$PROJECT_PARENT"; \
	docker run --rm \
		--net=host \
		-v /var/run/docker.sock:/var/run/docker.sock \
		-v "$$PROJECT_PARENT":/workspace \
		-w /workspace/$$PROJECT_BASENAME \
		$(if $(NETWORK_PLAN),-v $(NETWORK_PLAN):/workspace/network-plan.json,) \
		$(IMAGE_NAME):latest network-latency-overhead --dir=/workspace/$$PROJECT_BASENAME $(if $(NETWORK_PLAN),--network-plan=/workspace/network-plan.json,)
