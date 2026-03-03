# Open HamClock Backend — Test Suite Reference

> **Canonical reference for the OHB testing architecture, execution workflows, and
> contribution guidelines.**

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Test Pyramid](#test-pyramid)
3. [Prerequisites](#prerequisites)
4. [Quick Start](#quick-start)
5. [Tier Reference](#tier-reference)
   - [Tier 1 — Static Analysis (Lint)](#tier-1--static-analysis-lint)
   - [Tier 2 — Bash Unit Tests (Bats)](#tier-2--bash-unit-tests-bats)
   - [Tier 3 — Python Unit Tests (pytest)](#tier-3--python-unit-tests-pytest)
   - [Tier 4 — Perl Unit Tests (prove)](#tier-4--perl-unit-tests-prove)
   - [Tier 5 — Docker Image Tests](#tier-5--docker-image-tests)
   - [Tier 6 — Integration Tests](#tier-6--integration-tests)
6. [Environment Variables](#environment-variables)
7. [Failure Handling](#failure-handling)
8. [Directory Layout](#directory-layout)
9. [Writing New Tests](#writing-new-tests)
10. [CI/CD Integration](#cicd-integration)
11. [Future Development Areas](#future-development-areas)

---

## Architecture Overview

The test suite is organized as a **six-tier pyramid** executed sequentially by a
central `Makefile`. Each tier is independent and can be run in isolation. Tiers are
ordered from fastest/cheapest (static analysis) to slowest/most expensive
(integration tests requiring a live Docker container).

```
┌─────────────────────────────────────────────────────────┐
│                    test-all (Makefile)                   │
│  Orchestrates all tiers sequentially via Make targets    │
├────────┬────────┬────────┬────────┬─────────┬───────────┤
│ Tier 1 │ Tier 2 │ Tier 3 │ Tier 4 │ Tier 5  │  Tier 6   │
│  Lint  │  Bats  │ pytest │ prove  │ Docker  │Integration│
│        │        │        │        │  Image  │   (HTTP)  │
├────────┼────────┼────────┼────────┼─────────┼───────────┤
│Shell-  │ 3 test │ 3 test │ 3 test │ 3 shell │ 2 pytest  │
│Check,  │ files  │modules │modules │ scripts │  modules  │
│Ruff,   │        │+ conf  │        │         │  + conf   │
│Hadolint│        │        │        │         │           │
└────────┴────────┴────────┴────────┴─────────┴───────────┘
  ~2s       ~3s      ~5s      ~2s     ~60s+      ~90s+
```

### Data Flow

```
Source Code (scripts/, docker/, aws/, ham/)
       │
       ├──▶ Tier 1: Static Analysis ──▶ Lint violations
       ├──▶ Tier 2: Bats ──▶ Shell script correctness
       ├──▶ Tier 3: pytest ──▶ Python module correctness
       ├──▶ Tier 4: prove ──▶ Perl CGI validation logic
       ├──▶ Tier 5: Docker ──▶ Image security properties
       └──▶ Tier 6: Integration ──▶ Live HTTP endpoint security
```

---

## Test Pyramid

| Tier | Target             | Framework     | Scope                          | Files | Est. Time |
|------|--------------------|---------------|--------------------------------|-------|-----------|
| 1    | `lint`             | ShellCheck, Ruff, Hadolint | Static analysis      | —     | ~2 s      |
| 2    | `test-bash`        | Bats          | Shell script unit tests        | 3     | ~3 s      |
| 3    | `test-python`      | pytest        | Python module unit tests       | 3+1   | ~5 s      |
| 4    | `test-perl`        | prove (TAP)   | Perl CGI input validation      | 3     | ~2 s      |
| 5    | `test-docker`      | Shell/Docker  | Image build & security checks  | 3     | ~60 s     |
| 6    | `test-integration` | pytest + Docker Compose | Live HTTP endpoint tests | 2+1 | ~90 s |

---

## Prerequisites

### Required Tools

| Tool         | Purpose                    | Install (macOS)              | Install (Linux)              |
|--------------|----------------------------|------------------------------|------------------------------|
| `shellcheck` | Bash/sh static analysis    | `brew install shellcheck`    | `apt install shellcheck`     |
| `bats`       | Bash Automated Test System | `brew install bats-core`     | `apt install bats`           |
| `hadolint`   | Dockerfile linter          | `brew install hadolint`      | See [hadolint releases][hl]  |
| `python3`    | Python 3.10+               | `brew install python3`       | `apt install python3`        |
| `perl`       | Perl 5.x                   | Pre-installed                | Pre-installed                |
| `docker`     | Container engine           | Docker Desktop               | `apt install docker.io`      |
| `prove`      | Perl TAP harness           | Pre-installed w/ Perl        | Pre-installed w/ Perl        |

[hl]: https://github.com/hadolint/hadolint/releases

### Python Packages

Installed automatically by `make deps`:

```
ruff pytest requests feedparser dvoacap
```

### One-Time Setup

```bash
make -C tests deps
```

This installs Python packages and the optional `dvoacap` library from source
(required for `test_voacap.py`).

---

## Quick Start

```bash
# Run everything (failures are non-fatal by default):
make -C tests test-all

# Run a single tier:
make -C tests lint
make -C tests test-bash
make -C tests test-python
make -C tests test-perl
make -C tests test-docker
make -C tests test-integration

# Strict mode — halt on first failure:
make -C tests FAIL_FAST=true test-all
```

---

## Tier Reference

### Tier 1 — Static Analysis (Lint)

**Target:** `make -C tests lint`

Three sub-targets run in sequence:

| Sub-target     | Tool        | Scope                                            | Suppressions              |
|----------------|-------------|--------------------------------------------------|---------------------------|
| `lint-shell`   | ShellCheck  | `scripts/*.sh`, `docker/*.sh`, `aws/*.sh`        | SC2034, SC2140            |
| `lint-python`  | Ruff        | `scripts/*.py` — rules E, F, W                   | E501 (line length)        |
| `lint-docker`  | Hadolint    | `docker/Dockerfile`                               | DL3008, DL3013            |

**Why these suppressions?**
- **SC2034**: Unused variables that are intentionally exported for child processes.
- **SC2140**: Quoting style inside arrays (Bats compatibility).
- **E501**: Long lines in data-processing scripts are acceptable.
- **DL3008/DL3013**: Version pinning in base images is managed upstream.

---

### Tier 2 — Bash Unit Tests (Bats)

**Target:** `make -C tests test-bash`
**Framework:** [Bats-core](https://github.com/bats-core/bats-core) (Bash Automated Testing System)
**Directory:** `tests/bats/`

| File                     | Tests | Subject                                           |
|--------------------------|-------|---------------------------------------------------|
| `test_crontab.bats`      | 4     | Crontab security: no `/tmp` files, correct PATH   |
| `test_lib_sizes.bats`    | 4     | Config parser safety, injection defense (V-013)   |
| `test_shell_safety.bats` | 6     | Strict mode, no backticks, curl `-f` enforcement  |

**Conventions:**
- `ROOT` is always resolved via `$BATS_TEST_DIRNAME/../..`.
- `setup()` / `teardown()` manage temp directories per test.
- Tests use `grep`/`awk`-based analysis on source files, not runtime execution of
  privileged scripts.

---

### Tier 3 — Python Unit Tests (pytest)

**Target:** `make -C tests test-python`
**Framework:** [pytest](https://docs.pytest.org/)
**Directory:** `tests/python/`

| File                   | Classes | Subject                                         |
|------------------------|---------|--------------------------------------------------|
| `conftest.py`          | —       | Shared fixtures: `tmp_dir`, `sample_rss_xml`, etc. |
| `test_data_scripts.py` | 5       | BMP headers, RGB565 conversion, script existence |
| `test_rss_fetch.py`    | 2       | Atomic cache writes, encoding conversion         |
| `test_voacap.py`       | 4       | Argument validation, band correction math, mode labels |

**Key Fixture:**
`conftest.py` adds `scripts/` to `sys.path`, enabling direct import of project
modules under test.

**Conventions:**
- Each test class maps to one production module.
- `setup_method()` / `teardown_method()` manage isolated temp directories.
- `subprocess.run()` is used for CLI argument validation tests (no shell=True).

---

### Tier 4 — Perl Unit Tests (prove)

**Target:** `make -C tests test-perl`
**Framework:** [Test::More](https://perldoc.perl.org/Test::More) (TAP Protocol)
**Directory:** `tests/perl/`

| File                       | Assertions | Subject                                       |
|----------------------------|------------|------------------------------------------------|
| `cgi_input_validation.t`   | ~30        | Maidenhead grid, callsign, coordinate, maxage  |
| `fetchBandConditions.t`    | ~12        | Parameter validation for band conditions CGI   |
| `security_regression.t`    | ~30        | Regression tests for V-001 through V-054       |

**Design Pattern:**
- Validation functions are **extracted** from production CGI scripts and tested in
  isolation. This avoids starting a web server or running CGI in test mode.
- Attack payloads (SQL injection, path traversal, command injection, XSS) are
  exercised against the validation functions directly.

**Vulnerability Coverage Map:**

| Vuln ID | Description                  | Test File                |
|---------|------------------------------|--------------------------|
| V-001   | Path traversal in tail.pl    | `security_regression.t`  |
| V-002   | Path traversal variants      | `security_regression.t`  |
| V-003   | Command injection (status)   | `security_regression.t`  |
| V-004   | Command injection (metrics)  | `security_regression.t`  |
| V-013   | Config injection             | `test_lib_sizes.bats`    |
| V-029   | XSS via unsanitized output   | `security_regression.t`  |
| V-051   | SQL injection in fetchWSPR   | `security_regression.t`  |
| V-052   | SSRF via coordinate inject   | `security_regression.t`  |
| V-054   | HTTP response splitting      | `security_regression.t`  |

---

### Tier 5 — Docker Image Tests

**Target:** `make -C tests test-docker`
**Framework:** Shell scripts with pass/fail counters
**Directory:** `tests/docker/`

| File                           | Checks | Subject                                    |
|--------------------------------|--------|--------------------------------------------|
| `test_image_build.sh`          | 7      | Build, `.git` exclusion, user, size, COPY  |
| `test_container_security.sh`   | 6      | Non-root, shadow perms, no curl, SUID      |
| `test_container_runtime.sh`    | 5      | lighttpd, CGI, dashboard, cron             |

**Prerequisites:**
- Docker daemon must be running.
- The `build-image.sh` script must complete successfully before security/runtime
  checks can execute.

**Environment Variables:**
- `OHB_TEST_IMAGE` — Override the image name (default: `ohb:test`).

---

### Tier 6 — Integration Tests

**Target:** `make -C tests test-integration`
**Framework:** pytest + requests + Docker Compose
**Directory:** `tests/integration/`

| File                          | Classes | Tests | Subject                          |
|-------------------------------|---------|-------|----------------------------------|
| `conftest.py`                 | —       | —     | `base_url` fixture               |
| `test_endpoints.py`           | 30      | ~45   | Endpoint security & correctness  |
| `test_security_headers.py`    | 3       | ~12   | HTTP security headers & CORS     |

**Lifecycle:**

```
make test-integration
  ├── 1. Generate docker-compose.test.yml (port 8085)
  ├── 2. docker compose up -d --build --wait
  ├── 3. OHB_TEST_HOST=http://localhost:8085 pytest tests/integration/
  ├── 4. docker compose down --rmi local -v
  └── 5. Clean up docker-compose.test.yml
```

**Test Categories in `test_endpoints.py`:**

| Category            | Classes                                                                   |
|---------------------|---------------------------------------------------------------------------|
| Endpoint Smoke      | `TestVersionEndpoint`, `TestDashboardEndpoints`, `TestBandConditionsEndpoint` |
| Injection Defense   | `TestAdvancedInjection`, `TestNullByteInjection`, `TestDoubleEncoding`, `TestSSIInjection` |
| Path Traversal      | `TestTailEndpoint`, `TestFetchWSPREndpoint`                               |
| HTTP Method Safety  | `TestHTTPMethods`, `TestHTTPOptionsDisclosure`, `TestMethodOverrideHeader` |
| Header Security     | `TestHostHeaderInjection`, `TestMultipleHostHeaders`, `TestContentTypeEnforcement`, `TestETagInfoLeak` |
| Error Handling      | `TestErrorHandling`, `TestErrorPageInfoLeak`, `TestCGIStderrLeakage`      |
| Protocol Edge Cases | `TestHTTPVersionEnforcement`, `TestWebSocketUpgrade`, `TestAbsoluteURIRequest`, `TestSemicolonPathDelimiter` |
| Data Safety         | `TestDirectoryListing`, `TestStaticFileAccess`, `TestParameterPollution`  |
| Redirect Safety     | `TestOpenRedirectPrevention`                                              |
| Resilience          | `TestLargePostBody`, `TestHEADConsistency`, `TestUnicodeNormalization`    |

**All integration tests are skipped** when `OHB_TEST_HOST` is not set. This
allows `pytest tests/integration/` to be run safely outside of Docker contexts.

---

## Environment Variables

| Variable          | Default                  | Used By             | Description                          |
|-------------------|--------------------------|---------------------|--------------------------------------|
| `OHB_TEST_HOST`   | `http://localhost:8080`  | Integration tests   | Base URL for the running container   |
| `OHB_TEST_IMAGE`  | `ohb:test`               | Docker tests        | Docker image name to test            |
| `FAIL_FAST`       | `false`                  | Makefile             | Set `true` to halt on first failure  |
| `OHB_ROOT`        | Auto-detected            | Perl tests          | Root of the OHB repository           |

---

## Failure Handling

By default (`FAIL_FAST=false`), all tier failures are captured but **do not halt**
the overall `test-all` run. This allows a complete picture of the test landscape
in a single pass. Each failing tier prints `(Ignored failures)` and continues.

To enforce strict failure behavior (ideal for CI gate checks):

```bash
make -C tests FAIL_FAST=true test-all
```

**Implementation:** The `_FAIL_GUARD` Make variable appends `|| { echo "(Ignored
failures)"; exit 0; }` to each command when `FAIL_FAST=false`.

---

## Directory Layout

```
tests/
├── Makefile                          # Orchestrator — all targets defined here
├── TEST_README.md                    # ← This document
├── aws/
│   └── test_install_scripts.bats     # AWS install script static analysis
├── bats/
│   ├── test_crontab.bats            # Crontab security properties
│   ├── test_lib_sizes.bats          # Config parser injection defense
│   └── test_shell_safety.bats       # Shell best-practice enforcement
├── docker/
│   ├── test_image_build.sh          # Image build + security checks
│   ├── test_container_security.sh   # Container security hardening
│   └── test_container_runtime.sh    # Container runtime services
├── integration/
│   ├── conftest.py                  # Shared fixtures (base_url)
│   ├── test_endpoints.py            # HTTP endpoint tests (~45 tests)
│   └── test_security_headers.py     # Security header validation
└── python/
    ├── conftest.py                  # Shared fixtures (tmp_dir, sample data)
    ├── test_data_scripts.py         # BMP/RGB565 data processing
    ├── test_rss_fetch.py            # RSS cache writing & encoding
    └── test_voacap.py               # VOACAP band condition math
```

---

## Writing New Tests

### Python (pytest)

```python
"""Tests for <module_name> — <one-line purpose>.

Verifies:
    - Behavior A under condition X.
    - Rejection of invalid input Y.

References:
    - Vulnerability ID: V-NNN (if applicable)
    - Production module: scripts/<module_name>.py
"""

class TestFeatureName:
    """Validates <specific behavior> in <module>."""

    def test_valid_case_returns_expected(self):
        """Verify <function> returns <expected> when given <input>."""
        result = function_under_test(valid_input)
        assert result == expected_output

    def test_injection_rejected(self):
        """Verify <function> rejects <attack vector> (V-NNN)."""
        result = function_under_test(malicious_input)
        assert result is None or "error" in result
```

### Bats (Shell)

```bash
#!/usr/bin/env bats
# test_<feature>.bats — <one-line purpose>
#
# Scope:   <what is tested>
# Depends: <tools/files required>
# Refs:    V-NNN (if applicable)

ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"

@test "<descriptive test name>" {
    # Arrange
    local input="test_value"

    # Act
    run some_command "$input"

    # Assert
    [ "$status" -eq 0 ]
    [[ "$output" =~ expected_pattern ]]
}
```

### Perl (Test::More)

```perl
#!/usr/bin/env perl
# test_<feature>.t — <one-line purpose>
#
# Scope:   <what is tested>
# Runner:  prove -v tests/perl/test_<feature>.t
# Refs:    V-NNN (if applicable)
use strict;
use warnings;
use Test::More;

# ── Section Name ──────────────────────────────────────────────────────────────

sub function_under_test {
    my ($input) = @_;
    # ...validation logic extracted from production code...
}

ok(function_under_test("valid"),    "Valid input accepted");
ok(!function_under_test("invalid"), "Invalid input rejected");

done_testing();
```

---

## CI/CD Integration

### GitHub Actions (Recommended)

```yaml
name: Test Suite
on: [push, pull_request]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: sudo apt-get install -y shellcheck
      - run: pip install ruff
      - run: make -C tests lint

  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: sudo apt-get install -y bats
      - run: pip install pytest requests feedparser
      - run: make -C tests test-bash test-python test-perl

  docker-tests:
    runs-on: ubuntu-latest
    needs: [lint, unit-tests]
    steps:
      - uses: actions/checkout@v4
      - run: make -C tests FAIL_FAST=true test-docker test-integration
```

### Key Principles

1. **Gate on `FAIL_FAST=true`** in CI to catch regressions.
2. **Parallelize tiers 1–4** since they have no shared state.
3. **Tiers 5–6 require Docker** and should depend on passing unit tests.
4. **Integration tests produce no side effects** — the test container is torn down
   automatically via `docker compose down --rmi local -v`.

---

## Future Development Areas

### High Priority

- **Code Coverage Reporting** — Add `pytest-cov` integration and coverage gates
  for Python modules. Target: ≥ 80% line coverage on `scripts/*.py`.
- **Performance Benchmarks** — Add response-time assertions to integration tests
  (e.g., `assert response.elapsed.total_seconds() < 5.0`).
- **HTTPS/TLS Tests** — Test certificate validation, TLS version enforcement,
  and HSTS preload behavior end-to-end.

### Medium Priority

- **Mutation Testing** — Use `mutmut` (Python) or `Devel::Mutant` (Perl) to
  validate that tests detect injected faults.
- **Fuzz Testing** — Apply `hypothesis` (Python) to generate randomized inputs
  for CGI parameter validators.
- **Load Testing** — Add a `test-load` Makefile target using `wrk` or `ab` to
  verify the container handles concurrent connections gracefully.

### Low Priority

- **Contract Testing** — Validate that CGI endpoints conform to documented
  response schemas (e.g., CSV column counts for `fetchBandConditions.pl`).
- **Dependency Scanning** — Integrate Trivy or Grype for container image CVE
  scanning as a Tier 5.5.
- **Visual Regression** — Snapshot the dashboard HTML and diff against known-good
  baselines to detect unintended UI changes.

---

## License

This test suite is part of the [Open HamClock Backend](https://github.com/BrianWilkinsFL/open-hamclock-backend)
project and is distributed under the same license as the parent project.
