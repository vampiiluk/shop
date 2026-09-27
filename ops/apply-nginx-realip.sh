#!/usr/bin/env bash
# Make the shop's client-IP truth setup complete, idempotently.
#
# Two pieces are needed for "the site believes the socket, not a header the
# caller typed", and this script owns both:
#
#   1. The Cloudflare trust list at /etc/nginx/conf.d/50-cloudflare-realip.conf
#      (installed from ops/cloudflare-realip.conf). bench never writes there,
#      so once present it stays — but a **new machine** starts without it,
#      which is why this script ships it rather than assuming it.
#   2. The X-Forwarded-For line inside each bench's *generated*
#      config/nginx/include.conf starts trusting only $remote_addr instead of
#      appending the caller's own header text. `bench setup nginx` regenerates
#      that file, so re-run this script after a regenerate. No-op if nothing
#      is missing.
#
# Usage: sudo bash ops/apply-nginx-realip.sh
# Needs root only for writing /etc/nginx/conf.d and reloading nginx; on a
# filesystem where that file already exists and config test passes, the whole
# run is a confirmation, not a change.
set -euo pipefail

REPO_CONF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/cloudflare-realip.conf"
LIVE_CONF="/etc/nginx/conf.d/50-cloudflare-realip.conf"

install_trust_list() {
	if [[ -f "$LIVE_CONF" ]]; then
		echo "ok:      $LIVE_CONF"
		return
	fi
	[[ $EUID -eq 0 ]] || { echo "NEEDS SUDO: installing $LIVE_CONF" >&2; exit 1; }
	cp "$REPO_CONF" "$LIVE_CONF"
	echo "installed: $LIVE_CONF"
}

apply_one() {
	local file="$1"
	[[ -f "$file" ]] || return 0
	if grep -qE 'proxy_set_header[[:space:]]+X-Forwarded-For[[:space:]]+\$proxy_add_x_forwarded_for' "$file"; then
		sed -i.nginxbak -E 's#(proxy_set_header[[:space:]]+X-Forwarded-For[[:space:]]+)\$proxy_add_x_forwarded_for#\1$remote_addr#g' "$file"
		echo "patched: $file"
	else
		echo "ok:      $file"
	fi
}

main() {
	install_trust_list
	shopt -s nullglob
	local found=0 f
	for f in /home/frappe/pilot/benches/*/config/nginx/include.conf; do
		found=1; apply_one "$f"
	done
	(( found )) || echo "no bench include.conf found (nothing to patch)"
	if [[ $EUID -eq 0 ]]; then
		if nginx -t; then
			systemctl reload nginx 2>/dev/null || nginx -s reload || kill -HUP "$(cat /run/nginx.pid)" 2>/dev/null || true
			echo "nginx reloaded"
		fi
	else
		echo "not root: skipped nginx -t/reload (run with sudo to figure it live)"
	fi
}
main "$@"
