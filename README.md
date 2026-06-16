# stimulus_maker — recorded-EOD playback

Replays a real fish's EOD timing back to it on the rig: one waveform is fired at
each recorded discharge time, with the *measured* onset-to-onset intervals
preserved (no quantising). Playback does **not** auto-start — the sequence idles
until you press **P**.

## Layout

```
build_playback.py        generator: Spike2 text export -> output sequencer (.pls)
run_playback.s2s         Spike2 config builder: loads waveform + sequencer, opens a ready sampling doc
input_sequences/         Spike2 text exports of recorded EOD times (input to build_playback.py)
output_sequences/        generated .pls sequencers (output of build_playback.py)
waveforms/               the EOD pulse waveforms played at each event (.smrx / .csv)
```

## Workflow

### 1. Generate the sequencer (`.pls`) — on any machine with Python 3

`build_playback.py` reads a Spike2 text export (absolute event times) and emits a
`.pls` that fires play-wave area `B` at each time.

```bash
python3 build_playback.py input_sequences/Fish1_2_playback.txt \
    --channel 2 --code B \
    --waveform waveforms/Bb_EOD_norm2V.smrx \
    -o output_sequences/fish12_ch2.pls
```

- `--channel` — which channel in the export carries the event times (default: first non-empty).
- `--code` — play-wave area code, a **letter** (must match `AREA$` in the `.s2s`; default `B`).
- `--waveform` — recorded in the `.pls` header for provenance only; the waveform itself is loaded by the `.s2s`, not the `.pls`.
- `-o` — output path.

The generated sequence idles at `IDLE: HALT` and defines two keyboard jumps:
**P** = play the train once (then returns to idle), **S** = stop / return to idle.
Do not hand-edit the `.pls`; regenerate it.

### 2. Edit `run_playback.s2s` to match your setup

Open `run_playback.s2s` and update the settings near the top:

- **`BASE$`** — the drive-mapped path of *this folder* on the Spike2 PC. Double every
  backslash, keep the trailing one, e.g.
  `"Z:\\NSB_2026\\WEF2026\\Rigs\\OliviaAlex\\Special Project\\behavior_control\\stimulus_maker\\"`.
- **`WAVEFILE$`** / **`SEQFILE$`** — the waveform and the `.pls` from step 1
  (paths relative to `BASE$`; already set to the `waveforms\` / `output_sequences\` layout).
- **`AREA$`** — must equal the `--code` letter used in step 1.
- **Wiring constants** — `DAC%`, `EODPORT%`, `MONPORT%`, and the channel/rate
  constants. Set these to match how the rig is patched.

### 3. Run it on the rig

1. In Spike2, run `run_playback.s2s` **once**. It builds the configuration, loads
   the waveform into play-wave area `B`, attaches the sequencer, saves
   `playback.s2cx`, and opens a ready (un-started) sampling window, then exits.
   (Next time you can skip the script: **File ▸ Load Configuration ▸ playback.s2cx**.)
2. Press **Start** to begin sampling. Nothing plays yet — the sequencer idles.
3. Press **P** (or click **Play** on the sequencer control panel) to play the
   recorded EOD train. Press **S** to stop early. Each keypress is logged in the
   keyboard-marker channel.
4. Stop and save with the normal Spike2 sample controls.

## Before collecting data

Capture the DAC output on the rig and verify the realized pulse timing — there is a
sub-millisecond `WAVEBR` arming latency just before each onset, and the source
waveform must be ~100 kHz for the playback rate to be correct (the `.s2s` warns if not).
