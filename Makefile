.PHONY: start test lint build fine-tune

start:
	uvicorn jarvis.main:app --reload

test:
	python -m unittest discover -s jarvis/tests/

lint:
	flake8 jarvis/
	mypy jarvis/

build:
	cd extension && pnpm run compile

fine-tune:
	@echo "Fine-tuning pipeline not yet implemented in Phase 1"
