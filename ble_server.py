#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import os
import signal
import sys
import time
from datetime import datetime

from bluezero import adapter
from bluezero import peripheral
from bluezero import async_tools

# ==================== Defaults / estado base ====================
DEFAULT_CATEGORIES = [
    "person",
    "stairs",
    "motorcycle",
    "door",
    "escalator",
    "traffic_light",
]

CURRENT_CFG = {
    "vibration": False,
    "vibration_intensity": 90.0,
    "sound": False,
    "volume_intensity": 50.0,
    "alerts_enabled": DEFAULT_CATEGORIES[:],
    "min_distance": 1.0,
    "max_distance": 2.0,
}

CONFIG_PATH = os.path.expanduser('~/navicap/config.json')
OBSTACLE_FILE = os.path.expanduser('~/navicap/obstacle.json')

# ==================== UUIDs ====================
SERVICE_UUID       = '12345678-1234-1234-1234-123456789abc'
OBSTACLE_CHAR_UUID = '87654321-4321-4321-4321-cba987654321'  # READ + NOTIFY
CONFIG_CHAR_UUID   = '11111111-2222-3333-4444-555555555555'  # WRITE (app -> Pi)
CONFIG_STATE_UUID  = '22222222-3333-4444-5555-666666666666'  # READ + NOTIFY (Pi -> app)

# ==================== Obstacles: estado y watcher ====================
_last_obstacle_json = {
    "obstacle": "ready",
    "distance": 0.0,
    "traffic": "unknown",
    "ts": datetime.utcnow().isoformat() + "Z",
}
_obstacle_chr_obj = None
_last_ob_file_mtime = 0.0


def _poll_obstacle_file(_unused=None):
    """Lee obstacle.json SI existe y SI cambia, y manda NOTIFY."""
    global _last_ob_file_mtime

    try:
        if not os.path.exists(OBSTACLE_FILE):
            return True

        mtime = os.path.getmtime(OBSTACLE_FILE)

        # Solo volver a leer si cambia el archivo
        if mtime == _last_ob_file_mtime:
            return True

        _last_ob_file_mtime = mtime

        # Leer todo el archivo como texto primero
        with open(OBSTACLE_FILE, 'r', encoding='utf-8') as f:
            raw = f.read().strip()

        # Si esta vacio, probablemente lo pillamos en mitad de la escritura
        if not raw:
            # silencioso, reintentamos en el proximo tick
            return True

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Archivo a medio escribir: ignorar y reintentar
            print("[BLE] obstacle.json incompleto, reintentando...")
            return True

        obstacle = str(data.get('obstacle', 'unknown'))
        distance = float(data.get('distance', 0.0))
        traffic = str(data.get('traffic', 'unknown'))

        publish_obstacle(obstacle, distance, traffic)

        print(f"[BLE] obstacle.json -> NOTIFY: {obstacle} @ {distance:.2f} m (traffic={traffic})", flush=True)


    except Exception as e:
        print(f"[BLE] ERROR leyendo obstacle.json: {e}")

    return True

def _obstacle_read_cb():
    """Devuelve el ltimo JSON de obstaculo como bytes."""
    data = json.dumps(_last_obstacle_json, ensure_ascii=False)
    return list(data.encode("utf-8"))


def _obstacle_notify_cb(notifying, characteristic):
    """Guarda el characteristic para poder llamar set_value cuando haya notify."""
    global _obstacle_chr_obj
    _obstacle_chr_obj = characteristic if notifying else None
    print(f"[BLE] notify {'ON' if notifying else 'OFF'} para obstaculos")


def publish_obstacle(obstacle: str, distance_m: float, traffic_state: str):
    """Actualiza valor y notifica si hay suscripcion."""
    global _last_obstacle_json, _obstacle_chr_obj

    _last_obstacle_json = {
        "obstacle": str(obstacle),
        "distance": float(distance_m),
        "traffic": str(traffic_state),
        "ts": datetime.utcnow().isoformat() + "Z",
    }

    payload = json.dumps(_last_obstacle_json, ensure_ascii=False).encode('utf-8')

    if _obstacle_chr_obj is not None:
        _obstacle_chr_obj.set_value(list(payload))
        print(f"[BLE] NOTIFY enviado: {payload.decode('utf-8')}")
    else:
        # Todavia no hay central suscrito (la app no hizo notify ON)
        print("[BLE] publish_obstacle: no hay central suscrito aun")


# ==================== Config: normalización, cache, watcher ====================
_cfg_chr_obj = None         # characteristic READ+NOTIFY de config-state
_cfg_cache = {}             # espejo de config.json
_cfg_file_mtime = 0.0


