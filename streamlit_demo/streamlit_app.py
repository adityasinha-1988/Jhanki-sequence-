"""Jhanki Sequencer — Streamlit Simulator (v8, Full Save/Load & State Sync)"""

import time
import json
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st

CHANNEL_COUNT = 16

st.set_page_config(page_title="Jhanki Sequencer", layout="wide")

# --------------------------------------------------------------------------
# State Initialization
# --------------------------------------------------------------------------

if "sequence_df" not in st.session_state:
    st.session_state.sequence_df = pd.DataFrame([
        {"Channel": f"CH {i:02d}", "Start (s)": 0.0, "End (s)": 0.0}
        for i in range(1, CHANNEL_COUNT + 1)
    ])
if "canvas_size" not in st.session_state:
    st.session_state.canvas_size = 60.0
if "global_loop_enable" not in st.session_state:
    st.session_state.global_loop_enable = False
if "global_loop_count" not in st.session_state:
    st.session_state.global_loop_count = 2
if "global_loop_gap" not in st.session_state:
    st.session_state.global_loop_gap = 1.0
if "running" not in st.session_state:
    st.session_state.running = False
if "start_time" not in st.session_state:
    st.session_state.start_time = None
if "prev_active" not in st.session_state:
    st.session_state.prev_active = set()
if "event_log" not in st.session_state:
    st.session_state.event_log = []

st.title("🎛️ Jhanki Sequencer")

# --------------------------------------------------------------------------
# 1. Save & Load Configuration
# --------------------------------------------------------------------------
st.subheader("File Management")
col_save, col_load = st.columns(2)

with col_save:
    # Build a combined JSON payload including both settings and table data
    save_payload = {
        "settings": {
            "canvas_size": st.session_state.canvas_size,
            "global_loop_enable": st.session_state.global_loop_enable,
            "global_loop_count": st.session_state.global_loop_count,
            "global_loop_gap": st.session_state.global_loop_gap
        },
        "sequence": st.session_state.sequence_df.to_dict(orient="records")
    }
    json_str = json.dumps(save_payload, indent=4)
    
    st.download_button(
        label="💾 Save Sequence Configuration",
        data=json_str,
        file_name="jhanki_sequence.json",
        mime="application/json",
        disabled=st.session_state.running
    )

with col_load:
    uploaded_file = st.file_uploader("📂 Load Sequence Configuration", type=["json"], label_visibility="collapsed", disabled=st.session_state.running)
    if uploaded_file is not None:
        try:
            data = json.load(uploaded_file)
            # Restore Settings
            if "settings" in data:
                st.session_state.canvas_size = data["settings"].get("canvas_size", 60.0)
                st.session_state.global_loop_enable = data["settings"].get("global_loop_enable", False)
                st.session_state.global_loop_count = data["settings"].get("global_loop_count", 2)
                st.session_state.global_loop_gap = data["settings"].get("global_loop_gap", 1.0)
            # Restore Sequence Data
            if "sequence" in data:
                st.session_state.sequence_df = pd.DataFrame(data["sequence"])
            st.success("Configuration loaded successfully!")
            time.sleep(1) # Short delay to show success message
            st.rerun()
        except Exception as e:
            st.error("Invalid file format. Please upload a valid JSON sequence.")

st.divider()

# --------------------------------------------------------------------------
# 2. Global Settings
# --------------------------------------------------------------------------
st.subheader("Global Sequence & Loop Settings")
col_dur, col_loop_en, col_loop_cnt, col_loop_gap = st.columns(4)

with col_dur:
    st.number_input(
        "Timeline Reference Range (s)", 
        min_value=1.0, 
        step=1.0, 
        key="canvas_size",
        disabled=st.session_state.running
    )

with col_loop_en:
    st.markdown("<div style='height: 35px;'></div>", unsafe_allow_html=True)
    st.toggle(
        "Enable Global Loop", 
        key="global_loop_enable",
        disabled=st.session_state.running
    )

with col_loop_cnt:
    st.number_input(
        "Total Loop Count", 
        min_value=1, 
        step=1, 
        key="global_loop_count",
        disabled=st.session_state.running or not st.session_state.global_loop_enable
    )
    
with col_loop_gap:
    st.number_input(
        "Gap Between Loops (s)",
        min_value=0.0,
        step=0.5,
        key="global_loop_gap",
        disabled=st.session_state.running or not st.session_state.global_loop_enable
    )

st.divider()

# --------------------------------------------------------------------------
# 3. Centralized Sequence Editor (Inline Table)
# --------------------------------------------------------------------------
st.subheader("Sequence Editor")
st.caption("Double-click kisi bhi cell par edit karne ke liye. Naya time block add karne ke liye table ke bottom mein '+' icon dabayein. Delete karne ke liye row select karke 'Delete' dabayein.")

# State sync fixed by assigning directly and bypassing extra rerun loop
edited_df = st.data_editor(
    st.session_state.sequence_df,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "Channel": st.column_config.SelectboxColumn(
            "Channel",
            options=[f"CH {i:02d}" for i in range(1, CHANNEL_COUNT + 1)],
            required=True
        ),
        "Start (s)": st.column_config.NumberColumn(
            "Start Time (s)", 
            min_value=0.0, 
            step=0.5, 
            required=True
        ),
        "End (s)": st.column_config.NumberColumn(
            "End Time (s)", 
            min_value=0.0, 
            step=0.5, 
            required=True
        )
    },
    key="data_editor",
    disabled=st.session_state.running
)
st.session_state.sequence_df = edited_df

