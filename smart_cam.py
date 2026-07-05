import time
import numpy as np
import cv2
import requests
import os
import threading
from picamera2 import Picamera2
from picamera2.devices.imx500 import IMX500

# --- KONFIGURATION ---
BOT_TOKEN = ""
CHAT_ID = ""
NAS_PATH = ""
MODEL = ""

DETECTION_THRESHOLD = 2  # Sehr sensibel
PHOTO_BURST_DURATION = 30  # 30 Sekunden lang Fotos machen
TELEGRAM_COOLDOWN = 60     # Nur alle 60 Sekunden eine Telegram-Nachricht schicken

# --- State Variables ---
person_counter = 0
last_telegram_time = 0
is_burst_active = False
burst_end_time = 0
last_photo_time = 0

print("Checking NAS Connection...")
while not os.path.exists(NAS_PATH):
    time.sleep(5)
print("NAS ready.")

def send_telegram_async(image_path, caption):
    """Sendet den sofortigen Telegram-Alarm im Hintergrund"""
    def _send():
        try:
            with open(image_path, "rb") as photo:
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                              data={"chat_id": CHAT_ID, "caption": caption},
                              files={"photo": photo}, timeout=15)
            # Temporäres Bild vom Pi löschen, um die SD-Karte sauber zu halten
            if os.path.exists(image_path):
                os.remove(image_path)
            print("📱 Telegram-Alarm erfolgreich versendet!", flush=True)
        except Exception as e:
            print(f"❌ Telegram Fehler: {e}", flush=True)
    threading.Thread(target=_send, daemon=True).start()

def save_photo_async(frame_copy, filepath):
    """Speichert Full-HD Bilder im Hintergrund auf dem NAS"""
    def _save():
        try:
            bgr_frame = cv2.cvtColor(frame_copy, cv2.COLOR_YUV2BGR_I420)
            cv2.imwrite(filepath, bgr_frame)
        except Exception as e:
            print(f"❌ Fehler beim Speichern auf NAS: {e}", flush=True)
    threading.Thread(target=_save, daemon=True).start()

# --- Kamera Initialisierung (MAX SETTINGS) ---
imx500 = IMX500(MODEL)
picam2 = Picamera2()
# UPGRADE: Hier wird die Kamera auf 1920x1080 (Full HD) gezwungen!
picam2.configure(picam2.create_video_configuration(main={"size": (1920, 1080), "format": "YUV420"}))
picam2.start()

print("🔍 KI active (MAX Settings Photo-Burst Mode - 1080p).")

try:
    while True:
        frame = picam2.capture_array()
        out = None

        for _ in range(5):
            meta = picam2.capture_metadata()
            out = imx500.get_outputs(meta)
            if out is not None:
                break
            time.sleep(0.01)

        if out is None:
            continue

        current_time = time.time()
        detected = False
        scores = np.atleast_1d(out[1][0])
        classes = np.atleast_1d(out[2][0])

        # KI Auswertung
        for i in range(len(scores)):
            if scores[i] > 0.05:
                class_id = int(classes[i])
                if class_id == 0 and scores[i] > 0.15:
                    detected = True

        # Bewegungstracking
        if detected:
            if not is_burst_active:
                person_counter += 1
                print(f"👤 Bewegung: {person_counter}/{DETECTION_THRESHOLD}", flush=True)

                if person_counter >= DETECTION_THRESHOLD:
                    print("🚨 Alarm! Starte 1080p Foto-Serie auf NAS...", flush=True)
                    is_burst_active = True
                    burst_end_time = current_time + PHOTO_BURST_DURATION
                    person_counter = 0

                    # 1. Blitzschneller Telegram-Alarm
                    if current_time - last_telegram_time > TELEGRAM_COOLDOWN:
                        timestamp = time.strftime("%Y%m%d-%H%M%S")
                        tg_path = f"/tmp/alarm_{timestamp}.jpg"
                        bgr_tg = cv2.cvtColor(frame, cv2.COLOR_YUV2BGR_I420)
                        cv2.imwrite(tg_path, bgr_tg)
                        send_telegram_async(tg_path, "⚠️ Objekt im Garten erkannt! (1080p)")
                        last_telegram_time = current_time
        else:
            if not is_burst_active:
                person_counter = max(0, person_counter - 0.5)

        # 2. Foto-Serie auf NAS speichern (1 Bild pro Sekunde)
        if is_burst_active:
            if current_time < burst_end_time:
                if current_time - last_photo_time >= 1.0: # Genau 1 Sekunde Pause zwischen Fotos
                    ms_stamp = time.strftime("%Y%m%d-%H%M%S")
                    nas_file = os.path.join(NAS_PATH, f"snapshot_{ms_stamp}_{int((current_time%1)*1000):03d}.jpg")

                    # Kopie des Full-HD Frames machen und an Speicher-Thread übergeben
                    save_photo_async(frame.copy(), nas_file)
                    last_photo_time = current_time
                    print(f"📸 1080p Foto gespeichert: {nas_file}", flush=True)
            else:
                print("⏹️ Foto-Serie beendet. Warte auf neue Bewegung.", flush=True)
                is_burst_active = False

except KeyboardInterrupt:
    print("\nSkript manuell beendet.")
except Exception as e:
    print(f"❌ Error in main loop: {e}")
finally:
    print("Cleanup...")
    picam2.stop()
    try:
        picam2.close()
    except:
        pass