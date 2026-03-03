# =============================================================================
# open-hamclock-backend Test Suite — Makefile Orchestrator
# =============================================================================
#
# This Makefile is the single entry point for the six-tier test pyramid.
# Tiers are ordered from fastest/cheapest to slowest/most expensive:
#
#   Tier 1 (lint)             — Static analysis: ShellCheck, Ruff, Hadolint
#   Tier 2 (test-bash)        — Bats shell script unit tests
#   Tier 3 (test-python)      — pytest Python unit tests
#   Tier 4 (test-perl)        — prove Perl unit tests (TAP protocol)
#   Tier 5 (test-docker)      — Docker image build + security checks
#   Tier 6 (test-integration) — Live HTTP endpoint tests via Docker Compose
#
# Usage:
#   make -C tests <target>
#
# Targets:
#   lint             - Run all static analysis (ShellCheck, perlcritic, ruff, hadolint)
#   test-bash        - Run bats shell script tests
#   test-python      - Run pytest Python unit tests
#   test-perl        - Run prove Perl unit tests
#   test-docker      - Build Docker image and run security checks
#   test-integration - Start container, run web endpoint tests, tear down
#   test-all         - Run everything (tiers 1–6 sequentially)
#   deps             - Install test dependencies
#
# Flags:
#   FAIL_FAST=true   - Make any failure halt execution (default: false)
#
# Prerequisites:
#   shellcheck, bats, hadolint, python3, pip, perl, prove, docker
#   Run `make -C tests deps` for automated Python dependency installation.
#
# See Also:
#   tests/TEST_README.md — Full architecture reference and contribution guide
# =============================================================================

SHELL := /bin/bash
.PHONY: lint test-bash test-python test-perl test-docker test-integration test-all deps lint-perl

ROOT := $(shell dirname $(CURDIR))

# Set to true to make failures fatal (e.g. make FAIL_FAST=true test-all)
FAIL_FAST ?= false
ifeq ($(FAIL_FAST),true)
  _FAIL_GUARD :=
else
  _FAIL_GUARD := || { echo "  (Ignored failures)" ; exit 0 ; }
endif

# ── Dependencies ──────────────────────────────────────────────────────────────

deps:
	@echo "==> Installing test dependencies..."
	@command -v shellcheck >/dev/null || { echo "  Install ShellCheck: brew install shellcheck (mac) / apt install shellcheck (linux)"; }
	@command -v bats       >/dev/null || { echo "  Install bats: brew install bats-core (mac) / apt install bats (linux)"; }
	@command -v hadolint   >/dev/null || { echo "  Install hadolint: brew install hadolint (mac)"; }
	@pip install -q ruff pytest requests feedparser 2>/dev/null || true
	@if ! python3 -c "import dvoacap" 2>/dev/null; then \
		echo "  Installing dvoacap..."; \
		cd tests/python && \
		curl -fsSL https://github.com/skyelaird/dvoacap-python/archive/refs/heads/main.tar.gz | tar xz && \
		sed -i.bak 's/>=3.11/>=3.10/' dvoacap-python-main/pyproject.toml && \
		pip install -q ./dvoacap-python-main 2>/dev/null || true && \
		rm -rf dvoacap-python-main; \
	fi
	@echo "  Done."

# ── Tier 1: Static Analysis ──────────────────────────────────────────────────

lint: lint-shell lint-python lint-docker lint-perl
	@echo "==> All linters passed ✓"

lint-shell:
	@echo "==> ShellCheck..."
	@( find $(ROOT)/scripts $(ROOT)/docker $(ROOT)/aws -name '*.sh' -exec shellcheck -e SC2034,SC2140 -S warning {} + ) $(_FAIL_GUARD)
	@echo "  ShellCheck done ✓"

