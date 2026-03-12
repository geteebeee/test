PYTHON ?= python
VENV ?= .venv
PIP := $(VENV)/bin/pip
PY := $(VENV)/bin/python

.PHONY: help venv install install-build test lint run clean build-windows

help:
	@echo "Targets:"
	@echo "  venv         Create local virtualenv"
	@echo "  install      Install runtime dependencies"
	@echo "  install-build Install runtime + build dependencies"
	@echo "  test         Run pytest suite"
	@echo "  lint         Compile-check python files"
	@echo "  run          Launch GUI app"
	@echo "  clean        Remove local caches/build artifacts"
	@echo "  build-windows Print Windows build guidance"

venv:
	$(PYTHON) -m venv $(VENV)

install: venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

install-build: venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-build.txt

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m py_compile msg_attachment_extractor.py test_msg_attachment_extractor.py

run:
	$(PYTHON) msg_attachment_extractor.py

clean:
	$(PYTHON) -c "import shutil,pathlib; [shutil.rmtree(p, ignore_errors=True) for p in [pathlib.Path('.pytest_cache'), pathlib.Path('__pycache__'), pathlib.Path('build'), pathlib.Path('dist')]]; [p.unlink() for p in pathlib.Path('.').glob('*.spec')]"

build-windows:
	@echo "Build on Windows with: build_windows_exe.bat"
	@echo "Artifact: dist\\MsgAttachmentInspector.exe"
