#!/usr/bin/env bash
set -euo pipefail

DOMAIN="dog-management.benefit-navi.com"
LIMIT="25M"
OCR_TIMEOUT="600s"
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
  # 高精細な血統書OCRは数分かかる場合があるため、既定の60秒で
  # Nginxが504を返さないよう待機時間を延長する。
  for directive in proxy_connect_timeout proxy_send_timeout proxy_read_timeout send_timeout; do
    if grep -qE "^[[:space:]]*${directive}[[:space:]]+" "${config}"; then
      ${SUDO} sed -i -E "s/^[[:space:]]*${directive}[[:space:]]+[^;]+;/    ${directive} ${OCR_TIMEOUT};/" "${config}"
    else
      ${SUDO} sed -i -E "/server_name[^;]*${DOMAIN}/a\\    ${directive} ${OCR_TIMEOUT};" "${config}"
    fi
  done
done

${SUDO} nginx -t
if command -v systemctl >/dev/null 2>&1; then
  ${SUDO} systemctl reload nginx
else
  ${SUDO} service nginx reload
fi
echo "[NGINX] ${DOMAIN} のアップロード上限を ${LIMIT} に設定しました"
echo "[NGINX] OCR待機時間を ${OCR_TIMEOUT} に設定しました"