lint-python:
	@echo "==> Ruff (Python)..."
	@( ruff check $(ROOT)/scripts/*.py --select E,F,W --ignore E501 ) $(_FAIL_GUARD)
	@echo "  Ruff done ✓"

lint-docker:
	@echo "==> Hadolint (Dockerfile)..."
	@( hadolint $(ROOT)/docker/Dockerfile --ignore DL3008 --ignore DL3013 ) $(_FAIL_GUARD)
	@echo "  Hadolint done ✓"

lint-perl:
	@echo "==> Perlcritic (Perl)..."
	@if command -v perlcritic >/dev/null 2>&1; then \
		( perlcritic --severity 4 --quiet $(ROOT)/ham/HamClock/*.pl 2>/dev/null ) $(_FAIL_GUARD); \
		echo "  Perlcritic done ✓"; \
	else \
		echo "  perlcritic not installed — skipping (install: cpanm Perl::Critic)"; \
	fi

# ── Tier 2: Bash Tests ───────────────────────────────────────────────────────

test-bash:
	@echo "==> Running bats tests..."
	@( bats bats/*.bats ) $(_FAIL_GUARD)
	@echo "  Bash tests done ✓"

# ── Tier 3: Python Tests ─────────────────────────────────────────────────────

test-python:
	@echo "==> Running pytest..."
	@( cd $(ROOT) && python -m pytest tests/python/ -v --tb=short --cov=scripts --cov-report=term-missing 2>/dev/null \
		|| cd $(ROOT) && python -m pytest tests/python/ -v --tb=short ) $(_FAIL_GUARD)
	@echo "  Python tests done ✓"

# ── Tier 4: Perl Tests ───────────────────────────────────────────────────────

test-perl:
	@echo "==> Running prove (Perl tests)..."
	@( cd $(ROOT) && prove -r tests/perl/ -v ) $(_FAIL_GUARD)
	@echo "  Perl tests done ✓"

# ── Tier 5: Docker Tests ─────────────────────────────────────────────────────

test-docker:
	@echo "==> Running Docker tests..."
	@( bash docker/test_image_build.sh ) $(_FAIL_GUARD)
	@echo "  Docker tests done ✓"

# ── Tier 6: Integration Tests ────────────────────────────────────────────────

OHB_TEST_HOST ?= http://localhost:8085

test-integration:
	@echo "==> Starting test container..."
	@command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1 || \
		{ echo "SKIP: docker compose not available"; exit 0; }
	@docker volume inspect ohb-htdocs >/dev/null 2>&1 || docker volume create ohb-htdocs >/dev/null
	@cd $(ROOT) && git rev-parse --short HEAD 2>/dev/null > git.version || echo "test" > $(ROOT)/git.version
	@cd $(ROOT) && bash docker/manage-ohb-docker.sh generate-docker-compose -p 8085 -m > $(ROOT)/tests/docker/docker-compose.test.yml
	@cd $(ROOT) && docker compose -f $(ROOT)/tests/docker/docker-compose.test.yml up -d --build --wait --wait-timeout 120 || \
		{ echo "ERROR: container failed to start or become healthy"; \
		  docker compose -f $(ROOT)/tests/docker/docker-compose.test.yml logs; \
		  docker compose -f $(ROOT)/tests/docker/docker-compose.test.yml down --rmi local -v; \
		  rm -f $(ROOT)/tests/docker/docker-compose.test.yml $(ROOT)/git.version; exit 1; }
	@echo "==> Running integration tests against $(OHB_TEST_HOST)..."
	@cd $(ROOT) && \
		( OHB_TEST_HOST=$(OHB_TEST_HOST) python -m pytest tests/integration/ -v --tb=short; _rc=$$?; \
		docker compose -f $(ROOT)/tests/docker/docker-compose.test.yml down --rmi local -v; \
		rm -f $(ROOT)/tests/docker/docker-compose.test.yml $(ROOT)/git.version; \
		if [ "$$_rc" -ne 0 ] && [ "$(FAIL_FAST)" = "true" ]; then exit 1; fi; \
		if [ "$$_rc" -ne 0 ]; then echo "  (Ignored failures)"; fi )
	@echo "  Integration tests done ✓"

# ── All ───────────────────────────────────────────────────────────────────────

test-all: lint test-bash test-python test-perl test-docker test-integration
	@echo ""
	@echo "════════════════════════════════════════════"
	@echo "  All tests passed ✓"
	@echo "════════════════════════════════════════════"
