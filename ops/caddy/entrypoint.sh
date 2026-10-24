#!/bin/sh
# Один Caddy на всех. Пустой DOMAIN — HTTP на :80 (снаружи это HTTP_PORT).
# DOMAIN задан — Let's Encrypt и редирект www на apex. Сертификаты в томе caddy_data.
set -eu
DOMAIN="${DOMAIN:-}"
EMAIL="${ACME_EMAIL:-}"
OUT=/tmp/Caddyfile

COMMON='
	header {
		defer
		X-Content-Type-Options nosniff
		Referrer-Policy strict-origin-when-cross-origin
		X-Frame-Options SAMEORIGIN
		-Server
	}
	handle /healthz {
		respond "ok" 200
	}
	@assistant path /api/v1/assistant/messages /api/v1/assistant/messages/*
	handle @assistant {
		reverse_proxy web:80 {
			header_up Host {host}
			flush_interval -1
		}
	}
	handle {
		encode zstd gzip
		reverse_proxy web:80 {
			header_up Host {host}
		}
	}
'

if [ -z "$DOMAIN" ]; then
	cat >"$OUT" <<EOF
{
	auto_https off
}
:80 {
$COMMON
}
EOF
else
	EMAIL_LINE=""
	if [ -n "$EMAIL" ]; then
		EMAIL_LINE="	email $EMAIL"
	fi
	cat >"$OUT" <<EOF
{
$EMAIL_LINE
}
:80 {
	handle /healthz {
		respond "ok" 200
	}
}
http://www.${DOMAIN} {
	redir https://${DOMAIN}{uri} 301
}
www.${DOMAIN} {
	redir https://${DOMAIN}{uri} 301
}
${DOMAIN} {
$COMMON
}
EOF
fi

exec caddy run --config "$OUT" --adapter caddyfile
