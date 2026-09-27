#!/usr/bin/env bash
# Re-apply the client-IP truth patch to a bench-generated nginx include.conf.
#
# Why: `bench setup nginx` regenerates <bench>/config/nginx/include.conf and
# undoes the X-Forwarded-For hardening from the original fix. This script is
# idempotent — run it any time, it only touches what is missing:
#
#   - per-location lines change from $proxy_add_x_forwarded_for (appends the
#     caller's own header text, so its first hop is supposed mutable attacker
#     text) to $remote_addr (which nginx owns; with the conf.d/50-cloudflare
#     -realip.conf trust list, already rewritten to the real client when the
#     caller came through Cloudflare).
#   - if the trust-list drop-in has vanished from /etc/nginx/conf.d, it says
#     so loudly instead of redoing anything partially.
#
# The companion shop-app change (`X-Real-IP` read in checkout.py) does not
# depend on this file; this script exists to keep Frappe's XFF-based keys
# (rate limiting, login lockout, request_ip) honest after a regen.
set -euo pipefail

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
	if [[ ! -f /etc/nginx/conf.d/50-cloudflare-realip.conf ]]; then
		echo "MISSING: /etc/nginx/conf.d/50-cloudflare-realip.conf (the Cloudflare trust list) — restore it first" >&2
		exit 1
	fi
	shopt -s nullglob
	found=0
	for f in /home/frappe/pilot/benches/*/config/nginx/include.conf; do
		found=1; apply_one "$f"
	done
	(( found )) || { echo "no bench include.conf found"; exit 0; }
	if nginx -t; then
		systemctl reload nginx 2>/dev/null || nginx -s reload
		echo "nginx reloaded"
	fi
}
main "$@"
