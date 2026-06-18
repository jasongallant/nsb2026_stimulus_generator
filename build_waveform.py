#!/usr/bin/env python3
"""Convert a JSON EOD-waveform capture into a header-less CSV for Spike2 ingest.

This is the front end of the recorded-EOD playback pipeline. Waveforms are
captured as JSON (e.g. waveforms/BB_T48_DAY4_MAY11.json) -- a LIST of records,
each with:
    "wave"  : [float, ...]   the EOD samples, in recorded Volts
    "Rate"  : 100000          sample rate (Hz); the playback rate MUST be ~100 kHz
    plus metadata ("specimenno", "date", "gain", "temp", ...).

We take ONE record (the first by default), normalise it, and write the samples
one-per-line with NO header -- the same shape as the existing waveforms/*.csv,
so run_playback.s2s can Read() it straight into a play-wave area.

NORMALISATION (default): scale so the largest-magnitude sample = --peak (0.2),
matching the existing "norm2V" convention and keeping the sequencer DAC scale at
1. Pass --raw to write the recorded Volts unchanged.

Usage:
    python3 build_waveform.py waveforms/BB_T48_DAY4_MAY11.json
    python3 build_waveform.py waveforms/BB_T48_DAY4_MAY11.json \
        -o waveforms/BB_T48_norm2V.csv --peak 0.2
    python3 build_waveform.py waveforms/BB_T48_DAY4_MAY11.json --record 0 --raw

Next: import / load the CSV as the playback waveform (run_playback.s2s reads it
into play-wave area "B"), and build the sequencer with build_playback.py.
"""

import argparse
import json
import os
import sys

DEFAULT_PEAK = 0.2     # target largest-magnitude amplitude (Volts); see "norm2V"

# the rig replays at the source rate; outside this band the playback is wrong.
RATE_MIN = 99000.0
RATE_MAX = 101000.0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("json", help="JSON waveform capture (a list of records)")
    ap.add_argument("--record", type=int, default=0,
                    help="record index to convert (default 0 = first)")
    ap.add_argument("--peak", type=float, default=DEFAULT_PEAK,
                    help=f"normalise largest-magnitude sample to this (default {DEFAULT_PEAK})")
    ap.add_argument("--raw", action="store_true",
                    help="write recorded Volts unchanged (skip normalisation)")
    ap.add_argument("-o", "--output", default=None,
                    help="output .csv path (default: <json>_norm.csv beside the JSON)")
    args = ap.parse_args()

    with open(args.json) as f:
        data = json.load(f)
    if not isinstance(data, list):
        sys.exit(f"error: {args.json} is not a list of records")
    if not (0 <= args.record < len(data)):
        sys.exit(f"error: record {args.record} out of range "
                 f"(file has {len(data)} record(s))")

    rec = data[args.record]
    wave = rec.get("wave")
    if not isinstance(wave, list) or not wave:
        sys.exit(f"error: record {args.record} has no 'wave' array")
    wave = [float(v) for v in wave]
    rate = rec.get("Rate")

    src_min, src_max = min(wave), max(wave)
    peak_abs = max(abs(src_min), abs(src_max))

    if args.raw:
        out_wave = wave
        scale = 1.0
    else:
        if peak_abs == 0.0:
            sys.exit("error: waveform is all zeros; nothing to normalise")
        scale = args.peak / peak_abs
        out_wave = [v * scale for v in wave]

    if args.output:
        out = args.output
    else:
        base = os.path.splitext(os.path.basename(args.json))[0]
        out = os.path.join(os.path.dirname(os.path.abspath(args.json)),
                           f"{base}_norm.csv")

    with open(out, "w") as f:
        for v in out_wave:
            f.write(f"{v:.8g}\n")

    out_min, out_max = min(out_wave), max(out_wave)
    print(f"wrote {os.path.normpath(out)}")
    print(f"  record {args.record} of {len(data)}"
          + (f' ("{rec.get("specimenno")}")' if rec.get("specimenno") else ""))
    print(f"  samples : {len(out_wave)}"
          + (f"  @ {rate:g} Hz" if rate is not None else "  (no Rate in record)"))
    print(f"  source  : min {src_min:.6g}, max {src_max:.6g} V")
    if args.raw:
        print("  output  : raw (unscaled)")
    else:
        print(f"  output  : min {out_min:.6g}, max {out_max:.6g} V "
              f"(scale x{scale:.6g} -> peak {args.peak:g})")

    if rate is None:
        print("  WARNING: record has no 'Rate'; verify the source is ~100 kHz "
              "before playback.", file=sys.stderr)
    elif not (RATE_MIN <= float(rate) <= RATE_MAX):
        print(f"  WARNING: Rate is {float(rate):.0f} Hz, not ~100 kHz -- "
              "playback rate will be wrong.", file=sys.stderr)


if __name__ == "__main__":
    main()
