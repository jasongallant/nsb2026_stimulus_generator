#!/usr/bin/env python3
"""Generate a SPIKE2 output-sequencer (.pls) that replays a single waveform at a
list of recorded EOD times.

Where build_sequences.py synthesises the structured dishabituation TRAINS (fixed
bursts/intervals), this script takes the *actual* discharge times exported from a
Spike2 recording and emits one pulse (one play-wave trigger) at each time, so the
rig replays a real fish's EOD timing back to it.

INPUT -- a Spike2 text export (e.g. Fish1_2_playback.txt). The format is:
    "INFORMATION"  ... (file/source metadata)
    "SUMMARY"      ... one row per channel: "num" "type" "title" ...
    "CHANNEL" "N"
    <blank>
    894.0746375            <- absolute event times, seconds, one per line
    894.2245475
    ...
    <blank>
    "CHANNEL" "M"
    ...
Empty channels have no numeric lines. Event channels (Evt+, Marker) carry the
times we want; Waveform channels are listed in the SUMMARY but have no times here.

OUTPUT -- a .pls that, for each event time, arms and triggers ONE play-wave area
(the waveform), spaced by the *measured* onset-to-onset interval. Times are
zeroed so the first event fires at t=0; intervals are taken straight from the
data (NOT quantised to a fixed grid), so any rate modulation in the original
recording is reproduced.

The waveform itself is NOT in the .pls. As in the rest of this repo, the pulse is
loaded into a Spike2 "play wave" area (1 cycle, 100 kHz, on a DAC) and referenced
here by its area CODE (a LETTER -- digits clash with keyboard jump keys). Load it
separately (PlayWaveAdd in the .s2s / config). Pass --waveform to record which
file the area is expected to hold; it is written into the .pls header for
provenance only.

Usage:
    python3 build_playback.py input_sequences/Fish1_2_playback.txt
    python3 build_playback.py input_sequences/Fish1_2_playback.txt --channel 2 \
        --code B --waveform waveforms/Bb_EOD_norm2V.smrx -o output_sequences/fish12_ch2.pls

The sequence does NOT auto-run: at sampling start it idles at IDLE: HALT and waits
for a key. Press 'P' (or the sequencer-control-panel Play button) to jump to PLAY
and run the train once; it then JUMPs back to RESET (idle). Press 'S' to stop and
return to idle. These keyboard jumps follow the build_sequences.py master-sequencer
idiom (label, then 'KEY before the opcode, then a >prompt for the control panel) and
require the sampling config to allow jumps -- SampleSeqCtrl(1,0); run_playback.s2s
sets this up.

Sequencer idioms match build_sequences.py (Spike2 v7 manual, ch.5): per pulse
WAVEGO code,T -> WAVEBR ,W -> WAVEST T (onset) -> DELAY -> WAVEST S, i.e. 5
instructions, so each onset-to-onset DELAY subtracts PULSE_INSTR. The <=1 ms
WAVEBR arming latency sits just before each onset -- verify realised timing on the
rig (capture the DAC output) before collecting data.
"""

import argparse
import os
import sys

# ---- sequencer parameters (match build_sequences.py) ------------------------
MS_PER_STEP = 0.1     # sequencer step (Power1401: >=0.010, multiple of 0.001)
DEFAULT_CODE = "B"    # play-wave area code (a LETTER; see module docstring)

# instructions executed per unrolled pulse, for the DELAY -N compensation:
#   WAVEGO, WAVEBR, WAVEST T, DELAY, WAVEST S -> 5
PULSE_INSTR = 5

# shortest onset-to-onset interval the rig can honour; below this the waveform
# would not have finished playing and/or the DELAY would underflow. Warn only.
MIN_INTERVAL_MS = 1.0


def parse_export(path):
    """Parse a Spike2 text export into {channel_number: [float times]} plus a
    {channel_number: title} map from the SUMMARY block. Only channels that carry
    numeric event times come back non-empty."""
    times = {}
    titles = {}
    cur = None
    in_summary = False
    with open(path) as f:
        for raw in f:
            line = raw.rstrip("\n")
            stripped = line.strip()
            if not stripped:
                continue
            # section / structure markers are tab-separated quoted tokens
            tokens = [t.strip().strip('"') for t in line.split("\t")]
            head = tokens[0]
            if head == "SUMMARY":
                in_summary = True
                cur = None
                continue
            if head == "INFORMATION":
                in_summary = False
                cur = None
                continue
            if head == "CHANNEL":
                in_summary = False
                cur = int(tokens[1])
                times.setdefault(cur, [])
                continue
            if in_summary:
                # row: "num" "type" "title" rate ...
                if len(tokens) >= 3 and tokens[0].isdigit():
                    titles[int(tokens[0])] = tokens[2]
                continue
            if cur is not None:
                try:
                    times[cur].append(float(stripped))
                except ValueError:
                    # any non-numeric line ends the current channel's data
                    cur = None
    return times, titles


