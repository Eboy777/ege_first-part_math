#!/bin/bash
set -euo pipefail
DOMAIN="$1"
BASE=/srv/pyaterka
if [ -f "$BASE/state/trainer.sqlite3" ]; then
    printf 'State already exists; refusing to overwrite.\n' >&2
    exit 1
fi
tar -xzf /root/pyaterka-state.tar.gz -C "$BASE/state"
chown -R pyaterka:pyaterka "$BASE/state"
find "$BASE/state" -type d -exec chmod 700 {} +
find "$BASE/state" -type f -exec chmod 600 {} +
set -a
source /etc/pyaterka.env
set +a
cd "$BASE/current"
runuser -u pyaterka -- "$BASE/venv/bin/python" trainer/stage2.py migrate --noinput
runuser -u pyaterka -- "$BASE/venv/bin/python" trainer/stage2.py collectstatic --noinput
find "$BASE/static" -type d -exec chmod 755 {} +
find "$BASE/static" -type f -exec chmod 644 {} +
runuser -u pyaterka -- "$BASE/venv/bin/python" trainer/stage2.py check --deploy
cat > /etc/nginx/sites-available/pyaterka <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;
    location ^~ /.well-known/acme-challenge/ { root /var/www/letsencrypt; }
    location / { return 301 https://\$host\$request_uri; }
}
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name $DOMAIN;
    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    client_max_body_size 6m;
    location /static/ {
        alias /srv/pyaterka/static/;
        add_header X-Content-Type-Options nosniff always;
        expires 1h;
    }
    location / {
        proxy_pass http://127.0.0.1:8091;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$remote_addr;
        proxy_read_timeout 95s;
        proxy_send_timeout 95s;
        proxy_redirect off;
    }
}
EOF
nginx -t
systemctl enable --now pyaterka.service
systemctl enable --now pyaterka-notifications.timer
systemctl reload nginx
systemctl start pyaterka-notifications.service
systemctl is-active pyaterka.service pyaterka-notifications.timer nginx
printf 'Application and notification timer started.\n'
