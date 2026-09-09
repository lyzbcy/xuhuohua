#!/bin/sh
set -eu

CRON_SCHEDULE="${CRON_SCHEDULE:-30 0 * * *}"
RUN_ON_START="${RUN_ON_START:-false}"

mkdir -p /app/artifacts /data

if [ "$RUN_ON_START" = "true" ]; then
  echo "[docker] running task once on container start"
  cd /app
  python run.py || true
fi

cat > /etc/cron.d/douyin-auto-fire <<EOF
SHELL=/bin/sh
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
${CRON_SCHEDULE} root cd /app && /usr/local/bin/python run.py >> /proc/1/fd/1 2>> /proc/1/fd/2
EOF

chmod 0644 /etc/cron.d/douyin-auto-fire

printf '[docker] cron schedule: %s\n' "$CRON_SCHEDULE"
printf '[docker] timezone: %s\n' "${TZ:-Asia/Shanghai}"

exec cron -f
