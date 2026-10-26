#!/usr/bin/env bash
#
# Provision with:
#   sudo ./ops/setup-server.sh api.example.com sre-operations@example.com deploy
#
# Arguments: <fully-qualified-api-domain> <certificate-email> <existing-ssh-deploy-user>

set -Eeuo pipefail
IFS=$'\n\t'

LOG_FILE="/var/log/industrial-sre-agent-setup.log"
readonly LOG_FILE

if [[ "${EUID}" -ne 0 ]]; then
  printf 'Run this script as root through sudo.\n' >&2
  exit 1
fi

if [[ "$#" -ne 3 ]]; then
  printf 'Usage: %s <fully-qualified-api-domain> <certificate-email> <existing-ssh-deploy-user>\n' "$0" >&2
  exit 2
fi

DOMAIN="$1"
CERTBOT_EMAIL="$2"
DEPLOY_USER="$3"

if [[ ! "$DOMAIN" =~ ^([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}$ ]]; then
  printf 'The API domain must be a valid fully qualified domain name.\n' >&2
  exit 2
fi

if [[ ! "$CERTBOT_EMAIL" =~ ^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$ ]]; then
  printf 'The certificate email address is invalid.\n' >&2
  exit 2
fi

if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  printf 'The deployment user %s does not exist.\n' "$DEPLOY_USER" >&2
  exit 2
fi

exec > >(tee -a "$LOG_FILE") 2>&1

timestamp() {
  date --iso-8601=seconds
}

log() {
  printf '[%s] %s\n' "$(timestamp)" "$*"
}

on_error() {
  local exit_code="$?"
  local line_number="$1"
  log "ERROR: setup failed at line ${line_number} with exit status ${exit_code}."
  exit "$exit_code"
}

trap 'on_error $LINENO' ERR

export DEBIAN_FRONTEND=noninteractive

log "Validating Ubuntu release."
. /etc/os-release
if [[ "$ID" != "ubuntu" ]] || [[ "$VERSION_ID" != "22.04" && "$VERSION_ID" != "24.04" ]]; then
  log "ERROR: Ubuntu 22.04 LTS or 24.04 LTS is required; found ${PRETTY_NAME}."
  exit 1
fi

log "Updating system packages and installing base dependencies."
apt-get update
apt-get -y dist-upgrade
apt-get install -y ca-certificates curl git ufw software-properties-common nginx certbot python3-certbot-nginx

log "Removing conflicting Docker packages while preserving existing Docker data directories."
for package in docker.io docker-compose docker-compose-v2 docker-doc docker-buildx podman-docker containerd runc; do
  if dpkg-query --show --showformat='${db:Status-Status}' "$package" 2>/dev/null | grep -qx installed; then
    apt-get remove -y "$package"
  fi
done

log "Installing Docker Engine and Compose v2 from Docker's official APT repository."
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
install -d -m 0755 /etc/docker
cat > /etc/docker/daemon.json <<'EOF'
{"dns":["1.1.1.1","8.8.8.8"]}
EOF
systemctl enable --now docker
systemctl restart docker
systemctl is-active --quiet docker
docker compose version

log "Creating the deployment release root and granting Docker access to the deployment user."
install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" -m 0750 /opt/industrial-sre-agent
usermod -aG docker "$DEPLOY_USER"

log "Configuring UFW with deny-by-default inbound policy and explicit web allowances."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment "SSH administration"
ufw allow 80/tcp comment "HTTP ACME validation and redirect"
ufw allow 443/tcp comment "HTTPS API and WebSocket ingress"
ufw --force enable
ufw status verbose

PUBLIC_INTERFACE="$(ip route show default | awk '/default/ {print $5; exit}')"
if [[ -z "$PUBLIC_INTERFACE" ]]; then
  log "ERROR: unable to determine the public network interface."
  exit 1
fi

log "Installing persistent Docker ingress protection for public interface ${PUBLIC_INTERFACE}."
cat > /usr/local/sbin/industrial-sre-docker-firewall <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail
for binary in iptables ip6tables; do
  command -v "\$binary" >/dev/null 2>&1 || continue
  "\$binary" -N DOCKER-USER 2>/dev/null || true
  "\$binary" -C DOCKER-USER -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || "\$binary" -I DOCKER-USER 1 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
  "\$binary" -C DOCKER-USER -i "${PUBLIC_INTERFACE}" -j DROP 2>/dev/null || "\$binary" -I DOCKER-USER 2 -i "${PUBLIC_INTERFACE}" -j DROP
done
EOF
chmod 0750 /usr/local/sbin/industrial-sre-docker-firewall

cat > /etc/systemd/system/industrial-sre-docker-firewall.service <<EOF
[Unit]
Description=Block public ingress to Docker-published ports
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/industrial-sre-docker-firewall
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now industrial-sre-docker-firewall.service

log "Writing hardened Nginx reverse proxy configuration for ${DOMAIN}."
install -d -m 0755 /var/www/certbot
cat > /etc/nginx/conf.d/industrial-sre-security.conf <<'EOF'
server_tokens off;
EOF

cat > "/etc/nginx/sites-available/${DOMAIN}" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};
    client_max_body_size 1m;

    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        default_type "text/plain";
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
        proxy_buffering off;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 10s;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
    }
}
EOF

rm -f /etc/nginx/sites-enabled/default
ln -sfn "/etc/nginx/sites-available/${DOMAIN}" "/etc/nginx/sites-enabled/${DOMAIN}"
nginx -t
systemctl enable --now nginx
systemctl reload nginx

log "Checking DNS resolution before certificate provisioning."
if ! getent ahosts "$DOMAIN" >/dev/null; then
  log "ERROR: ${DOMAIN} does not resolve. Create its public DNS A or AAAA record before running this script."
  exit 1
fi

log "Provisioning the Let's Encrypt certificate and enabling HTTPS redirection."
certbot --nginx \
  --non-interactive \
  --agree-tos \
  --email "$CERTBOT_EMAIL" \
  --redirect \
  --keep-until-expiring \
  -d "$DOMAIN"
systemctl enable --now certbot.timer
certbot renew --dry-run

log "Verifying public proxy configuration and local API reachability."
nginx -t
curl --fail --silent --show-error --max-time 10 "https://${DOMAIN}/health" >/dev/null || true
docker info >/dev/null
systemctl is-active --quiet nginx
systemctl is-active --quiet docker
systemctl is-active --quiet industrial-sre-docker-firewall

log "Server initialization completed successfully."
log "Deploy releases to /opt/industrial-sre-agent and set PROD_DEPLOY_PATH to that exact value."
log "The deployment user must start a new SSH session before Docker group membership is active."
