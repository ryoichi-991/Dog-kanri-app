#!/usr/bin/env bash
set -euo pipefail

DOMAIN="dog-management.benefit-navi.com"
LIMIT="25M"
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  SUDO="sudo"
fi

mapfile -t CONFIGS < <(
  grep -RIl --include='*.conf' "server_name[^;]*${DOMAIN}" /etc/nginx/sites-enabled /etc/nginx/conf.d 2>/dev/null || true
)

if [ "${#CONFIGS[@]}" -eq 0 ]; then
  echo "[NGINX] ${DOMAIN} の設定ファイルが見つかりません"
  exit 1
fi

for config in "${CONFIGS[@]}"; do
  echo "[NGINX] upload limit ${LIMIT}: ${config}"
  if grep -qE '^[[:space:]]*client_max_body_size[[:space:]]+' "${config}"; then
    ${SUDO} sed -i -E "s/^[[:space:]]*client_max_body_size[[:space:]]+[^;]+;/    client_max_body_size ${LIMIT};/" "${config}"
  else
    ${SUDO} sed -i -E "/server_name[^;]*${DOMAIN}/a\\    client_max_body_size ${LIMIT};" "${config}"
  fi
done

${SUDO} nginx -t
if command -v systemctl >/dev/null 2>&1; then
  ${SUDO} systemctl reload nginx
else
  ${SUDO} service nginx reload
fi
echo "[NGINX] ${DOMAIN} のアップロード上限を ${LIMIT} に設定しました"
