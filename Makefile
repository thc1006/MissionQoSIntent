.PHONY: sync test cov lint type all policy-test golden-update e2e e1 e2

UV ?= uv
OPA ?= opa

sync:
	$(UV) sync

test:
	$(UV) run pytest -q

cov:
	$(UV) run pytest --cov=mqi --cov-report=term-missing --cov-fail-under=90

lint:
	$(UV) run ruff check .

type:
	$(UV) run mypy --strict src tests

all: lint type cov

policy-test:
	$(OPA) test policy -v --coverage --fail-on-empty

golden-update:
	MQI_GOLDEN_UPDATE=1 $(UV) run pytest tests/renderers -q

# Full real-cluster E2E (kind + DRA + Kueue + GAIE + L2/L3 service). NOT part of `all` — heavy.
# Pass flags via E2E_FLAGS, e.g. `make e2e E2E_FLAGS=--keep`.
E2E_FLAGS ?=
e2e:
	bash ./test/e2e/run.sh $(E2E_FLAGS)

# E1 experiment: consistency + policy-guard over the seeded corpus (offline; real OPA guard).
e1:
	$(UV) run python experiments/e1/run.py

# E2 experiment: control-path value vs data-path throughput (real vLLM on GPU + real L2/L3 gate).
# Run on the cluster host (needs the mqi-exp vLLM deployment + kubectl + curl).
e2:
	bash ./experiments/e2/run.sh
