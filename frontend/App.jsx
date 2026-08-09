import React, { useState, useEffect, useRef, useCallback } from "react";

// ---------------------------------------------------------------------------
// Jhanki Sequencer — 16-Channel Relay Control Dashboard (v2)
// Talks to a local FastAPI backend at BACKEND_URL.
//
// What's new vs v1:
//   - Each channel is set with a dual-handle range slider (drag both ends)
//     instead of two separate number inputs — faster and more usable,
//     especially on touch screens.
//   - A timeline preview (mini Gantt chart) shows all 16 channels' ON
//     windows at once, so you can visually verify the sequence before
//     hitting Start.
//   - A live event log records every ON/OFF transition with its timestamp
//     while playing, so you can confirm the sequence is actually firing
//     correctly, not just watch colors change.
// ---------------------------------------------------------------------------

const BACKEND_URL = "http://localhost:8000"; // change to your PC's LAN IP if the ESP32 / other devices need to reach it
const CHANNEL_COUNT = 16;

const defaultChannel = (i) => ({
  id: i + 1,
  label: `Channel ${String(i + 1).padStart(2, "0")}`,
  start: 0,
  end: 0,
});

function classNames(...c) {
  return c.filter(Boolean).join(" ");
}

// ---------------------------------------------------------------------------
// Dual-handle range slider (two native <input type="range"> layered so
// each thumb can be dragged independently, with a colored fill between them)
// ---------------------------------------------------------------------------

