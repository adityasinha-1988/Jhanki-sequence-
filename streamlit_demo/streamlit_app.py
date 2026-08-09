"""Jhanki Sequencer — Streamlit Simulator (v2, slider UI + verification)
------------------------------------------------------------------------
Software-only demo of the 16-channel relay sequencer.
"""

import time
import matplotlib.pyplot as plt
import streamlit as st

CHANNEL_COUNT = 16

st.set_page_config(page_title="Jhanki Sequencer — Simulator", layout="wide")

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

# Loop States
if "loop_enable" not in st.session_state:
    st.session_state.loop_enable = False
if "loop_channel" not in st.session_state:
    st.session_state.loop_channel = 1
if "loop_count" not in st.session_state:
    st.session_state.loop_count = 2
if "loop_gap" not in st.session_state:
    st.session_state.loop_gap = 1.0

st.title("🎛️ Jhanki Sequencer — Simulator")
st.caption(
    "Software-only demo. No real relays switch here — this mirrors the "
    "ON/OFF timeline logic your ESP32 + MCP23017 rig executes for real."
)

# --------------------------------------------------------------------------
# 1. Timeline range control & Grid Layout
# --------------------------------------------------------------------------

st.session_state.duration = st.number_input(
    "Sequence duration (seconds) — sets the base slider range below",
    min_value=1.0,
    value=st.session_state.duration,
    step=1.0,
    disabled=st.session_state.running,
)
duration = st.session_state.duration

st.subheader("Channel timing")
st.caption("Drag the slider to set ON (start) and OFF (end) times.")

# 2-Column Grid Implementation
cols = st.columns(2)

for i, ch in enumerate(st.session_state.channels):
    ch["start"] = min(ch["start"], duration)
    ch["end"] = min(ch["end"], duration)
    
    with cols[i % 2]:
        st.markdown(f"**Channel {ch['id']:02d}**")
        lo, hi = st.slider(
            f"Timing for Channel {ch['id']:02d}",
            min_value=0.0,
            max_value=float(duration),
            value=(float(ch["start"]), float(ch["end"])),
            step=0.5,
            key=f"slider_{ch['id']}",
            disabled=st.session_state.running,
            label_visibility="collapsed"
        )
        ch["start"], ch["end"] = lo, hi
        st.caption(f"ON: {lo:.1f}s | OFF: {hi:.1f}s")
        st.write("") # Spacer

st.divider()

# --------------------------------------------------------------------------
# 2. Loop Configuration
# --------------------------------------------------------------------------

st.subheader("Loop Settings")
l_col1, l_col2, l_col3, l_col4 = st.columns(4)

with l_col1:
    loop_enable = st.checkbox("Enable Loop", value=st.session_state.loop_enable, disabled=st.session_state.running)
with l_col2:
    loop_channel = st.selectbox("Select Channel", [c['id'] for c in st.session_state.channels], index=st.session_state.loop_channel-1, disabled=st.session_state.running or not loop_enable)
with l_col3:
    loop_count = st.number_input("Loop Total Count", min_value=1, value=st.session_state.loop_count, disabled=st.session_state.running or not loop_enable)
with l_col4:
    loop_gap = st.number_input("Gap Between Loops (s)", min_value=0.0, value=st.session_state.loop_gap, step=0.5, disabled=st.session_state.running or not loop_enable)

st.session_state.loop_enable = loop_enable
st.session_state.loop_channel = loop_channel
st.session_state.loop_count = loop_count
st.session_state.loop_gap = loop_gap

# Calculate active sequence windows dynamically based on loop settings
all_windows = []
dynamic_max_duration = duration

