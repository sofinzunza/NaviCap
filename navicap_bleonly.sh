#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C
iface=hci0
TO=/usr/bin/timeout

# Asegurar bluetoothd activo
systemctl is-active --quiet bluetooth.service || systemctl start bluetooth.service

# LE-only y sin pairing
btmgmt -i "$iface" power off || true
btmgmt -i "$iface" le on || true
btmgmt -i "$iface" bredr off || true
btmgmt -i "$iface" bondable off || true
btmgmt -i "$iface" connectable on || true
btmgmt -i "$iface" advertising on || true
btmgmt -i "$iface" power on || true

# Alias EXACTO (sin sufijos): "NaviCap"
$TO 6s bluetoothctl --timeout 5 system-alias "NaviCap" || \
  hciconfig "$iface" name "NaviCap" || true

# Para Bluetooth clásico (no BLE): dejar OFF discoverable y pairable
$TO 6s bluetoothctl --timeout 5 discoverable off || true
$TO 6s bluetoothctl --timeout 5 pairable off || true

# Diagnóstico corto
btmgmt -i "$iface" info || true
$TO 6s bluetoothctl show || true

# Reforzar politicas justo al final del script
timeout 6s bluetoothctl --timeout 5 discoverable off || true
sudo btmgmt -i hci0 bredr off || true

exit 0
