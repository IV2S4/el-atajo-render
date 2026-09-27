#!/bin/bash
# AUTONOMON - se ejecuta SOLO al crear el servidor (cloud-init).
# Instala Docker + n8n + Caddy (https automático con dominio gratis sslip.io).
exec > /var/log/autonomon-setup.log 2>&1
set -x

# 1) Firewall del sistema: abrir web (80/443) y dejar pasar a Docker
iptables -I INPUT 1 -p tcp --dport 80 -j ACCEPT
iptables -I INPUT 1 -p tcp --dport 443 -j ACCEPT
iptables -D FORWARD -j REJECT --reject-with icmp-host-prohibited 2>/dev/null || true
netfilter-persistent save 2>/dev/null || (apt-get update -q && DEBIAN_FRONTEND=noninteractive apt-get install -y -q iptables-persistent && netfilter-persistent save)

# 2) Memoria extra (swap) por si el servidor es pequeño
if [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# 3) Docker
curl -fsSL https://get.docker.com | sh

# 4) n8n + Caddy
IP=$(curl -s --max-time 10 https://api.ipify.org || curl -s --max-time 10 https://ifconfig.me)
HOST="${IP//./-}.sslip.io"
mkdir -p /opt/autonomon && cd /opt/autonomon
if [ ! -f .env ]; then
  echo "HOST=$HOST" > .env
  echo "N8N_ENCRYPTION_KEY=$(openssl rand -hex 24)" >> .env
fi
cat > docker-compose.yml <<'EOF'
services:
  n8n:
    image: docker.n8n.io/n8nio/n8n:latest
    restart: always
    environment:
      - N8N_HOST=${HOST}
      - N8N_PROTOCOL=https
      - N8N_PORT=5678
      - WEBHOOK_URL=https://${HOST}/
      - N8N_EDITOR_BASE_URL=https://${HOST}/
      - N8N_ENCRYPTION_KEY=${N8N_ENCRYPTION_KEY}
      - GENERIC_TIMEZONE=America/Manaus
      - TZ=America/Manaus
      - N8N_RUNNERS_ENABLED=true
      - N8N_PROXY_HOPS=1
      - EXECUTIONS_DATA_PRUNE=true
      - EXECUTIONS_DATA_MAX_AGE=168
      - N8N_DIAGNOSTICS_ENABLED=false
    volumes:
      - n8n_data:/home/node/.n8n
  caddy:
    image: caddy:2
    restart: always
    ports:
      - "80:80"
      - "443:443"
    command: caddy reverse-proxy --from ${HOST} --to n8n:5678
    volumes:
      - caddy_data:/data
volumes:
  n8n_data:
  caddy_data:
EOF
docker compose up -d
echo "LISTO https://$HOST" > /opt/autonomon/estado
