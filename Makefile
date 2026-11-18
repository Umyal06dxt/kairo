.PHONY: install ui ui-dev serve test test-py test-web lint check clean-ui

PY ?= .venv/bin/python

install:            ## Python deps (editable) and web deps
	python3 -m venv .venv && .venv/bin/pip install -e '.[dev,voice,qdrant,local,web]'
	cd web && npm install

ui:                 ## Build the React app into src/kairo/server/static
	cd web && npm run build

ui-dev:             ## Vite dev server with hot reload (proxies the API on :8000)
	cd web && npm run dev

serve: ui           ## Build the UI and start the lab on http://127.0.0.1:8000
	.venv/bin/kairo serve

test-py:
	$(PY) -m pytest -q

test-web:
	cd web && npm run check

test: test-py test-web   ## Everything

lint:
	$(PY) -m pyflakes src tests && cd web && npm run lint

check: lint test

clean-ui:
	find src/kairo/server/static -mindepth 1 ! -name .gitkeep -delete
