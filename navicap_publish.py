#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
from datetime import datetime

# Carpeta base de NaviCap
BASE_DIR = os.path.expanduser('~/navicap')
OBSTACLE_FILE = os.path.join(BASE_DIR, 'obstacle.json')
LOG_DIR = os.path.join(BASE_DIR, 'logs')
OBSTACLE_LOG = os.path.join(LOG_DIR, 'navicap_obstacles.log')

os.makedirs(BASE_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

def push_obstacle(obstacle: str, distance_m: float, traffic: str = "unknown",
                  confidence: float | None = None) -> None:
    """
    Guarda el ultimo obstaculo detectado en obstacle.json,
    que es el archivo que ble_server.py esta vigilando.
    """
    data = {
        "obstacle": str(obstacle),
        "distance": float(distance_m),
        "traffic": str(traffic),
        "ts": datetime.utcnow().isoformat() + "Z",
    }
    if confidence is not None:
        data["confidence"] = float(confidence)

    # Escribir el JSON donde ble_server.py lo espera
    with open(OBSTACLE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    # Log simple para debug
    with open(OBSTACLE_LOG, "a", encoding="utf-8") as lf:
        lf.write(datetime.utcnow().isoformat() + "Z " + json.dumps(data, ensure_ascii=False) + "\n")

    print(f"[NAVICAP] push {data}")
