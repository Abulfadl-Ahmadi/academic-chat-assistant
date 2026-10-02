#!/usr/bin/env bash
# ==============================================================================
# Automated VPS Provisioner for Academic LLM Chat Assistant
# Supported OS: Ubuntu 22.04 / 24.04 LTS, Debian 12
# ==============================================================================
set -euo pipefail

echo "==> [1/5] Updating system packages non-interactively..."
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -qq
sudo apt-get install -y -qq curl wget git ufw htop ca-certificates gnupg lsb-release

echo "==> [2/5] Hardening UFW firewall..."
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp comment "SSH"
sudo ufw allow 80/tcp comment "HTTP (Caddy Let's Encrypt)"
sudo ufw allow 443/tcp comment "HTTPS (WebUI Traffic)"
echo "y" | sudo ufw enable
sudo ufw status verbose

echo "==> [3/5] Installing Docker Engine & Docker Compose Plugin..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
    sudo sh /tmp/get-docker.sh
    sudo usermod -aG docker "$USER"
    rm -f /tmp/get-docker.sh
fi

echo "==> [4/5] Preparing deployment directory at /opt/chat-assistant..."
sudo mkdir -p /opt/chat-assistant/backups
sudo chown -R "$USER:$USER" /opt/chat-assistant

echo "==> [5/5] Checking Docker daemon status..."
sudo systemctl enable --now docker
docker --version
docker compose version

echo "=========================================================================="
echo "✓ VPS Provisioning completed successfully!"
echo "Next step: Copy project files to /opt/chat-assistant and run 'docker compose up -d'"
echo "=========================================================================="
