#!/bin/bash
set -euo pipefail
DOMAIN="$1"
BASE=/srv/pyaterka
RELEASE="$BASE/releases/$(date -u +%Y%m%dT%H%M%SZ)"
if ! id pyaterka >/dev/null 2>&1; then useradd --system --home-dir "$BASE" --shell /usr/sbin/nologin pyaterka; fi
install -d -m 755 "$BASE" "$BASE/releases" "$BASE/static"
install -d -m 700 -o pyaterka -g pyaterka "$BASE/state"
install -d -m 700 /var/backups/pyaterka
install -d -m 755 "$RELEASE"
tar -xzf /root/pyaterka-source.tar.gz -C "$RELEASE"
chmod -R a+rX "$RELEASE"
ln -sfn "$RELEASE" "$BASE/current"
python3 -m venv "$BASE/venv"
"$BASE/venv/bin/pip" install -r "$RELEASE/deploy/requirements-production.txt" > /root/pyaterka-pip.log 2>&1
tail -n 4 /root/pyaterka-pip.log
if [ ! -f /etc/pyaterka.env ]; then
 DOMAIN="$DOMAIN" python3 - <<'PY'
import os,secrets
fd=os.open('/etc/pyaterka.env',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
domain=os.environ['DOMAIN']
values={'DJANGO_SETTINGS_MODULE':'config.production_settings','TRAINER_PRODUCTION':'1','TRAINER_STATE_DIR':'/srv/pyaterka/state','TRAINER_STATIC_ROOT':'/srv/pyaterka/static','TRAINER_SECRET_KEY':secrets.token_urlsafe(64),'TRAINER_ALLOWED_HOSTS':domain,'TRAINER_PUBLIC_ORIGIN':'https://'+domain,'PYTHONUNBUFFERED':'1','PYTHONDONTWRITEBYTECODE':'1'}
with os.fdopen(fd,'w') as f:f.write('\n'.join(k+'='+v for k,v in values.items())+'\n')
PY
fi
chown pyaterka:pyaterka "$BASE/static"
install -m 644 "$RELEASE/deploy/pyaterka.service" /etc/systemd/system/
install -m 644 "$RELEASE/deploy/pyaterka-notifications.service" /etc/systemd/system/
install -m 644 "$RELEASE/deploy/pyaterka-notifications.timer" /etc/systemd/system/
systemctl daemon-reload
mkdir -p /var/www/letsencrypt/.well-known/acme-challenge
cat > /etc/nginx/sites-available/pyaterka <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;
    location ^~ /.well-known/acme-challenge/ { root /var/www/letsencrypt; }
    location / { return 503; }
}
EOF
ln -sfn /etc/nginx/sites-available/pyaterka /etc/nginx/sites-enabled/pyaterka
if [ -L /etc/nginx/sites-enabled/default ]; then unlink /etc/nginx/sites-enabled/default; fi
nginx -t
systemctl enable --now nginx
systemctl reload nginx
certbot certonly --webroot -w /var/www/letsencrypt --non-interactive --agree-tos --register-unsafely-without-email -d "$DOMAIN"
install -d /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx <<'HOOK'
#!/bin/sh
systemctl reload nginx
HOOK
chmod 755 /etc/letsencrypt/renewal-hooks/deploy/reload-nginx
systemctl enable --now certbot.timer
printf 'Code, environment and TLS certificate prepared.\n'
