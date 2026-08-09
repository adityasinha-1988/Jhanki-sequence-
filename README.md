# Jhanki Sequencer — 16-Channel Relay Automation

## Files

- `frontend/App.jsx` — React (Vite + Tailwind) dashboard
- `backend/main.py` — FastAPI server (sequence storage + playback loop)
- `firmware/boot.py` — ESP32 MicroPython, Wi-Fi connect on boot
- `firmware/main.py` — ESP32 MicroPython, MCP23017 + HTTP relay server
- `firmware/mcp23017.py` — minimal MCP23017 driver (no external deps)

## Setup

### 1. Firmware (ESP32, MicroPython)
1. Flash MicroPython onto the ESP32 if not already done.
2. Edit `firmware/boot.py`: set `SSID` / `PASSWORD`. Optionally set `STATIC_IP`
   so the ESP32 always gets the same address — much easier than DHCP lookup.
3. Wire MCP23017: SCL → GPIO22, SDA → GPIO21 (edit `I2C_SCL_PIN`/`I2C_SDA_PIN`
   in `firmware/main.py` if wired differently), VDD/VSS to 5V/GND, A0-A2 tied
   to GND (address `0x20`) or set per your wiring.
4. Upload `boot.py`, `main.py`, and `mcp23017.py` to the ESP32 (e.g. via
   `ampy`, `mpremote`, or Thonny). Reset the board — it should print its IP.

### 2. Backend (FastAPI)
```bash
cd backend
pip install fastapi uvicorn httpx pydantic
```
Edit `ESP32_IP` in `main.py` to match the ESP32's actual IP (match `STATIC_IP`
above if you set one). Run:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Frontend (React + Vite + Tailwind)
```bash
npm create vite@latest frontend -- --template react
cd frontend
npm install
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```
Enable Tailwind in `tailwind.config.js` (`content: ["./index.html","./src/**/*.{js,jsx}"]`)
and add the Tailwind directives to `src/index.css`. Replace the generated
`src/App.jsx` with the provided `App.jsx`. If your backend runs on a
different machine, update `BACKEND_URL` at the top of the file. Then:
```bash
npm run dev
```

## How it works

1. You fill in Start/End (seconds) per channel in the dashboard and hit
   **Save configuration** → `POST /config` on the FastAPI backend.
2. **Start sequence** → `POST /play`. The backend runs an async loop, ticking
   every 100ms, comparing elapsed time to each channel's window, and firing
   `GET http://<ESP32_IP>/<channel_id>/on` or `/off` exactly on the
   transitions.
3. The ESP32's socket server parses that path and flips the matching
   MCP23017 pin, which switches the relay.
4. The dashboard polls `GET /status` twice a second to highlight active
   channels and drive the progress bar.
5. **Stop all** (or reaching the max end-time) sends `off` to every channel
   and resets state.

## Notes / things to double check before wiring up motors

- This is ON/OFF only — no PWM/soft-start, as specified. Automotive wiper
  motors and pumps at 24V/12V draw real inrush current; make sure your relay
  board's contact rating and the SMPS's ampere rating cover the largest motor
  you're switching, and keep motor/pump wiring physically separated from the
  5V logic side.
- The MCP23017 driver assumes IOCON.BANK is at its power-on default (0). If
  you've previously reconfigured the chip's BANK bit, the register map
  changes — a power cycle resets it to default.
- `send_all_off` runs whenever `/stop` is called, when the sequence reaches
  `max_duration`, or if the play loop errors out — so a network hiccup mid-
  sequence still results in relays being told to turn off rather than being
  left stuck on.
