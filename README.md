# NaviCap 🚀
> Sistema de Asistencia y Detección de Obstáculos con Visión Artificial para Raspberry Pi 4.

!! ESTE PROYECTO ES UNA TESIS, SI LO OCUPARA SE DEBE PEDIR AUTORIZACIÓN, DEBIDO QUE ESTA EN TRÁMITES DE PATENTIZACIÓN.

## 📖 Descripción

**NaviCap** es una solución integrada de hardware y software diseñada para correr en una **Raspberry Pi 4B**. Utiliza modelos de Deep Learning (**YOLOv4-tiny**) para la detección de objetos en tiempo real y notifica sobre obstáculos o eventos a través de un servidor **Bluetooth Low Energy (BLE)**.


## ⚙️ Características Principales

* **Detección en Tiempo Real:** Implementación optimizada de YOLOv4-tiny para procesar video y detectar objetos definidos.
* **Conectividad BLE:** Servidor Bluetooth integrado (`ble_server.py`) para enviar alertas a dispositivos móviles u otros receptores.
* **Configurable:** Ajuste de parámetros de detección y obstáculos mediante archivos JSON (`config.json`, `obstacle.json`).
* **Modo Servicio:** Incluye configuraciones de `systemd` para ejecución automática al inicio del sistema.
* **Logging:** Sistema de registro de eventos en la carpeta `logs/`.

## 🛠️ Estructura del Proyecto

* `navicap_detect.py`: Script principal de visión por computadora. Carga el modelo y procesa las imágenes.
* `ble_server.py`: Gestiona la conexión Bluetooth y el envío de datos.
* `navicap_publish.py`: Módulo para la publicación de eventos detectados.
* `config.json` & `obstacle.json`: Archivos de configuración para parámetros del sistema y definición de zonas de obstáculos.
* `yolov4-tiny-custom.*`: Archivos del modelo neuronal (pesos y configuración).
* `run_ble.sh` / `navicap_bleonly.sh`: Scripts de shell para facilitar la ejecución.

## 📋 Requisitos Previos

* **Hardware:**
    * Raspberry Pi 4 Model B (Recomendado 4GB o más de RAM).
    * Cámara compatible (Pi Camera o USB Webcam).
* **Software:**
    * Raspberry Pi OS (64-bit recomendado).
    * Python 3.
    * Librerías principales: OpenCV (`opencv-python`), Numpy, PyBluez (o librería BLE correspondiente).

## 🚀 Instalación y Uso

1.  **Clonar el repositorio:**
    ```bash
    git clone [https://github.com/sofinzunza/NaviCap.git](https://github.com/sofinzunza/NaviCap.git)
    cd NaviCap
    ```

2.  **Instalar dependencias:**
    *(Asegúrate de instalar las librerías necesarias de Python)*
    ```bash
    pip3 install opencv-python numpy
    # Instalar dependencias de Bluetooth según sea necesario (ej. pybluez, gattlib)
    ```

3.  **Ejecución Manual:**
    Puedes iniciar el servicio BLE o la detección usando los scripts provistos:
    ```bash
    sudo chmod +x run_ble.sh
    ./run_ble.sh
    ```
    O ejecutar el script de Python directamente:
    ```bash
    python3 navicap_detect.py
    ```

4.  **Configuración Automática (Systemd):**
    Los archivos en la carpeta `-etc-systemd-system` están diseñados para configurar NaviCap como un servicio que inicia con la Raspberry Pi.

## 🧠 Personalización del Modelo

El sistema utiliza **YOLOv4-tiny** entrenado especialmente para este proyecto. Si deseas detectar nuevos objetos:
1.  Entrena tu modelo personalizado.
2.  Reemplaza los archivos `.weights` y `.cfg`.
3.  Actualiza el archivo `obj.names` con las nuevas clases.

## 🤝 Contribución

¡Las contribuciones son bienvenidas! Por favor, abre un "Issue" para discutir cambios mayores o envía un "Pull Request".

## 📄 Licencia

Este proyecto es de código abierto. Pero por favor hazme saber si lo utilizaras!

---

sofia.inzunzalara@gmail.com

*Desarrollado con ❤️ por [sofinzunza](https://github.com/sofinzunza)*