# --------------------------------------------------------------------------
# 4. Compute Active Windows & Render Preview (Gantt Chart)
# --------------------------------------------------------------------------
base_windows = []

for _, row in edited_df.iterrows():
    ch_str = str(row.get("Channel", ""))
    if pd.isna(row.get("Start (s)")) or pd.isna(row.get("End (s)")):
        continue
        
    start = float(row["Start (s)"])
    end = float(row["End (s)"])
    
    if "CH" in ch_str and end > start:
        try:
            ch_id = int(ch_str.replace("CH ", ""))
            base_windows.append({"id": ch_id, "start": start, "end": end})
        except ValueError:
            pass

all_windows = []
cycle_lines = []

if base_windows:
    actual_seq_end = max(w["end"] for w in base_windows)
    
    if st.session_state.global_loop_enable:
        cycle_length = actual_seq_end + st.session_state.global_loop_gap
        loop_iterations = st.session_state.global_loop_count
        
        for iteration in range(loop_iterations):
            offset = iteration * cycle_length
            if iteration > 0:
                cycle_lines.append(offset)
            
            for w in base_windows:
                all_windows.append({
                    "id": w["id"],
                    "start": w["start"] + offset,
                    "end": w["end"] + offset
                })
        max_duration = (loop_iterations - 1) * cycle_length + actual_seq_end
    else:
        all_windows = base_windows.copy()
        max_duration = actual_seq_end
else:
    max_duration = st.session_state.canvas_size

st.subheader("Sequence Preview")

if not all_windows:
    st.info("Koi valid sequence set nahi hai. Data Editor mein start aur end time dalein.")
else:
    unique_active = set(w["id"] for w in all_windows)
    fig, ax = plt.subplots(figsize=(12, max(3, 0.4 * len(unique_active))))
    fig.patch.set_facecolor("#141416")
    ax.set_facecolor("#141416")

    for w in sorted(all_windows, key=lambda x: x["id"]):
        ax.barh(
            y=f"CH {w['id']:02d}",
            width=w["end"] - w["start"],
            left=w["start"],
            height=0.5,
            color="#2ECC71",
        )
        
    ax.set_xlabel("Time (s)", color="#8B8B8F")
    ax.tick_params(colors="#8B8B8F")
    for spine in ax.spines.values():
        spine.set_color("#3A3A3E")
    
    for line_x in cycle_lines:
        ax.axvline(x=line_x, color="#555555", linestyle="--", alpha=0.7)

    ax.set_xlim(0, max_duration + (max_duration * 0.05))
    ax.grid(axis="x", color="#2A2A2E", linewidth=0.5)
    st.pyplot(fig, use_container_width=True)

st.divider()

# --------------------------------------------------------------------------
# 5. Controls & Execution Logic
# --------------------------------------------------------------------------
c1, c2, c3 = st.columns([1, 1, 3])
with c1:
    start_clicked = st.button("▶ Start sequence", disabled=st.session_state.running, use_container_width=True)
with c2:
    stop_clicked = st.button("⏹ Stop all", use_container_width=True)

if start_clicked and all_windows:
    st.session_state.running = True
    st.session_state.start_time = time.monotonic()
    st.session_state.prev_active = set()
    st.session_state.event_log = []
    st.rerun()

if stop_clicked:
    if st.session_state.running and st.session_state.prev_active:
        elapsed = time.monotonic() - (st.session_state.start_time or time.monotonic())
        for ch_id in sorted(st.session_state.prev_active):
            st.session_state.event_log.append(f"{elapsed:5.1f}s — CH {ch_id:02d} OFF (stopped)")
    st.session_state.running = False
    st.session_state.start_time = None
    st.session_state.prev_active = set()
    st.rerun()

# --------------------------------------------------------------------------
# 6. Live State Render
# --------------------------------------------------------------------------
st.subheader("Live execution state")
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
            st.success(f"Running — Time: {elapsed:.1f}s / {max_duration:.1f}s")
        else:
            st.info("Idle")

    with progress_placeholder.container():
        pct = min(1.0, elapsed / max_duration) if max_duration > 0 else 0.0
        st.progress(pct)

    with grid_placeholder.container():
        grid_cols = st.columns(8)
        for i in range(1, CHANNEL_COUNT + 1):
            is_on = i in active_ids
            bg_color = '#2ECC71' if is_on else '#232326'
            text_color = '#141416' if is_on else '#8B8B8F'
            
            with grid_cols[(i - 1) % 8]:
                st.markdown(
                    f"""
                    <div style="
                        border-radius:8px; padding:10px; text-align:center; margin-bottom:8px;
                        background:{bg_color}; color:{text_color};
                        font-family:monospace; font-weight:600;
                    ">
                        CH {i:02d}<br>{'ON' if is_on else 'off'}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    with log_placeholder.container():
        with st.expander(f"Event log ({len(st.session_state.event_log)} transitions)", expanded=st.session_state.running):
            if st.session_state.event_log:
                st.code("\n".join(st.session_state.event_log[-40:]), language=None)
            else:
                st.caption("No transitions yet.")

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
    
