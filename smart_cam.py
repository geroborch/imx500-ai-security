import time, numpy as np, subprocess, cv2, requests, os
from picamera2 import Picamera2
from picamera2.devices.imx500 import IMX500

# --- KONFIGURATION ---
BOT_TOKEN = "ENTER YOUR TELEGRAM BOT TOKEEN HERE"       # best replace them with variable loaded from .env file
CHAT_ID = "ENTER YOUR TELEGRAM CHAT TOKEN HERE"         # best replace them with variable loaded from .env file
NAS_PATH = "/mnt/nas/kamera"
MODEL = "/usr/share/imx500-models/imx500_network_ssd_mobilenetv2_fpnlite_320x320_pp.rpk"

DETECTION_THRESHOLD = 3
RECORDING_COOLDOWN = 30  # Cooldowntime in seconds after last detection
TELEGRAM_COOLDOWN = 60   # Spam protection

# --- State Variables ---

person_counter = 0
video_process = None
last_detection_time = 0
last_telegram_time = 0

print("Checking NAS Connection...")
while not os.path.exists(NAS_PATH):
    time.sleep(5)
print("NAS ready.")

def send_telegram_async(image_path, caption):
    """Sends Photo in the background so that AI does'nt pause"""
    def _send():
        try:
            with open(image_path, "rb") as photo:
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                              data={"chat_id": CHAT_ID, "caption": caption},
                              files={"photo": photo}, timeout=15)
        except Exception as e:
            print(f"Telegram Fehler: {e}")
    threading.Thread(target=_send, daemon=True).start()

# Kamera Initialisierung
imx500 = IMX500(MODEL)
picam2 = Picamera2()
picam2.configure(picam2.create_video_configuration(main={"size": (1920, 1080), "format": "YUV420"}))
picam2.start()

print("🔍 KI active (Lean Mode).")

try:
    while True:
        frame = picam2.capture_array()


        out = None
        for _ in range(5):
            meta = picam2.capture_metadata()
            out = imx500.get_outputs(meta)
            if out is not None:
                break
            time.sleep(0.01) # 10ms wait, incase ai chip still calculating

        if out is None:
            # After 5 attempts we skip frame
            continue


        current_time = time.time()
        detected = False

        scores = np.atleast_1d(out[1][0])
        classes = np.atleast_1d(out[2][0])
        for i in range(len(scores)):

            if scores[i] > 0.05:
                class_id = int(classes[i])
                print(f"🔍 Ai sees {class_id} mit {scores[i]:.2f}", flush=True)


                if class_id == 0 and scores[i] > 0.15:  # adjust sensibility here
                    detected = True
        if detected:
            person_counter += 1
            last_detection_time = current_time
            print(f"👤 Recognition: {person_counter}/{DETECTION_THRESHOLD}", flush=True)

            if person_counter >= DETECTION_THRESHOLD:
                timestamp = time.strftime("%Y%m%d-%H%M%S")


                if current_time - last_telegram_time > TELEGRAM_COOLDOWN:
                    image_path = f"/tmp/alarm_{timestamp}.jpg"
                    bgr_frame = cv2.cvtColor(frame, cv2.COLOR_YUV2BGR_I420)
                    cv2.imwrite(image_path, bgr_frame)
                    send_telegram_async(image_path, "⚠️ Object Detected! Video is being saved on NAS.")
                    last_telegram_time = current_time


                if video_process is None or video_process.poll() is not None:
                    print("🚨 Starts Recording ...", flush=True)
                    video_file = os.path.join(NAS_PATH, f"motion_{timestamp}.mp4")

                    video_process = subprocess.Popen([
                        'ffmpeg', '-loglevel', 'error', '-y',
                        '-f', 'rawvideo', '-pixel_format', 'yuv420p',
                        '-video_size', '1920x1080', '-framerate', '15',
                        '-i', '-',
                        '-c:v', 'h264_v4l2m2m', '-b:v', '3000k',
                        video_file
                    ], stdin=subprocess.PIPE)
        else:
            person_counter = max(0, person_counter - 0.5)


        if video_process is not None and video_process.poll() is None:
            try:
                video_process.stdin.write(frame.tobytes())

                if current_time - last_detection_time > RECORDING_COOLDOWN:
                    print("⏹️ Action over, stop recording", flush=True)
                    video_process.stdin.close()
                    video_process.wait()
                    video_process = None
                    person_counter = 0
            except BrokenPipeError:
                video_process = None

except Exception as e:
    print(f"❌ Error in main loop: {e}")
finally:
    print("Cleanup...")
    if video_process is not None:
        try:
            video_process.stdin.close()
            video_process.terminate()
        except: pass
    picam2.stop()
