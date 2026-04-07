#!/bin/bash
# script to easily start the secure Docker cloudflare tunnel environment
echo "Building and starting CaptainHandy backend + Cloudflare Tunnel via Docker..."
docker compose up -d --build
echo "All systems running! View logs using 'docker compose logs -f'"
