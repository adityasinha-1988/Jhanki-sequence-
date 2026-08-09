Jhanki Sequencer â€” Streamlit Simulator (v2, slider UI + verification)
------------------------------------------------------------------------
Software-only demo of the 16-channel relay sequencer.

What's new vs v1:
  - Each channel is set with a single range slider (drag both ends) instead
    of two number boxes â€” much easier on a touchscreen.
  - A Gantt-style timeline preview lets you SEE the whole sequence before
    running it, so you can catch overlaps/mistakes visually.
  - A live event log records every ON/OFF transition with its timestamp
    while playing, so you can verify the sequence actually fires at the
    times you configured (not just watch colors change).

Run locally:
    pip install streamlit matplotlib
    streamlit run streamlit_app.py
"""

import time

import matplotlib.pyplot as plt
import streamlit as st

CHANNEL_COUNT = 16

st.set_page_config(page_title="Jhanki Sequencer â€” Simulator", layout="wide")

# --------------------------------------------------------------------------
# State
# --------------------------------------------------------------------------

if "channels" not in st.session_state:
    st.session_state.channels = [
        {"id": i + 1, "start": 0.0, "end": 0.0} for i in range(CHANNEL_COUNT)
    ]
if "duration" not in st.session_state:
    st.session_state.duration = 60.0
if "running" not in st.session_state:
    st.session_state.running = False
if "start_time" not in st.session_state:
    st.session_state.start_time = None
if "prev_active" not in st.session_state:
    st.session_state.prev_active = set()
if "event_log" not in st.session_state:
    st.session_state.event_log = []

st.title("ðŸª” Jhanki Sequencer â€” Simulator")
st.caption(
    "Software-only demo. No real relays switch here â€” this mirrors the "
    "ON/OFF timeline logic your ESP32 + MCP23017 rig executes for real."
)

# --------------------------------------------------------------------------
# 1. Timeline range control
# --------------------------------------------------------------------------

st.session_state.duration = st.number_input(
    "Sequence duration (seconds) â€” sets the slider range below",
    min_value=1.0,
    value=st.session_state.duration,
    step=1.0,
    disabled=st.session_state.running,
)
duration = st.session_state.duration

st.subheader("Channel timing")
st.caption("Drag both ends of each slider to set when that channel turns ON and OFF.")

for ch in st.session_state.channels:
    # Clamp existing values into the (possibly changed) duration range.
    ch["start"] = min(ch["start"], duration)
    ch["end"] = min(ch["end"], duration)
    lo, hi = st.slider(
        f"Channel {ch['id']:02d}",
        min_value=0.0,
        max_value=float(duration),
        value=(float(ch["start"]), float(ch["end"])),
        step=0.5,
        key=f"slider_{ch['id']}",
        disabled=st.session_state.running,
    )
    ch["start"], ch["end"] = lo, hi

max_duration = max((c["end"] for c in st.session_state.channels), default=0.0)

st.divider()

# --------------------------------------------------------------------------
# 2. Timeline preview (Gantt-style) â€” check the sequence before running it
# --------------------------------------------------------------------------

st.subheader("Sequence preview")
active_windows = [c for c in st.session_state.channels if c["end"] > c["start"]]

if not active_windows:
    st.info("No channel has an ON window yet â€” drag some sliders above.")
else:
    fig, ax = plt.subplots(figsize=(10, max(3, 0.35 * len(active_windows))))
    fig.patch.set_facecolor("#141416")
    ax.set_facecolor("#141416")

    for i, c in enumerate(sorted(active_windows, key=lambda x: x["id"])):
        ax.barh(
            y=f"CH {c['id']:02d}",
            width=c["end"] - c["start"],
            left=c["start"],
            height=0.5,
            color="#E8A33D",
        )
    ax.set_xlabel("Time (s)", color="#8B8B8F")
    ax.tick_params(colors="#8B8B8F")
    for spine in ax.spines.values():
        spine.set_color("#3A3A3E")
    ax.set_xlim(0, duration)
    ax.grid(axis="x", color="#2A2A2E", linewidth=0.5)
    st.pyplot(fig, use_container_width=True)

st.divider()

# --------------------------------------------------------------------------
# 3. Controls
# --------------------------------------------------------------------------

c1, c2, c3 = st.columns([1, 1, 3])
with c1:
    start_clicked = st.button("â–¶ Start sequence", disabled=st.session_state.running)
with c2:
    stop_clicked = st.button("â¹ Stop all")

if start_clicked and max_duration > 0:
    st.session_state.running = True
    st.session_state.start_time = time.monotonic()
    st.session_state.prev_active = set()
    st.session_state.event_log = []

if stop_clicked:
    if st.session_state.running and st.session_state.prev_active:
        elapsed = time.monotonic() - (st.session_state.start_time or time.monotonic())
        for ch_id in sorted(st.session_state.prev_active):
            st.session_state.event_log.append(f"{elapsed:5.1f}s â€” CH {ch_id:02d} OFF (stopped)")
    st.session_state.running = False
    st.session_state.start_time = None
    st.session_state.prev_active = set()

# --------------------------------------------------------------------------
# 4. Live playback + event log (this is what actually verifies correctness)
# --------------------------------------------------------------------------

st.subheader("Live state")
status_placeholder = st.empty()
progress_placeholder = st.empty()
grid_placeholder = st.empty()
log_placeholder = st.empty()


def compute_active(elapsed):
    return {c["id"] for c in st.session_state.channels if c["start"] <= elapsed < c["end"]}


def log_transitions(elapsed, active_ids):
    turned_on = active_ids - st.session_state.prev_active
    turned_off = st.session_state.prev_active - active_ids
    for ch_id in sorted(turned_on):
        st.session_state.event_log.append(f"{elapsed:5.1f}s â€” CH {ch_id:02d} ON")
    for ch_id in sorted(turned_off):
        st.session_state.event_log.append(f"{elapsed:5.1f}s â€” CH {ch_id:02d} OFF")
    st.session_state.prev_active = active_ids


def render_state(elapsed, active_ids):
    with status_placeholder.container():
        if st.session_state.running:
            st.success(f"Running â€” {elapsed:.1f}s / {max_duration:.0f}s")
        else:
            st.info("Idle")

    with progress_placeholder.container():
        pct = min(1.0, elapsed / max_duration) if max_duration > 0 else 0.0
        st.progress(pct)

    with grid_placeholder.container():
        grid_cols = st.columns(8)
        for i, ch in enumerate(st.session_state.channels):
            is_on = ch["id"] in active_ids
            with grid_cols[i % 8]:
                st.markdown(
                    f"""
                    <div style="
                        border-radius:8px;
                        padding:10px;
                        text-align:center;
                        margin-bottom:8px;
                        background:{'#E8A33D' if is_on else '#232326'};
                        color:{'#141416' if is_on else '#8B8B8F'};
                        font-family:monospace;
                        font-weight:600;
                    ">
                        CH {ch['id']:02d}<br>{'ON' if is_on else 'off'}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    with log_placeholder.container():
        with st.expander(f"Event log ({len(st.session_state.event_log)} transitions)", expanded=st.session_state.running):
            if st.session_state.event_log:
                st.code("\n".join(st.session_state.event_log[-40:]), language=None)
            else:
                st.caption("No transitions yet â€” start the sequence to see ON/OFF timestamps here.")


if st.session_state.running and st.session_state.start_time is not None:
    elapsed = time.monotonic() - st.session_state.start_time
    if elapsed >= max_duration:
        active_ids = set()
        log_transitions(max_duration, active_ids)
        st.session_state.running = False
        st.session_state.start_time = None
        render_state(max_duration, active_ids)
        st.rerun()
    else:
        active_ids = compute_active(elapsed)
        log_transitions(elapsed, active_ids)
        render_state(elapsed, active_ids)
        time.sleep(0.2)
        st.rerun()
else:
    render_state(0.0, set())

st.divider()
st.caption(
    "This simulator mirrors the timing logic of the real FastAPI backend "
    "(`backend/main.py`), which sends actual HTTP GET commands to an ESP32 "
    "running MicroPython + MCP23017 to switch physical relays. Use the "
    "preview chart to sanity-check overlaps and the event log to confirm "
    "transitions fire at the right second before wiring up real motors."
)
