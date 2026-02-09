# Project: imx500-ai-security
# Version: 1.0.0-stable
# Status: Production

AI-powered security camera system for Raspberry Pi Zero 2 W using the IMX500 sensor-  incl. Objekt Detection, Telegram alerts, and automated NAS video storage ! 

features: 
- Minimal latency by running inference directly on the IMX500 sensor
- Automated video backup to NAS via RTSP stream capture.
- automated NAS-mount checks and auto-restart capabilities
- Instant & smart mobile alerts including a captured image, event timestamp

Installation 
Hardware Drivers: Ensure you have te latest RPi camera installed:
------------------------------------------------------------------------------
sudo apt update
sudo apt install libcamera-v4l2 python3-libcamera imx500-models python3-psutil
------------------------------------------------------------------------------
* Depending on your OS version(Debian Trixie/Bookworm), the AI models might be located in different directories. If the script doesnt load, verify the location using: find /usr/share -name "*.rpk"


Python Dependencies: Install the required libraries via pip:
------------------------------------------------------------
          pip install -r requirements.txt
------------------------------------------------------------

make sure to adjust the systemd-Service to have your System running 24/7 & after reboot 
-----------------------------------------------------------------
      sudo cp smartcam.service /etc/systemd/system/
      sudo systemctl daemon-reload
      sudo systemctl enable smartcam.service
      sudo systemctl start smartcam.service
-----------------------------------------------------------------

Once everything is setup you can run: 
-----------------------------------------
    journalctl -u smartcam.service -f
-----------------------------------------
to check the logs and ajust the script accordingly to your environment

