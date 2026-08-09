"""
Jhanki Sequencer — FastAPI backend
-----------------------------------
Stores a 16-channel ON/OFF time sequence and, on /play, runs a background
timer loop that fires HTTP GET requests at the ESP32 to switch relays
(via the MCP23017 expander) on and off at the configured second-marks.

Run with:
    pip install fastapi uvicorn httpx pydantic
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import asyncio
import time
from typing import Dict, List, Optional, Set

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

ESP32_IP = "192.168.1.50"          # <-- set to your ESP32's actual local IP
ESP32_TIMEOUT = 2.0                 # seconds, per HTTP call to the ESP32
POLL_INTERVAL = 0.1                 # seconds, tick rate of the play loop
CHANNEL_COUNT = 16

app = FastAPI(title="Jhanki Sequencer Backend")

# Allow the Vite dev server (or any LAN frontend) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------

class ChannelWindow(BaseModel):
    id: int = Field(..., ge=1, le=CHANNEL_COUNT)
    start: float = Field(..., ge=0)
    end: float = Field(..., ge=0)


class SequenceConfig(BaseModel):
    channels: List[ChannelWindow]


class StatusResponse(BaseModel):
    running: bool
    elapsed: float
    active_channels: List[int]
    max_duration: float


# --------------------------------------------------------------------------
# In-memory state
# --------------------------------------------------------------------------

class SequencerState:
    def __init__(self) -> None:
        self.config: Dict[int, ChannelWindow] = {}
        self.running: bool = False
        self.start_time: Optional[float] = None
        self.elapsed: float = 0.0
        self.active_channels: Set[int] = set()
        self._task: Optional[asyncio.Task] = None
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def max_duration(self) -> float:
        if not self.config:
            return 0.0
        return max(c.end for c in self.config.values())


state = SequencerState()


# --------------------------------------------------------------------------
# ESP32 communication helpers
# --------------------------------------------------------------------------

async def send_relay_command(client: httpx.AsyncClient, channel_id: int, turn_on: bool) -> None:
    action = "on" if turn_on else "off"
    url = f"http://{ESP32_IP}/{channel_id}/{action}"
    try:
        await client.get(url, timeout=ESP32_TIMEOUT)
    except httpx.HTTPError as exc:
        # Don't let one flaky relay call kill the whole sequence; log and continue.
        print(f"[WARN] Failed to send {action.upper()} to channel {channel_id}: {exc}")


async def send_all_off(client: httpx.AsyncClient) -> None:
    tasks = [send_relay_command(client, ch_id, False) for ch_id in range(1, CHANNEL_COUNT + 1)]
    await asyncio.gather(*tasks, return_exceptions=True)


# --------------------------------------------------------------------------
# Playback loop
# --------------------------------------------------------------------------

async def playback_loop() -> None:
    state._client = httpx.AsyncClient()
    state.start_time = time.monotonic()
    state.active_channels = set()

    try:
        while state.running:
            now = time.monotonic()
            elapsed = now - state.start_time
            state.elapsed = elapsed

            if elapsed >= state.max_duration and state.max_duration > 0:
                break

            for ch_id, window in state.config.items():
                should_be_on = window.start <= elapsed < window.end
                is_on = ch_id in state.active_channels

                if should_be_on and not is_on:
                    await send_relay_command(state._client, ch_id, True)
                    state.active_channels.add(ch_id)
                elif not should_be_on and is_on:
                    await send_relay_command(state._client, ch_id, False)
                    state.active_channels.discard(ch_id)

            await asyncio.sleep(POLL_INTERVAL)
    finally:
        # Sequence finished naturally or was cancelled — make sure everything is off.
        await send_all_off(state._client)
        await state._client.aclose()
        state._client = None
        state.running = False
        state.active_channels = set()


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------

@app.post("/config")
async def save_config(cfg: SequenceConfig):
    if state.running:
        raise HTTPException(status_code=409, detail="Cannot update configuration while sequence is running")

    ids = [c.id for c in cfg.channels]
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=400, detail="Duplicate channel ids in configuration")

    for c in cfg.channels:
        if c.end < c.start:
            raise HTTPException(
                status_code=400,
                detail=f"Channel {c.id}: end time must be >= start time",
            )

    state.config = {c.id: c for c in cfg.channels}
    return {"message": "Configuration saved", "channels_configured": len(state.config)}


@app.get("/config")
async def get_config():
    return {"channels": list(state.config.values())}


@app.post("/play")
async def play():
    if state.running:
        raise HTTPException(status_code=409, detail="Sequence already running")
    if not state.config:
        raise HTTPException(status_code=400, detail="No configuration saved yet")

    state.running = True
    state._task = asyncio.create_task(playback_loop())
    return {"message": "Sequence started", "max_duration": state.max_duration}


@app.post("/stop")
async def stop():
    state.running = False
    if state._task and not state._task.done():
        # Let the loop's finally block send the all-off commands, then wait briefly for it.
        try:
            await asyncio.wait_for(state._task, timeout=ESP32_TIMEOUT + 2.0)
        except asyncio.TimeoutError:
            state._task.cancel()
    else:
        # Not running via the loop (e.g. already stopped) — still force all-off directly.
        async with httpx.AsyncClient() as client:
            await send_all_off(client)

    state.elapsed = 0.0
    state.active_channels = set()
    return {"message": "All channels stopped"}


@app.get("/status", response_model=StatusResponse)
async def status():
    return StatusResponse(
        running=state.running,
        elapsed=state.elapsed,
        active_channels=sorted(state.active_channels),
        max_duration=state.max_duration,
    )


@app.get("/")
async def root():
    return {"service": "Jhanki Sequencer Backend", "esp32_ip": ESP32_IP, "channels": CHANNEL_COUNT}
