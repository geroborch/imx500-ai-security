import time, numpy as np, subprocess, cv2, requests, os
from picamera2 import Picamera2
from picamera2.devices.imx500 import IMX500

# --- KONFIGURATION ---
BOT_TOKEN = "ENTER YOUR TELEGRAM BOT TOKEEN HERE"       # best replace them with variable loaded from .env file
CHAT_ID = "ENTER YOUR TELEGRAM CHAT TOKEN HERE"         # best replace them with variable loaded from .env file
NAS_PATH = "/mnt/nas/kamera"
MODEL = "/usr/share/imx500-models/imx500_network_ssd_mobilenetv2_fpnlite_320x320_pp.rpk"

LAST_ALARM = 0
ALARM_COOLDOWN = 60
DETECTION_THRESHOLD = 3  # ajust sensibility here
person_counter = 0

print("Prüfe NAS...")
while not os.path.exists(NAS_PATH):
    time.sleep(5)
print("NAS bereit.")

imx500 = IMX500(MODEL)
picam2 = Picamera2()
picam2.configure(picam2.create_video_configuration(main={"size": (640, 480), "format": "YUV420"}))          #YUV420 - native format of the RPi ISP, avoiding heavy RGB conversions
picam2.start()

# FFmpeg with silent Log-Level
ffmpeg_stream = subprocess.Popen([
    'ffmpeg', '-loglevel', 'error', '-y',
    '-f', 'rawvideo', '-vcodec', 'rawvideo', '-s', '640x480',
    '-pix_fmt', 'yuv420p', '-r', '15', '-i', '-',
    '-c:v', 'h264_v4l2m2m', '-b:v', '1000k',        # h264_v4l2m2m to reduce cpu load.
    '-f', 'rtsp', 'rtsp://localhost:8554/cam'
], stdin=subprocess.PIPE)

print("🔍 AI is active and scanning")

try:
    while True:
        frame = picam2.capture_array()
        meta = picam2.capture_metadata()
        out = imx500.get_outputs(meta)

        detected = False
        if out is not None:
            scores = np.atleast_1d(out[1][0])
            classes = np.atleast_1d(out[2][0])
            for i in range(len(scores)):
                if scores[i] > 0.15: # adjust sensibility here - keep it low in the beginning
                    if int(classes[i]) == 0: # 0 = Person, check readme for different classes
                        detected = True

        if detected:
            person_counter += 1
            print(f"👤 Detection: {person_counter}/{DETECTION_THRESHOLD}", flush=True)
            if person_counter >= DETECTION_THRESHOLD:
                print("🚨 ALARM running!", flush=True)
                timestamp = time.strftime("%Y%m%d-%H%M%S")
                image_path = f"/tmp/alarm_{timestamp}.jpg"
                bgr_frame = cv2.cvtColor(frame, cv2.COLOR_YUV2BGR_I420)
                cv2.imwrite(image_path, bgr_frame)

                try:
                    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                                  data={"chat_id": CHAT_ID, "caption": "⚠️ Person Detected ! "},
                                  files={"photo": open(image_path, "rb")}, timeout=10)
                except: pass

                video_file = os.path.join(NAS_PATH, f"video_{timestamp}.mp4")
                subprocess.Popen(['timeout', '10', 'ffmpeg', '-loglevel', 'quiet', '-i', 'rtsp://localhost:8554/cam', '-c', 'copy', video_file])
                person_counter = 0 # Reset after alarm!
        else:
            person_counter = max(0, person_counter - 0.5) #  Hysteresis logic: Instead of a full reset, the counter decreases slowly to compensate flickering...

        ffmpeg_stream.stdin.write(frame.tobytes())

except Exception as e:
    print(f"Error: {e}")
finally:
    picam2.stop()
    ffmpeg_stream.stdin.close()