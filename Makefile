PYTHON ?= .venv/bin/python

.PHONY: install test test-python test-browser build api dev
install:
	npm install
	$(PYTHON) -m pip install -e ./packages/commsfail -e "./packages/agenttrace-api[dev,scout]"

test: test-python
	npm test

test-python:
	$(PYTHON) -m pytest packages/commsfail/tests packages/agenttrace-api/tests

test-browser: build
	AGENTTRACE_BROWSER_TESTS=1 $(PYTHON) -m pytest packages/agenttrace-api/tests/test_browser.py

build:
	npm run build

api:
	$(PYTHON) -m uvicorn agenttrace.api:create_app --factory --host 127.0.0.1 --port 3000 --reload

dev:
	npm run dev
