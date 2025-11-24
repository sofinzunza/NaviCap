#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
# Evitar backend GStreamer en OpenCV (reduce warnings/errores en RPi)
os.environ.setdefault('OPENCV_VIDEOIO_PRIORITY_GSTREAMER', '0')

import time, math, statistics
import cv2
import RPi.GPIO as GPIO
from navicap_publish import push_obstacle

# ---------- Paths ----------
BASE  = os.path.expanduser('~/navicap')
CFG   = os.path.join(BASE, 'yolov4-tiny-custom.cfg')
WTS   = os.path.join(BASE, 'yolov4-tiny-custom_best.weights')
NAMES = os.path.join(BASE, 'obj.names')

# ---------- Camara ----------
CAM_INDEX = int(os.getenv('NAVICAP_CAM_INDEX', '0'))  # cambia si es /dev/video1
FRAME_W, FRAME_H, FPS = 640, 480, 15

# ---------- HC-SR04 (modo BCM) ----------
TRIG_PIN, ECHO_PIN = 23, 24

# ---------- Aliases de clases ----------
ALIASES = {
    "persona": "person", "person": "person",
    "perro": "dog", "dog": "dog",
    "bicicleta": "bicycle", "bicycle": "bicycle",
    "auto": "car", "car": "car",
    "moto": "motorcycle", "motorcycle": "motorcycle",
    "puerta": "door", "door": "door",
    "escalera": "stairs", "stairs": "stairs",
    "escalera_mecanica": "escalator", "escalator": "escalator",
    "semaforo": "traffic_light", "semaforo": "traffic_light", "traffic light": "traffic_light",
    "semáforo": "traffic_light",
    "traffic_light": "traffic_light",
    "arbol": "tree", "arbol": "tree", "tree": "tree", "árbol": "tree"
}
OBSTACLE_GROUP = {"person", "stairs", "motorcycle", "door", "escalator"}

def normalize(lbl: str) -> str:
    return ALIASES.get(lbl.strip(), lbl.strip())

# ---------- Cargar clases ----------
with open(NAMES, 'r', encoding='utf-8', errors='ignore') as f:
    CLASSES = [normalize(x) for x in f.read().splitlines() if x.strip()]

# ---------- YOLO tiny (OpenCV DNN) ----------
net = cv2.dnn.readNetFromDarknet(CFG, WTS)
net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

# Tamaño mayor mejora objetos chicos (semaforitos)
INPUT_SIZE = int(os.getenv('NAVICAP_YOLO_SIZE', '608'))  # prueba 736 si aun cuesta
model = cv2.dnn_DetectionModel(net)
model.setInputParams(size=(INPUT_SIZE, INPUT_SIZE), scale=1/255.0, swapRB=True)

# Umbrales por clase
CONF_GENERAL = 0.35
CONF_TLIGHT  = 0.12   # mas permisivo para semaforo
NMS          = 0.35

def open_camera(idx: int):
    cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
    if not cap.isOpened():
        cap = cv2.VideoCapture(idx)  # fallback
    # Preferir MJPG (si la camara lo soporta)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  FRAME_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)
    cap.set(cv2.CAP_PROP_FPS,          FPS)
    return cap

cap = open_camera(CAM_INDEX)

# ---------- HC-SR04 ----------
GPIO.setmode(GPIO.BCM)
GPIO.setup(TRIG_PIN, GPIO.OUT)
GPIO.setup(ECHO_PIN, GPIO.IN)
GPIO.output(TRIG_PIN, GPIO.LOW)
time.sleep(0.05)

def distance_m(samples=3, timeout=0.03) -> float:
    vals = []
    for _ in range(samples):
        GPIO.output(TRIG_PIN, True); time.sleep(10e-6); GPIO.output(TRIG_PIN, False)
        t0 = time.monotonic()
        while GPIO.input(ECHO_PIN) == 0:
            if time.monotonic() - t0 > timeout:
                break
        start = time.monotonic()
        while GPIO.input(ECHO_PIN) == 1:
            if time.monotonic() - start > timeout:
                break
        dur = time.monotonic() - start
        d = (dur * 343.0) / 2.0  # ida/vuelta
        if 0.02 <= d <= 5.0:
            vals.append(d)
        time.sleep(0.005)
    return statistics.median(vals) if vals else math.inf

# ---------- Color de semaforo ----------
def traffic_color_hsv(frame, box):
    x, y, w, h = map(int, box)
    # Ampliar ROI 25% para capturar el foco completo
    pad = int(max(w, h) * 0.25)
    x0 = max(0, x - pad); y0 = max(0, y - pad)
    x1 = min(frame.shape[1], x + w + pad)
    y1 = min(frame.shape[0], y + h + pad)
    roi = frame[y0:y1, x0:x1]
    if roi.size == 0:
        return 'unknown'
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

    # Rangos tolerantes
    red1  = cv2.inRange(hsv, (0,   70, 80), (10, 255, 255))
    red2  = cv2.inRange(hsv, (165, 70, 80), (180,255, 255))
    green = cv2.inRange(hsv, (35,  60, 80), (90, 255, 255))
    rpx = cv2.countNonZero(red1) + cv2.countNonZero(red2)
    gpx = cv2.countNonZero(green)

    area = roi.shape[0] * roi.shape[1]
    if area == 0:
        return 'unknown'
    # si la ROI es chica, acepta 0.5% del area
    if max(rpx, gpx) / area < 0.005:
        return 'unknown'
    return 'red' if rpx > gpx else 'green'

