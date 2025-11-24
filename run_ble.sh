#!/usr/bin/env bash
set -euo pipefail
BASE="/home/pi/navicap"
VENV="$BASE/.venv"
LOGDIR="$BASE/logs"
LOGFILE="$LOGDIR/ble_server.log"
mkdir -p "$LOGDIR"

# Para que el venv vea dbus instalado con APT:
export PYTHONPATH="/usr/lib/python3/dist-packages:${PYTHONPATH:-}"

# Cabecera mínima
{
  echo "========== $(date -Is) =========="
  echo "[wrapper] start; python: $("$VENV/bin/python" -V 2>&1)"
} >> "$LOGFILE" 2>&1

# Lanzar servidor (stdout/stderr -> log)
exec "$VENV/bin/python" -u "$BASE/ble_server.py" >> "$LOGFILE" 2>&1
