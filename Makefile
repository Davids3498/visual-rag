.PHONY: help setup setup-retrieval env data sanity db-up db-down serve-up serve-down baseline visual calibrate generate k8s-up k8s-verify k8s-down bench corpus corpus-record corpus-verify pages pages-rebuild lint test clean

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

setup:  ## create the pinned venv (Part 0-1 deps only)
	uv sync

setup-retrieval:  ## add torch / bge-m3 / pgvector client (steps 2-3)
	uv sync --extra retrieval

env:  ## environment + GPU report -> reports/env_report.json
	uv run python scripts/00_check_env.py

data:  ## download ViDoRe V3, verify counts, build eval set -> data/eval/
	uv run python scripts/01_load_inspect.py

sanity:  ## render sample pages with gold spans -> reports/sanity/
	uv run python scripts/02_sanity_render.py

db-up:  ## start the pgvector container (port 5434)
	docker compose up -d --wait

db-down:  ## stop it (keeps the volume)
	docker compose down

baseline:  ## step 2: embed markdown with BGE-M3, index in pgvector, score NDCG@10
	uv run python scripts/03_text_baseline.py

visual:  ## step 3: ColQwen2 page-image embeddings, two-stage ANN + MaxSim rerank
	uv run python scripts/04_visual_retrieval.py

calibrate:  ## step 4: compare both runs against the published industrial numbers
	uv run python scripts/05_calibration.py

serve-up:  ## start the quantized Qwen2.5-VL on vLLM (port 8000)
	docker compose --profile serving up -d vllm

serve-down:  ## stop it and give the GPU back
	docker compose --profile serving stop vllm

generate:  ## step 5: RAG answers from page images, with citations
	uv run python scripts/06_generate.py

k8s-up:  ## deploy pgvector + vLLM to the local cluster (OVERLAY=k3s|minikube)
	kubectl apply -k k8s/overlays/$(or $(OVERLAY),k3s)
	kubectl rollout status -n visual-rag statefulset/pgvector --timeout=300s
	kubectl rollout status -n visual-rag deployment/vllm --timeout=1200s

k8s-verify:  ## check GPU scheduling, pod health and a real request -> reports/k8s.json
	uv run python scripts/07_k8s_verify.py

k8s-down:  ## remove the workloads (keeps the cluster and its volumes)
	kubectl delete -k k8s/overlays/$(or $(OVERLAY),k3s) --ignore-not-found

bench:  ## step 7: latency/throughput/GPU/cost at concurrency 1,4,16 -> reports/serving.json
	uv run python scripts/08_serving_bench.py

corpus:  ## step 9: fetch the MCU corpus from the manifest, verify every pinned hash
	uv run python scripts/09_fetch_corpus.py

corpus-record:  ## first collect: download and pin each document's hash into the manifest
	uv run python scripts/09_fetch_corpus.py --record

corpus-verify:  ## offline: re-hash the local PDFs against the manifest, no network
	uv run python scripts/09_fetch_corpus.py --verify-only

pages:  ## step 10: render the selected pages to images -> data/mcu/pages/
	uv run python scripts/10_build_pages.py

pages-rebuild:  ## re-render every page (e.g. after changing the resolution)
	uv run python scripts/10_build_pages.py --rebuild

lint:  ## ruff check + format check
	uv run --group dev ruff check .
	uv run --group dev ruff format --check .

test:  ## pytest
	uv run --group dev pytest -q

clean:  ## drop generated artifacts (keeps the HF cache)
	rm -rf data/eval data/embeddings data/runs reports/sanity reports/*.json
