#!/usr/bin/env bash
# Deploy AI News Aggregator on the server
# Usage: bash deploy/install.sh

set -euo pipefail

PROJECT_DIR="/AIGC/XD-AIGC-ai-news"
CONDA_ENV="/AIGC_Group/miniconda3/envs/xd-aigc-ainews"
SYSTEMD_DIR="/etc/systemd/system"

echo "=== AI News Aggregator Deploy ==="

# 1. Install Python dependencies
echo "[1/4] Installing Python dependencies..."
"${CONDA_ENV}/bin/pip" install -r "${PROJECT_DIR}/requirements.txt" -q

# 2. Create data directories
echo "[2/4] Creating data directories..."
mkdir -p "${PROJECT_DIR}/data"
mkdir -p "${PROJECT_DIR}/reports/markdown"

# 3. Install systemd units
echo "[3/4] Installing systemd service and timer..."
sudo cp "${PROJECT_DIR}/deploy/ai-news.service" "${SYSTEMD_DIR}/"
sudo cp "${PROJECT_DIR}/deploy/ai-news.timer" "${SYSTEMD_DIR}/"
sudo systemctl daemon-reload
sudo systemctl enable ai-news.timer
sudo systemctl start ai-news.timer

# 4. Verify
echo "[4/4] Verifying..."
systemctl status ai-news.timer --no-pager || true
echo ""
echo "Timer schedule:"
systemctl list-timers ai-news.timer --no-pager || true

echo ""
echo "=== Deploy complete ==="
echo "To run manually:  cd ${PROJECT_DIR} && ${CONDA_ENV}/bin/python main.py --days 1"
echo "To start web UI:  cd ${PROJECT_DIR} && ${CONDA_ENV}/bin/python main.py --serve"
echo "To check logs:    journalctl -u ai-news.service -f"
