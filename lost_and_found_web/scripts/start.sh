#!/usr/bin/env bash
set -euo pipefail

python3 -m gunicorn --bind 0.0.0.0:${PORT:-5000} "lost_and_found_web.wsgi:app"