def pick_best(ids, scores, boxes):
    best = (-1.0, None, (0, 0, 0, 0))
    # prioriza obstaculos del grupo
    for cid, sc, box in zip(ids, scores, boxes):
        lbl = CLASSES[int(cid)]
        sc  = float(sc)
        if lbl in OBSTACLE_GROUP and sc > best[0]:
            best = (sc, lbl, box)
    if best[1] is not None:
        return best[1], best[0], best[2]
    # si no hay, el mayor score global
    for cid, sc, box in zip(ids, scores, boxes):
        sc  = float(sc); lbl = CLASSES[int(cid)]
        if sc > best[0]:
            best = (sc, lbl, box)
    return (best[1], best[0], best[2]) if best[1] else (None, 0.0, (0, 0, 0, 0))

def main():
    global cap
    if not cap.isOpened():
        print("[NAVICAP] Camara no abierta, reintentando?")
        cap = open_camera(CAM_INDEX)
        if not cap.isOpened():
            raise SystemExit("No se pudo abrir la camara. Revisa /dev/video* y permisos.")

    last_label  = 'ready'
    last_traffic= 'unknown'
    last_dist   = 9e9
    last_push   = 0.0
    last_tl_seen = 0.0


    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                cap.release()
                time.sleep(0.2)
                cap = open_camera(CAM_INDEX)
                continue

            ids, confs, boxes = model.detect(
                frame,
                confThreshold=min(CONF_GENERAL, 0.99),
                nmsThreshold=NMS
            )

            # A listas planas
            ids   = ids.flatten().tolist()   if len(ids)   else []
            confs = [float(x) for x in (confs.flatten().tolist() if len(confs) else [])]
            boxes = [tuple(map(int, b)) for b in (boxes if len(boxes) else [])]

            # Debug (primeras 5 detecciones)
            for i, (cid, sc) in enumerate(zip(ids, confs)):
                if i >= 5: break
                print(f"[DET] {i}: {CLASSES[int(cid)]} conf={float(sc):.2f}")

            dist = distance_m(samples=3)

            # --- Semaforo: buscar candidatos con umbral propio ---
            # --- Semaforo: buscar candidatos con umbral propio + filtros geomotricos ---
            traffic = 'unknown'
            tl_candidates = []
            frame_area = frame.shape[0] * frame.shape[1]

            for cid, sc, box in zip(ids, confs, boxes):
                lbl = CLASSES[int(cid)]
                if lbl != 'traffic_light': 
                    continue
                sc = float(sc)
                if sc < CONF_TLIGHT:
                    continue
                x,y,w,h = map(int, box)
                area = w*h
                if area/frame_area < 0.0015:   
                    continue
                ar = h/max(1,w)                # aspect ratio (alto/ancho)
                if ar < 1.1:                   # suelen ser mas altos que anchos
                    continue
                # opcional: preferir lo alto del frame (semaforos arriba)
                score = sc + 0.05*(y < frame.shape[0]*0.6)
                tl_candidates.append((score, box, sc))

            if tl_candidates:
                tl_candidates.sort(key=lambda x: x[0], reverse=True)
                _, best_box, best_sc = tl_candidates[0]
                traffic = traffic_color_hsv(frame, best_box)
                print(f"[TL] conf={best_sc:.2f} color={traffic} box={best_box}")
            
            now = time.monotonic()
            if traffic != 'unknown':
                last_tl_seen = now
            else:
                # si hace muy poquito lo vimos, mantenlo
                if now - last_tl_seen < 0.8:
                    traffic = last_traffic


            # --- Obstaculo principal para publicar ---
            label, score, box = pick_best(ids, confs, boxes)
            if label is None:
                label = 'none'

            now = time.monotonic()
            changed = (label != last_label) or (traffic != last_traffic) or (abs(dist - last_dist) > 0.15)
            timed   = (now - last_push) >= 0.7

            if changed or timed:
                # IMPORTANTE: distancia en METROS. Ej: 0.17 -> 17 cm
                push_obstacle(label, float(f"{dist:.2f}"), traffic)
                last_label, last_dist, last_traffic, last_push = label, dist, traffic, now

            time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        GPIO.cleanup()

if __name__ == '__main__':
    for p in (CFG, WTS, NAMES):
        if not os.path.exists(p):
            raise SystemExit(f"Falta archivo: {p}")
    main()
