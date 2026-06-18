# stimulus_maker — recorded-EOD playback

Replays a real fish's EOD timing back to it on the rig: one waveform is fired at
each recorded discharge time, with the *measured* onset-to-onset intervals
preserved (no quantising). From one recorded train it builds **three stimuli over
the same waveform** — **exact**, **time-reversed**, and **scrambled-interval** —
each on its own key. Playback does **not** auto-start — the sequence idles until
you press a key.

## Layout

```
build_waveform.py        JSON waveform capture -> header-less CSV (for Spike2 ingest)
build_playback.py        Spike2 text export -> output sequencer (.pls, three trains)
run_playback.s2s         Spike2 config builder: loads waveform .smrx + sequencer, opens a ready sampling doc
input_sequences/         Spike2 text exports of recorded EOD times (input to build_playback.py)
output_sequences/        generated .pls sequencers (output of build_playback.py)
waveforms/               EOD waveforms: .json captures, .csv (Spike2 import), .smrx (loaded by the .s2s)
```

## Workflow

### 1. Convert the JSON waveform to CSV — on any machine with Python 3

`build_waveform.py` takes one record (the first by default) from a JSON capture,
normalises it (largest-magnitude sample → 0.2 V, the `norm2V` convention), and
writes a header-less CSV (one sample per line) that Spike2 reads.

```bash
python3 build_waveform.py waveforms/BB_T48_DAY4_MAY11.json \
    -o waveforms/BB_T48_DAY4_MAY11_norm.csv
```

- `--record` — which record to convert (default `0`).
- `--peak` — normalisation target (default `0.2`); `--raw` writes recorded Volts unchanged.

The source `Rate` must be ~100 kHz (the script warns otherwise).

Then **import the CSV into Spike2 and save it as a `.smrx`** (one waveform channel
at the JSON `Rate`, ~100 kHz). The `.smrx` is what `run_playback.s2s` loads into the
play-wave area; the CSV is just the data-exchange format between Python and Spike2.

### 2. Generate the sequencer (`.pls`)

`build_playback.py` reads a Spike2 text export (absolute event times) and emits a
`.pls` with three trains that all fire play-wave area `B`.

```bash
python3 build_playback.py input_sequences/Fish1_2_playback.txt \
    --channel 2 --code B --seed 0 \
    --waveform waveforms/BB_T48_DAY4_MAY11_norm.csv \
    -o output_sequences/fish12_ch2.pls
```

- `--channel` — which channel in the export carries the event times (default: first non-empty).
- `--code` — play-wave area code, a **letter** (must match `AREA$` in the `.s2s`; default `B`).
- `--seed` — RNG seed for the scrambled train (default `0`); recorded in the header, so the same seed reproduces the same order.
- `--waveform` — recorded in the `.pls` header for provenance only; the waveform itself is loaded by the `.s2s`, not the `.pls`.
- `-o` — output path.

The generated sequence idles at `IDLE: HALT` and defines four keyboard jumps:
**P** = exact train, **R** = time-reversed, **X** = scrambled-interval (each plays
once then returns to idle), **S** = stop / return to idle. All three trains share
the same waveform and the same interval *set* (identical min/max/mean ISI); only
the temporal order differs. Do not hand-edit the `.pls`; regenerate it.

### 3. Edit `run_playback.s2s` to match your setup

Open `run_playback.s2s` and update the settings near the top:

- **`BASE$`** — the drive-mapped path of *this folder* on the Spike2 PC. Double every
  backslash, keep the trailing one, e.g.
  `"Z:\\NSB_2026\\WEF2026\\Rigs\\OliviaAlex\\Special Project\\behavior_control\\stimulus_maker\\"`.
- **`WAVEFILE$`** — the waveform **`.smrx`** from step 1; **`SEQFILE$`** — the `.pls` from step 2
  (paths relative to `BASE$`; already set to the `waveforms\` / `output_sequences\` layout).
- **`AREA$`** — must equal the `--code` letter used in step 2.
- **`SRCCHAN%`** — the waveform channel inside the `.smrx` (which sets the replay rate; must be ~100 kHz).
- **Wiring constants** — `DAC%`, `PHYSPORT%` (physiology, ADC), `STIMPORT%`
  (DAC-loopback stimulus monitor, ADC), `CMDPORT%` (EOD command, Event input), and
  the channel/rate constants. Set these to match how the rig is patched.

### 4. Run it on the rig

1. In Spike2, run `run_playback.s2s` **once**. It builds the configuration, loads
   the waveform `.smrx` into play-wave area `B`, attaches the sequencer, saves
   `playback.s2cx`, and opens a ready (un-started) sampling window, then exits.
   (Next time you can skip the script: **File ▸ Load Configuration ▸ playback.s2cx**.)
2. Press **Start** to begin sampling. Nothing plays yet — the sequencer idles.
3. Press **P** (exact), **R** (reversed), or **X** (scrambled) to play that train;
   press **S** to stop early. Each keypress is logged in the keyboard-marker
   channel, so the recording knows which train ran.
4. Stop and save with the normal Spike2 sample controls.

## Before collecting data

Capture the DAC output on the rig and verify the realized pulse timing — there is a
sub-millisecond `WAVEBR` arming latency just before each onset, and the `.smrx`
waveform channel must be ~100 kHz for the playback rate to be correct (the `.s2s`
warns if not).
