#!/bin/sh
set -e

TEMPLATES=/etc/nginx/templates

if [ "$SSL_ENABLED" = "true" ]; then
    rm -f "$TEMPLATES/app-http.conf.template"
else
    rm -f "$TEMPLATES/app.conf.template"
fi