for ch in st.session_state.channels:
    if ch["end"] > ch["start"]:
        # Add the base sequence window
        all_windows.append({"id": ch["id"], "start": ch["start"], "end": ch["end"]})
        dynamic_max_duration = max(dynamic_max_duration, ch["end"])
        
        # Add looped windows if applicable
        if loop_enable and ch["id"] == loop_channel:
            curr_end = ch["end"]
            win_dur = ch["end"] - ch["start"]
            for _ in range(loop_count - 1):
                n_start = curr_end + loop_gap
                n_end = n_start + win_dur
                all_windows.append({"id": ch["id"], "start": n_start, "end": n_end})
                dynamic_max_duration = max(dynamic_max_duration, n_end)
                curr_end = n_end

max_duration = dynamic_max_duration

st.divider()

# --------------------------------------------------------------------------
# 3. Timeline preview (Gantt-style)
# --------------------------------------------------------------------------

st.subheader("Sequence preview")

if not all_windows:
    st.info("No channel has an ON window yet — set some times above.")
else:
    # Render chart scaling height based on unique active channels
    unique_active = set(w["id"] for w in all_windows)
    fig, ax = plt.subplots(figsize=(10, max(3, 0.35 * len(unique_active))))
    fig.patch.set_facecolor("#141416")
    ax.set_facecolor("#141416")

    # Sort blocks for consistent visual stacking
    for w in sorted(all_windows, key=lambda x: x["id"]):
        ax.barh(
            y=f"CH {w['id']:02d}",
            width=w["end"] - w["start"],
            left=w["start"],
            height=0.5,
            color="#E8A33D",
        )
        
    ax.set_xlabel("Time (s)", color="#8B8B8F")
    ax.tick_params(colors="#8B8B8F")
    for spine in ax.spines.values():
        spine.set_color("#3A3A3E")
    ax.set_xlim(0, max_duration)
    ax.grid(axis="x", color="#2A2A2E", linewidth=0.5)
    st.pyplot(fig, use_container_width=True)

st.divider()

# --------------------------------------------------------------------------
# 4. Controls
# --------------------------------------------------------------------------

c1, c2, c3 = st.columns([1, 1, 3])
with c1:
    start_clicked = st.button("▶ Start sequence", disabled=st.session_state.running)
with c2:
    stop_clicked = st.button("⏹ Stop all")

if start_clicked and max_duration > 0:
    st.session_state.running = True
    st.session_state.start_time = time.monotonic()
    st.session_state.prev_active = set()
    st.session_state.event_log = []

if stop_clicked:
    if st.session_state.running and st.session_state.prev_active:
        elapsed = time.monotonic() - (st.session_state.start_time or time.monotonic())
        for ch_id in sorted(st.session_state.prev_active):
            st.session_state.event_log.append(f"{elapsed:5.1f}s — CH {ch_id:02d} OFF (stopped)")
    st.session_state.running = False
    st.session_state.start_time = None
    st.session_state.prev_active = set()

# --------------------------------------------------------------------------
# 5. Live playback + event log
# --------------------------------------------------------------------------

st.subheader("Live state")
status_placeholder = st.empty()
progress_placeholder = st.empty()
grid_placeholder = st.empty()
log_placeholder = st.empty()

def compute_active(elapsed):
    active = set()
    for w in all_windows:
        if w["start"] <= elapsed < w["end"]:
            active.add(w["id"])
    return active

def log_transitions(elapsed, active_ids):
    turned_on = active_ids - st.session_state.prev_active
    turned_off = st.session_state.prev_active - active_ids
    for ch_id in sorted(turned_on):
        st.session_state.event_log.append(f"{elapsed:5.1f}s — CH {ch_id:02d} ON")
    for ch_id in sorted(turned_off):
        st.session_state.event_log.append(f"{elapsed:5.1f}s — CH {ch_id:02d} OFF")
    st.session_state.prev_active = active_ids

def render_state(elapsed, active_ids):
    with status_placeholder.container():
        if st.session_state.running:
            st.success(f"Running — {elapsed:.1f}s / {max_duration:.0f}s")
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
                st.caption("No transitions yet — start the sequence to see ON/OFF timestamps here.")

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

