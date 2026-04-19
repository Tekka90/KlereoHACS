#!/usr/bin/env bash
# setup_test_env.sh
# Creates the .venv, installs test dependencies, and installs the HA stub
# from tests/ha_stub/ into the venv's site-packages.
#
# The stub is test-only infrastructure — it never ships with the integration.
# The real homeassistant package (available inside HA) takes precedence at runtime.
#
# Run once from the project root: bash setup_test_env.sh

set -e
cd "$(dirname "$0")"

echo ">>> Creating virtual environment..."
# Run venv creation from a temp directory to prevent the project's select.py / number.py
# from shadowing Python's own stdlib modules (which are imported during venv bootstrap).
VENV_ABS="$(pwd)/.venv"
(cd /tmp && python3 -m venv "$VENV_ABS")

echo ">>> Installing test dependencies..."
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements-test.txt

echo ">>> Installing Home Assistant stub into venv site-packages..."
SITE_PACKAGES=$(.venv/bin/python -c "import site; print(site.getsitepackages()[0])")
echo "    site-packages: $SITE_PACKAGES"

# Copy the stub homeassistant package into site-packages
cp -r tests/ha_stub/homeassistant "$SITE_PACKAGES/"

echo ""
echo "✅  Setup complete."
echo ""
echo "Run unit tests:    .venv/bin/pytest tests/unit/ -v"
echo "Run all tests:     .venv/bin/pytest -v"
echo "Run live tests:    .venv/bin/pytest tests/live/ -v  (requires .env with credentials)"
