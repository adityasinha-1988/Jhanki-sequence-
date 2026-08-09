"""
boot.py — runs once on power-up, before main.py.
Connects the ESP32 to the local Wi-Fi network.
"""

import network
import time

SSID = "YOUR_WIFI_SSID"          # <-- set your network name
PASSWORD = "YOUR_WIFI_PASSWORD"  # <-- set your network password

STATIC_IP = None
# To pin the ESP32's IP so it matches ESP32_IP in the FastAPI backend, set e.g.:
# STATIC_IP = ("192.168.1.50", "255.255.255.0", "192.168.1.1", "192.168.1.1")


def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if STATIC_IP:
        wlan.ifconfig(STATIC_IP)

    if not wlan.isconnected():
        print(f"Connecting to Wi-Fi SSID '{SSID}'...")
        wlan.connect(SSID, PASSWORD)

        timeout = 20
        while not wlan.isconnected() and timeout > 0:
            time.sleep(1)
            timeout -= 1
            print(".", end="")

    if wlan.isconnected():
        print("\nWi-Fi connected. IP:", wlan.ifconfig()[0])
    else:
        print("\nWi-Fi connection FAILED. Check SSID/password and retry.")

    return wlan


connect_wifi()
