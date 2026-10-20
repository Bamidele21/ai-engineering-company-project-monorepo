#!/bin/sh
# Starts both Nexova Next.js apps (website + backoffice) from one container
# with hot reloading. Runs in the foreground under `docker compose up`.
set -e

# Use the webpack dev server (not Turbopack) so WATCHPACK_POLLING can make
# file watching work over Windows/OneDrive bind mounts, where inotify events
# are not delivered reliably.
cd /app/uis/website
npm run dev -- --webpack -H 0.0.0.0 -p 3000 &

cd /app/uis/backoffice
npm run dev -- --webpack -H 0.0.0.0 -p 3001 &

wait