def _cfg_default():
    return {
        "vibration": True,
        "vibration_intensity": 50.0,
        "sound": True,
        "volume_intensity": 50.0,
        "alerts_enabled": DEFAULT_CATEGORIES[:],
        "min_distance": 1.5,
        "max_distance": 4.0,
    }


def _cfg_load_from_disk():
    """Carga config.json a _cfg_cache (crea defaults si no existe)."""
    global _cfg_cache, _cfg_file_mtime
    try:
        if os.path.exists(CONFIG_PATH):
            m = os.path.getmtime(CONFIG_PATH)
            if m != _cfg_file_mtime:
                with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                    _cfg_cache = json.load(f)
                _cfg_file_mtime = m
        else:
            _cfg_cache = _cfg_default()
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(_cfg_cache, f, ensure_ascii=False, indent=2)
            _cfg_file_mtime = os.path.getmtime(CONFIG_PATH)
    except Exception as e:
        print(f"[BLE] ERROR cargando config: {e}")
        _cfg_cache = _cfg_default()


def _cfg_save_to_disk(cfg: dict):
    """Guarda cfg a disco y refresca cache/mtime."""
    global _cfg_cache, _cfg_file_mtime
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    to_save = dict(cfg)
    to_save["timestamp"] = int(time.time())
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(to_save, f, ensure_ascii=False, indent=2)
    _cfg_cache = dict(cfg)
    _cfg_file_mtime = os.path.getmtime(CONFIG_PATH)


def _cfg_notify_if_needed():
    """Empuja _cfg_cache a la característica READ+NOTIFY si hay suscriptor."""
    if _cfg_chr_obj is not None:
        payload = json.dumps(_cfg_cache, ensure_ascii=False).encode('utf-8')
        _cfg_chr_obj.set_value(list(payload))


def _poll_config_file(_unused=None):
    """Si alguien cambió config.json en disco, recarga y notifica a la app."""
    before = _cfg_file_mtime
    _cfg_load_from_disk()
    if _cfg_file_mtime != before:
        _cfg_notify_if_needed()
        print("[BLE] Config cambiada en disco -> NOTIFY")
    return True


def _cfg_read_cb():
    _cfg_load_from_disk()
    return list(json.dumps(_cfg_cache, ensure_ascii=False).encode('utf-8'))


def _cfg_notify_cb(notifying, characteristic):
    global _cfg_chr_obj
    _cfg_chr_obj = characteristic if notifying else None
    if notifying:
        _cfg_load_from_disk()
        _cfg_notify_if_needed()
    print(f"[BLE] notify {'ON' if notifying else 'OFF'} para config")


# ==================== Config: write de la app ====================
def _normalize_and_merge_config(raw_json: str):
    # Base previa
    prev = dict(CURRENT_CFG)
    try:
        payload = json.loads(raw_json)
    except Exception as e:
        print(f"[BLE] Config JSON invalido: {e}")
        return prev, [], []

    cfg = dict(prev)

    # Booleans simples
    for k in ("vibration", "sound"):
        if k in payload:
            cfg[k] = bool(payload[k])

    # Numéricos
    for k in ("vibration_intensity", "volume_intensity", "min_distance", "max_distance"):
        if k in payload:
            try:
                cfg[k] = float(payload[k])
            except Exception:
                pass

    # alerts_enabled vs obstacles_enabled
    new_set = None
    if isinstance(payload.get("alerts_enabled"), list):
        new_set = set(str(x) for x in payload["alerts_enabled"])
    if new_set is None and "obstacles_enabled" in payload:
        new_set = set(DEFAULT_CATEGORIES) if bool(payload["obstacles_enabled"]) else set()

    old_set = set(prev.get("alerts_enabled", DEFAULT_CATEGORIES))
    if new_set is None:
        new_set = set(old_set)
    cfg["alerts_enabled"] = sorted(list(new_set))

    enabled_now = sorted(list(new_set - old_set))
    disabled_now = sorted(list(old_set - new_set))
    return cfg, enabled_now, disabled_now


def _config_write_cb(value: bytes, options):
    """WRITE: app -> Pi. Guarda en disco y notifica eco por la característica READ+NOTIFY."""
    try:
        if isinstance(value, (list, tuple)):
            value = bytes(value)
        raw = value.decode('utf-8').strip()
    except Exception:
        print("[BLE] Error decodificando bytes de config")
        return

    new_cfg, enabled_now, disabled_now = _normalize_and_merge_config(raw)

    # Actualiza globals y disco
    global CURRENT_CFG
    CURRENT_CFG = dict(new_cfg)
    try:
        _cfg_save_to_disk(CURRENT_CFG)
        _cfg_notify_if_needed()  # eco para el central suscrito
        if enabled_now:
            print(f"[BLE] Obstaculos ACTIVADOS: {', '.join(enabled_now)}")
        if disabled_now:
            print(f"[BLE] Obstaculos DESACTIVADOS: {', '.join(disabled_now)}")
        print(f"[BLE] Config recibida y guardada en {CONFIG_PATH}: {CURRENT_CFG}")
    except Exception as e:
        print(f"[BLE] Error guardando config: {e}")


