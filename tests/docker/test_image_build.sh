#!/usr/bin/env bash
# =============================================================================
# test_image_build.sh — Docker image build verification and security checks
# =============================================================================
#
# Scope:
#   Builds the OHB Docker image using the project's own build-image.sh
#   script, then runs post-build security and hygiene checks on the
#   resulting image.
#
# What is Tested:
#   1. Build success — the image builds without errors via build-image.sh.
#   2. .git exclusion — the .git directory must NOT be present inside the
#      image (V-032: source-code leakage via container inspection).
#   3. www-data user exists — the non-root service account is present.
#   4. Non-root default — the container must not run as root (V-008).
#   5. Image size — the image must be under 2 GB to prevent bloat.
#   6. COPY over ADD — the Dockerfile must use COPY (not ADD) to avoid
#      unintended archive extraction and remote URL fetching.
#   7. .dockerignore — a .dockerignore file must exist to prevent
#      sensitive files from entering the build context.
#   8. git.version cleanup — the temporary git.version file must be
#      removed after the build completes.
#
# Prerequisites:
#   - Docker daemon running
#   - docker/build-image.sh must be functional
#   - Git repository with tags (for image naming)
#
# Exit Codes:
#   0 — All checks passed
#   1 — One or more checks failed
#
# Runner:
#   bash tests/docker/test_image_build.sh
#
# See Also:
#   tests/TEST_README.md — Tier 5 (Docker Image Tests)
#   V-008 — Container runs as root
#   V-032 — .git directory in image
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PASS=0
FAIL=0

pass() { echo "  ✓ $1"; ((PASS++)); }
fail() { echo "  ✗ $1"; ((FAIL++)); }

echo "==> Docker Image Build Tests"
echo ""

# ── Build the image using the project's own build script ─────────────────────
# This validates that the Dockerfile, .dockerignore, and build-image.sh
# are all consistent and produce a working image.
echo "--- Building image via docker/build-image.sh ---"
if bash "$ROOT/docker/build-image.sh"; then
    pass "Image builds successfully via build-image.sh"
else
    fail "Image build failed (see output above)"
    echo ""
    echo "Results: $PASS passed, $FAIL failed"
    exit 1
fi

# ── Determine image name (same logic as build-image.sh) ─────────────────────
IMAGE_BASE="komacke/open-hamclock-backend"
TAG=$(cd "$ROOT" && git describe --exact-match --tags 2>/dev/null || echo "latest")
IMAGE="${IMAGE_BASE}:${TAG}"
echo "    Testing image: $IMAGE"
echo ""

# ── Verify .git is NOT in the image (V-032) ──────────────────────────────────
# The .git directory contains full commit history, credentials, and
# potentially sensitive branch names. It must be excluded via .dockerignore.
echo "--- Checking image contents ---"
if docker run --rm "$IMAGE" test -d /opt/hamclock-backend/.git 2>/dev/null; then
    fail ".git directory is inside the image (V-032)"
else
    pass ".git directory excluded from image"
fi

# ── Verify www-data user exists ──────────────────────────────────────────────
# The www-data user is the non-root service account for lighttpd and CGI.
if docker run --rm "$IMAGE" id www-data >/dev/null 2>&1; then
    pass "www-data user exists in image"
else
    fail "www-data user missing from image"
fi

# ── Verify image is not running as root by default (V-008) ───────────────────
# Running as root inside a container provides no isolation benefit and
# enables container-escape exploits.
CONTAINER_USER="$(docker run --rm "$IMAGE" whoami 2>/dev/null || echo root)"
if [ "$CONTAINER_USER" = "root" ]; then
    fail "Container runs as root by default (V-008)"
else
    pass "Container runs as $CONTAINER_USER (non-root)"
fi

# ── Verify image size is reasonable ──────────────────────────────────────────
# Large images indicate unnecessary dependencies that expand the attack surface.
SIZE_MB="$(docker image inspect "$IMAGE" --format '{{.Size}}' | awk '{printf "%.0f", $1/1048576}')"
if [ "$SIZE_MB" -lt 2000 ]; then
    pass "Image size is ${SIZE_MB}MB (< 2GB)"
else
    fail "Image size is ${SIZE_MB}MB (> 2GB — too large)"
fi

# ── Verify Dockerfile uses COPY not ADD ──────────────────────────────────────
# ADD has implicit behaviors (archive extraction, remote URL fetch) that
# can introduce unexpected files. COPY is explicit and auditable.
if grep -q '^ADD ' "$ROOT/docker/Dockerfile" 2>/dev/null; then
    fail "Dockerfile uses ADD instead of COPY"
else
    pass "Dockerfile uses COPY (not ADD)"
fi

# ── Verify .dockerignore exists ──────────────────────────────────────────────
# Without .dockerignore, the entire repository (including .git, .env,
# node_modules) is sent as build context.
if [ -f "$ROOT/docker/Dockerfile.dockerignore" ] || [ -f "$ROOT/.dockerignore" ]; then
    pass ".dockerignore file exists"
else
    fail ".dockerignore file missing (V-032)"
fi

# ── Verify git.version was cleaned up ────────────────────────────────────────
# build-image.sh creates a temporary git.version file for embedding the
# git commit hash. It must be removed after the build completes.
if [ -f "$ROOT/git.version" ]; then
    fail "git.version file left behind after build"
else
    pass "git.version cleaned up after build"
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