def build(event_times, code, src_name, channel, title, waveform):
    """Build the .pls text. `event_times` are absolute seconds (will be zeroed)."""
    t0 = event_times[0]
    rel = [t - t0 for t in event_times]                  # seconds from first event
    intervals_ms = [(rel[i + 1] - rel[i]) * 1000.0       # onset-to-onset, ms
                    for i in range(len(rel) - 1)]
    n = len(event_times)

    H = []
    H.append(f";Waveform PLAYBACK sequence -- replays one waveform at recorded EOD times")
    H.append(";GENERATED by build_playback.py -- DO NOT EDIT BY HAND")
    H.append(f";source export : {src_name}")
    H.append(f";channel       : {channel}" + (f'  ("{title}")' if title else ""))
    H.append(f";waveform      : {waveform or '(load into play-wave area ' + code + ')'}")
    H.append(f";play-wave area: {code}")
    H.append(";control       : idles at HALT; press 'P' (or the control-panel Play "
             "button) to start playback, 'S' to stop/return to idle")
    H.append(f";pulses        : {n}  (first at t=0; original start {t0:.6f} s)")
    if intervals_ms:
        H.append(f";interval ms   : min {min(intervals_ms):.2f}, "
                 f"max {max(intervals_ms):.2f}, "
                 f"mean {sum(intervals_ms) / len(intervals_ms):.2f}")
        H.append(f";total dur     : {rel[-1]:.3f} s")
    H.append("")
    H.append(f"            SET    {MS_PER_STEP},1,0         ;ms/step; DAC scale 1, offset 0 (Volts)")
    H.append("")
    H.append("RESET:    'S DIGOUT [00000000]      ;stop / all markers low   >Idle: press P to play, S to stop")
    H.append("            DAC    0,0             ;DAC 0 to 0 V")
    H.append("IDLE:       HALT                   ;wait for a key           >Idle: press P to play")
    H.append("")
    H.append("PLAY:    'P DIGOUT [.......1]      ;start playback           >Playing back recorded EOD train")
    H.append("")

    for i in range(n):
        wl = f"P{i + 1}w"
        H.append(f"            ; -- pulse {i + 1}/{n}  (recorded t={rel[i]:.6f} s)")
        H.append(f"            WAVEGO {code},T            ;arm waveform (triggered)")
        H.append(f"{wl}:{' ' * max(1, 8 - len(wl))}WAVEBR {wl},W           ;wait until armed")
        H.append( "            WAVEST T               ;trigger -> ONSET")
        if i < n - 1:
            ms = intervals_ms[i]
            H.append(f"            DELAY  ms({ms:.3f})-{PULSE_INSTR}      ;onset-to-onset = {ms:.3f} ms")
        H.append( "            WAVEST S               ;stop (safety; pulse already ended)")
        H.append("")

    H.append("            DIGOUT [00000000]      ;clear markers")
    H.append("            DAC    0,0")
    H.append("            JUMP   RESET           ;playback done -> idle   >Done; press P to replay")
    H.append("")
    return "\n".join(H), intervals_ms


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export", help="Spike2 text export (e.g. Fish1_2_playback.txt)")
    ap.add_argument("--channel", type=int, default=None,
                    help="channel number to use (default: first non-empty)")
    ap.add_argument("--code", default=DEFAULT_CODE,
                    help=f"play-wave area code, a LETTER (default {DEFAULT_CODE})")
    ap.add_argument("--waveform", default=None,
                    help="waveform file the area holds (recorded in header for provenance)")
    ap.add_argument("-o", "--output", default=None,
                    help="output .pls path (default: <export>_ch<N>.pls beside the export)")
    args = ap.parse_args()

    times, titles = parse_export(args.export)
    nonempty = [c for c in sorted(times) if times[c]]
    if not nonempty:
        sys.exit(f"error: no channels with event times found in {args.export}")

    if args.channel is None:
        channel = nonempty[0]
    elif args.channel in times and times[args.channel]:
        channel = args.channel
    else:
        sys.exit(f"error: channel {args.channel} has no event times "
                 f"(channels with data: {nonempty})")

    event_times = times[channel]
    if len(event_times) < 2:
        sys.exit(f"error: channel {channel} has {len(event_times)} event(s); "
                 "need >=2 to build a sequence")

    text, intervals_ms = build(event_times, args.code, os.path.basename(args.export),
                               channel, titles.get(channel, ""), args.waveform)

    if args.output:
        out = args.output
    else:
        base = os.path.splitext(os.path.basename(args.export))[0]
        out = os.path.join(os.path.dirname(os.path.abspath(args.export)),
                           f"{base}_ch{channel}.pls")

    with open(out, "w") as f:
        f.write(text)

    short = [round(m, 2) for m in intervals_ms if m < MIN_INTERVAL_MS]
    print(f"wrote {os.path.normpath(out)}")
    print(f"  channel {channel}"
          + (f' ("{titles[channel]}")' if titles.get(channel) else "")
          + f", {len(event_times)} pulses, area '{args.code}'")
    if intervals_ms:
        print(f"  intervals ms: min {min(intervals_ms):.2f}, "
              f"max {max(intervals_ms):.2f}, "
              f"mean {sum(intervals_ms) / len(intervals_ms):.2f}")
    if short:
        print(f"  WARNING: {len(short)} interval(s) < {MIN_INTERVAL_MS} ms "
              f"({short}); verify the waveform fits and DELAY does not underflow",
              file=sys.stderr)
    print("  reminder: load the waveform into play-wave area "
          f"'{args.code}' (PlayWaveAdd) before running.")


if __name__ == "__main__":
    main()
