#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/../docker/ngrok"
exec ngrok start --all \
    --config "$HOME/snap/ngrok/current/.config/ngrok/ngrok.yml" \
    --config ngrok.yml