# ==================== Conexión ====================
def _on_connect(ble_device):
    print(f"[BLE] Conectado: {ble_device.address}")


def _on_disconnect(adapter_address, device_address):
    print(f"[BLE] Desconectado: {device_address}")


# ==================== Peripheral ====================
def _get_adapter_and_alias():
    adpts = list(adapter.Adapter.available())
    if not adpts:
        print("No hay adaptadores BLE disponibles.")
        sys.exit(1)
    a = adpts[0] if isinstance(adpts[0], adapter.Adapter) else adapter.Adapter(adpts[0])
    return a.address, a.alias or "NaviCap"


def build_and_publish():
    adapter_addr, alias = _get_adapter_and_alias()
    local_name = alias
    print(f"[BLE] Publicando Peripheral en {adapter_addr} con nombre '{local_name}'")

    periph = peripheral.Peripheral(adapter_addr, local_name=local_name)

    periph.add_service(srv_id=1, uuid=SERVICE_UUID, primary=True)

    # Obstacles: READ + NOTIFY
    periph.add_characteristic(
        srv_id=1,
        chr_id=1,
        uuid=OBSTACLE_CHAR_UUID,
        value=list(json.dumps(_last_obstacle_json).encode('utf-8')),
        notifying=False,
        flags=['read', 'notify'],
        read_callback=_obstacle_read_cb,
        write_callback=None,
        notify_callback=_obstacle_notify_cb,
    )

    # Config (WRITE)
    periph.add_characteristic(
        srv_id=1,
        chr_id=2,
        uuid=CONFIG_CHAR_UUID,
        value=[],
        notifying=False,
        flags=['write', 'write-without-response'],
        write_callback=_config_write_cb,
        read_callback=None,
        notify_callback=None,
    )

    # Config state (READ + NOTIFY)
    _cfg_load_from_disk()
    periph.add_characteristic(
        srv_id=1,
        chr_id=3,
        uuid=CONFIG_STATE_UUID,
        value=list(json.dumps(_cfg_cache, ensure_ascii=False).encode('utf-8')),
        notifying=False,
        flags=['read', 'notify'],
        read_callback=_cfg_read_cb,
        write_callback=None,
        notify_callback=_cfg_notify_cb,
    )

    periph.on_connect = _on_connect
    periph.on_disconnect = _on_disconnect

    periph.publish()

    # Timers: obstacle.json y config.json
    async_tools.add_timer_seconds(0.5, _poll_obstacle_file, None)
    async_tools.add_timer_seconds(0.5, _poll_config_file, None)
    print(f"[BLE] Watcher de obstaculos activo en: {OBSTACLE_FILE}")


    # Heartbeat liviano para mantener viva la suscripción (opcional)
    def _heartbeat(_unused=None):
        _cfg_notify_if_needed()
        return True

    async_tools.add_timer_seconds(10, _heartbeat, None)

    return periph


# ==================== Demo opcional ====================
def _start_demo():
    obstacles = [
        ("persona", 1.6, "green"),
        ("auto",    3.2, "red"),
        ("perro",   0.9, "green"),
        ("puerta",  0.7, "green"),
        ("bicicleta", 2.5, "red"),
    ]
    idx = {"i": 0}

    def _tick(_chr):
        o, d, t = obstacles[idx["i"] % len(obstacles)]
        idx["i"] += 1
        publish_obstacle(o, d, t)
        return _obstacle_chr_obj is not None

    async_tools.add_timer_seconds(2, _tick, None)


# ==================== Main ====================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Envia notificaciones de ejemplo (cada 2s).",
    )
    args = parser.parse_args()

    build_and_publish()
    if args.demo:
        _start_demo()

    def _sigint(_sig, _frm):
        print("\n[BLE] Saliendo...")
        # Pedimos al loop que pare y luego salimos
        try:
            loop.quit()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, _sigint)

    # ? Crear el event loop de bluezero y arrancarlo
    loop = async_tools.EventLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        print("\n[BLE] KeyboardInterrupt, saliendo...")
        try:
            loop.quit()
        except Exception:
            pass



if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        import traceback
        print("[FATAL] Excepcion no controlada:", e)
        try:
            with open('/home/pi/navicap/last_err.log', 'a', encoding='utf-8') as lf:
                lf.write(datetime.utcnow().isoformat() + 'Z\n')
                lf.write(repr(e) + '\n')
                lf.write(traceback.format_exc() + '\n\n')
        except Exception:
            pass
        raise
