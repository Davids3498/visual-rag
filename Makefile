.PHONY: help setup setup-retrieval env data sanity db-up db-down baseline lint test clean

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

lint:  ## ruff check + format check
	uv run --group dev ruff check .
	uv run --group dev ruff format --check .

test:  ## pytest
	uv run --group dev pytest -q

clean:  ## drop generated artifacts (keeps the HF cache)
	rm -rf data/eval data/embeddings data/runs reports/sanity reports/*.json