function DualRangeSlider({ min, max, step, valueMin, valueMax, onChange, disabled }) {
  const range = Math.max(max - min, 0.0001);
  const pctMin = ((valueMin - min) / range) * 100;
  const pctMax = ((valueMax - min) / range) * 100;

  const handleMinChange = (e) => {
    const next = Math.min(Number(e.target.value), valueMax);
    onChange(next, valueMax);
  };

  const handleMaxChange = (e) => {
    const next = Math.max(Number(e.target.value), valueMin);
    onChange(valueMin, next);
  };

  return (
    <div className="relative h-6 w-full select-none">
      <div className="absolute top-1/2 h-1.5 w-full -translate-y-1/2 rounded-full bg-[#232326]" />
      <div
        className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-[#E8A33D]"
        style={{ left: `${pctMin}%`, width: `${Math.max(pctMax - pctMin, 0)}%` }}
      />
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={valueMin}
        disabled={disabled}
        onChange={handleMinChange}
        className="range-thumb absolute top-1/2 w-full -translate-y-1/2 appearance-none bg-transparent"
        style={{ zIndex: valueMin === valueMax ? 2 : 1 }}
      />
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={valueMax}
        disabled={disabled}
        onChange={handleMaxChange}
        className="range-thumb absolute top-1/2 w-full -translate-y-1/2 appearance-none bg-transparent"
        style={{ zIndex: 2 }}
      />
      <style>{`
        .range-thumb {
          pointer-events: none;
        }
        .range-thumb::-webkit-slider-thumb {
          pointer-events: auto;
          appearance: none;
          width: 18px;
          height: 18px;
          border-radius: 9999px;
          background: #EDEAE3;
          border: 3px solid #E8A33D;
          cursor: pointer;
          margin-top: 0;
        }
        .range-thumb::-moz-range-thumb {
          pointer-events: auto;
          width: 18px;
          height: 18px;
          border-radius: 9999px;
          background: #EDEAE3;
          border: 3px solid #E8A33D;
          cursor: pointer;
        }
        .range-thumb::-webkit-slider-runnable-track {
          background: transparent;
        }
        .range-thumb::-moz-range-track {
          background: transparent;
        }
        .range-thumb:disabled::-webkit-slider-thumb {
          border-color: #4A4A4E;
          cursor: not-allowed;
        }
      `}</style>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Timeline preview — a mini Gantt chart so you can eyeball the sequence
// ---------------------------------------------------------------------------

function TimelinePreview({ channels, duration }) {
  const active = channels.filter((c) => c.end > c.start);

  if (active.length === 0) {
    return (
      <p className="text-sm text-[#8B8B8F] py-6 text-center">
        No channel has an ON window yet — drag some sliders above.
      </p>
    );
  }

  return (
    <div className="space-y-1.5">
      {active.map((c) => {
        const leftPct = (c.start / duration) * 100;
        const widthPct = ((c.end - c.start) / duration) * 100;
        return (
          <div key={c.id} className="flex items-center gap-3">
            <span className="w-14 shrink-0 font-mono text-xs text-[#8B8B8F]">
              CH {String(c.id).padStart(2, "0")}
            </span>
            <div className="relative h-4 flex-1 rounded bg-[#1B1B1E]">
              <div
                className="absolute top-0 h-full rounded bg-[#E8A33D]"
                style={{ left: `${leftPct}%`, width: `${Math.max(widthPct, 0.5)}%` }}
              />
            </div>
            <span className="w-24 shrink-0 text-right font-mono text-xs text-[#8B8B8F]">
              {c.start}s–{c.end}s
            </span>
          </div>
        );
      })}
      <div className="flex justify-between pt-1 font-mono text-[10px] text-[#5A5A5E]">
        <span>0s</span>
        <span>{duration}s</span>
      </div>
    </div>
  );
}

export default function App() {
  const [duration, setDuration] = useState(60);
  const [channels, setChannels] = useState(
    Array.from({ length: CHANNEL_COUNT }, (_, i) => defaultChannel(i))
  );
  const [savedAt, setSavedAt] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);

  const [isPlaying, setIsPlaying] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [activeChannels, setActiveChannels] = useState(new Set());
  const [statusMsg, setStatusMsg] = useState("Idle");
  const [eventLog, setEventLog] = useState([]);
  const prevActiveRef = useRef(new Set());
  const pollRef = useRef(null);

  const maxDuration = channels.reduce((m, c) => Math.max(m, Number(c.end) || 0), 0);

  // ---- Config editing -----------------------------------------------------
  const updateChannelRange = (idx, start, end) => {
    setChannels((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], start, end };
      return next;
    });
  };

  const handleDurationChange = (e) => {
    const next = Math.max(1, Number(e.target.value) || 1);
    setDuration(next);
    // clamp existing windows into the new range
    setChannels((prev) =>
      prev.map((c) => ({
        ...c,
        start: Math.min(c.start, next),
        end: Math.min(c.end, next),
      }))
    );
  };

  const saveConfig = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const payload = {
        channels: channels.map((c) => ({
          id: c.id,
          start: Number(c.start) || 0,
          end: Number(c.end) || 0,
        })),
      };
      const res = await fetch(`${BACKEND_URL}/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(`Server responded ${res.status}`);
      setSavedAt(new Date());
    } catch (err) {
      setSaveError(err.message || "Failed to save configuration");
    } finally {
      setSaving(false);
    }
  };

  // ---- Playback control ----------------------------------------------------
  const startSequence = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/play`, { method: "POST" });
      if (!res.ok) throw new Error(`Server responded ${res.status}`);
      setIsPlaying(true);
      setStatusMsg("Running");
      setEventLog([]);
      prevActiveRef.current = new Set();
    } catch (err) {
      setStatusMsg(`Error: ${err.message}`);
    }
  };

  const stopAll = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/stop`, { method: "POST" });
      if (!res.ok) throw new Error(`Server responded ${res.status}`);
    } catch (err) {
      setStatusMsg(`Error: ${err.message}`);
    } finally {
      setIsPlaying(false);
      setElapsed(0);
      setActiveChannels(new Set());
      prevActiveRef.current = new Set();
      setStatusMsg("Stopped");
    }
  };

  // Poll backend for live status while playing; diff active sets to build an event log
  const pollStatus = useCallback(async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/status`);
      if (!res.ok) return;
      const data = await res.json();
      const nextActive = new Set(data.active_channels ?? []);
      const t = data.elapsed ?? 0;

      const turnedOn = [...nextActive].filter((id) => !prevActiveRef.current.has(id));
      const turnedOff = [...prevActiveRef.current].filter((id) => !nextActive.has(id));
      if (turnedOn.length || turnedOff.length) {
        setEventLog((prev) => {
          const additions = [
            ...turnedOn.map((id) => `${t.toFixed(1)}s — CH ${String(id).padStart(2, "0")} ON`),
            ...turnedOff.map((id) => `${t.toFixed(1)}s — CH ${String(id).padStart(2, "0")} OFF`),
          ];
          return [...prev, ...additions].slice(-40);
        });
      }
      prevActiveRef.current = nextActive;

      setElapsed(t);
      setActiveChannels(nextActive);
      setIsPlaying(Boolean(data.running));
      setStatusMsg(data.running ? "Running" : t > 0 ? "Sequence complete" : "Idle");
    } catch {
      // backend unreachable — ignore this tick
    }
  }, []);

  useEffect(() => {
    pollRef.current = setInterval(pollStatus, 500);
    return () => clearInterval(pollRef.current);
  }, [pollStatus]);

  const progressPct = maxDuration > 0 ? Math.min(100, (elapsed / maxDuration) * 100) : 0;

  return (
    <div className="min-h-screen bg-[#141416] text-[#EDEAE3] font-sans">
      {/* Header / control strip */}
      <header className="sticky top-0 z-10 border-b border-[#2A2A2E] bg-[#141416]/95 backdrop-blur">
        <div className="mx-auto max-w-4xl px-4 py-4 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div
              className={classNames(
                "h-3 w-3 rounded-full",
                isPlaying ? "bg-[#E8A33D] animate-pulse" : "bg-[#4A4A4E]"
              )}
              aria-hidden="true"
            />
            <div>
              <h1 className="font-mono text-lg tracking-tight text-[#EDEAE3]">
                JHANKI SEQUENCER
              </h1>
              <p className="text-xs text-[#8B8B8F] font-mono">
                16-CH relay timeline · {statusMsg}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={saveConfig}
              disabled={saving || isPlaying}
              className="rounded-md border border-[#3A3A3E] px-4 py-2 text-sm font-medium text-[#EDEAE3] hover:border-[#E8A33D] hover:text-[#E8A33D] transition-colors disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save configuration"}
            </button>
            <button
              onClick={startSequence}
              disabled={isPlaying}
              className="rounded-md bg-[#E8A33D] px-4 py-2 text-sm font-semibold text-[#141416] hover:bg-[#F0B658] transition-colors disabled:opacity-40"
            >
              Start sequence
            </button>
            <button
              onClick={stopAll}
              className="rounded-md bg-[#C2453C] px-4 py-2 text-sm font-semibold text-white hover:bg-[#D6564D] transition-colors"
            >
              Stop all
            </button>
          </div>
        </div>

        {/* live progress bar */}
        <div className="mx-auto max-w-4xl px-4 pb-3">
          <div className="flex items-center justify-between text-xs font-mono text-[#8B8B8F] mb-1">
            <span>{elapsed.toFixed(1)}s</span>
            <span>{maxDuration}s total</span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-[#232326] overflow-hidden">
            <div
              className="h-full bg-[#E8A33D] transition-all duration-300 ease-linear"
              style={{ width: `${progressPct}%` }}
            />
          </div>
        </div>
        {saveError && (
          <p className="mx-auto max-w-4xl px-4 pb-2 text-xs text-[#C2453C]">{saveError}</p>
        )}
        {savedAt && !saveError && (
          <p className="mx-auto max-w-4xl px-4 pb-2 text-xs text-[#6FA37D]">
            Saved at {savedAt.toLocaleTimeString()}
          </p>
        )}
      </header>

      <main className="mx-auto max-w-4xl px-4 py-6 space-y-8">
        {/* Duration control */}
        <section>
          <label className="flex items-center justify-between text-sm font-medium text-[#EDEAE3] mb-1">
            <span>Sequence duration (seconds)</span>
            <input
              type="number"
              min="1"
              value={duration}
              disabled={isPlaying}
              onChange={handleDurationChange}
              className="w-24 rounded border border-[#3A3A3E] bg-[#1B1B1E] px-2 py-1 text-right font-mono text-[#EDEAE3] focus:border-[#E8A33D] focus:outline-none disabled:opacity-50"
            />
          </label>
          <p className="text-xs text-[#8B8B8F]">Sets the range every slider below can reach.</p>
        </section>

        {/* Channel sliders */}
        <section>
          <h2 className="text-sm font-semibold text-[#EDEAE3] mb-1">Channel timing</h2>
          <p className="text-xs text-[#8B8B8F] mb-4">
            Drag either end of a slider to set when that channel turns ON and OFF.
          </p>
          <div className="space-y-4">
            {channels.map((ch, idx) => {
              const active = activeChannels.has(ch.id);
              return (
                <div
                  key={ch.id}
                  className={classNames(
                    "rounded-lg border p-3 transition-colors",
                    active ? "border-[#E8A33D] bg-[#2A2114]" : "border-[#2A2A2E] bg-[#1B1B1E]"
                  )}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-mono text-sm text-[#EDEAE3]">{ch.label}</span>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-[#8B8B8F]">
                        {ch.start}s – {ch.end}s
                      </span>
                      <span
                        className={classNames(
                          "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-mono",
                          active ? "bg-[#E8A33D] text-[#141416]" : "bg-[#232326] text-[#8B8B8F]"
                        )}
                      >
                        {active ? "ON" : "off"}
                      </span>
                    </div>
                  </div>
                  <DualRangeSlider
                    min={0}
                    max={duration}
                    step={0.5}
                    valueMin={ch.start}
                    valueMax={ch.end}
                    disabled={isPlaying}
                    onChange={(s, e) => updateChannelRange(idx, s, e)}
                  />
                </div>
              );
            })}
          </div>
        </section>

        {/* Timeline preview */}
        <section>
          <h2 className="text-sm font-semibold text-[#EDEAE3] mb-1">Sequence preview</h2>
          <p className="text-xs text-[#8B8B8F] mb-3">
            Check the whole sequence for overlaps or mistakes before running it.
          </p>
          <div className="rounded-lg border border-[#2A2A2E] bg-[#1B1B1E] p-4">
            <TimelinePreview channels={channels} duration={duration} />
          </div>
        </section>

        {/* Event log */}
        <section>
          <h2 className="text-sm font-semibold text-[#EDEAE3] mb-1">
            Event log {eventLog.length > 0 && `(${eventLog.length})`}
          </h2>
          <p className="text-xs text-[#8B8B8F] mb-3">
            Every ON/OFF transition fired during playback, with its timestamp — use this to confirm
            the sequence is actually running on time.
          </p>
          <div className="rounded-lg border border-[#2A2A2E] bg-[#1B1B1E] p-4 h-48 overflow-y-auto font-mono text-xs text-[#8B8B8F] space-y-1">
            {eventLog.length === 0 ? (
              <p className="text-[#5A5A5E]">No transitions yet — start the sequence to see them here.</p>
            ) : (
              eventLog.map((line, i) => <div key={i}>{line}</div>)
            )}
          </div>
        </section>

        <p className="text-xs text-[#8B8B8F] font-mono pt-2">
          Backend: {BACKEND_URL} — edit BACKEND_URL at the top of App.jsx if your
          FastAPI server runs elsewhere on the network.
        </p>
      </main>
    </div>
  );
}
