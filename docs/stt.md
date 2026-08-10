# Local speech-to-text for audio evidence

Audio evidence (call recordings, voicemails, interviews, dictation) is
privileged and sensitive. **Transcribe locally only — never upload it
to a cloud transcription service.** The pipelines below run entirely
on-machine. Where a setup step downloads something from the internet,
it downloads *models*; the audio never leaves the machine.

Two pipelines, chosen by how many voices matter:

- **Single voice** (dictation, voicemail, one-sided recording):
  `whisper-cpp`. Fast, simple, no diarization.
- **Multiple voices where WHO said WHAT matters** (client interviews,
  witness calls, hearings): WhisperX with pyannote speaker
  diarization.

## Single-voice pipeline: whisper-cpp

### Setup

Install `whisper-cpp` (e.g. via Homebrew; Metal-accelerated on macOS,
fully offline). Download a model, e.g. Whisper medium.en:

```bash
curl -L -o ~/.local/share/whisper-models/ggml-medium.en.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.en.bin
```

### Usage

`whisper-cli` wants 16 kHz mono WAV; convert with ffmpeg first:

```bash
ffmpeg -i recording.mp3 -ar 16000 -ac 1 -c:a pcm_s16le /tmp/stt.wav
whisper-cli -m ~/.local/share/whisper-models/ggml-medium.en.bin \
  -f /tmp/stt.wav -otxt -osrt -of output_basename
```

Note that Whisper does not diarize: any speaker labels in the cleaned
transcript are inferred by the reviewing human/agent and must be
marked as inferred.

## Multi-voice pipeline: WhisperX + pyannote

For any recording with two or more speakers where attribution
matters, use WhisperX (Whisper transcription + pyannote speaker
diarization) instead of plain whisper-cpp.

### One-time setup

```bash
conda create -n whisperx python=3.11 -y && conda activate whisperx
pip install whisperx
# Free HuggingFace account; create a read token at
# hf.co/settings/tokens, then accept the click-through license on
# BOTH model pages:
#   https://hf.co/pyannote/segmentation-3.0
#   https://hf.co/pyannote/speaker-diarization-3.1
export HF_TOKEN=hf_...          # put in ~/.zshrc or pass per-run
```

### Per recording

```bash
conda activate whisperx
whisperx recording.m4a \
  --model medium.en --compute_type int8 \
  --diarize --min_speakers 2 --max_speakers 2 \
  --hf_token $HF_TOKEN \
  --output_format all --output_dir ./transcript
```

Set `--min/--max_speakers` to the true count if known — tighter
bounds give better labels. Output includes `[SPEAKER_00]`-style
labels with timestamps (.txt/.srt/.json).

### Recording protocol at capture time

These matter more than the software:

- Quiet room; one mic/phone roughly equidistant between speakers.
- Open the recording with each participant saying their own name in
  a full sentence ("This is Jane Roe, today is ..."). This anchors
  the SPEAKER_NN → name mapping.
- Don't talk over each other; overlapping speech is the main thing
  that breaks diarization. Leave a half-beat between turns.

### Post-processing

In addition to the general sidecar conventions below:

- Map `SPEAKER_00/01` → real names using the opening introductions;
  produce the final sidecar `.txt` with `NAME:` turns. State in the
  provenance header that diarization was machine-generated
  (WhisperX + pyannote model version) and that the name mapping was
  done by the reviewing human/agent.
- Keep the raw diarized machine output (.srt or .json, unedited)
  alongside the cleaned transcript.
- Spot-check speaker attribution at several points before relying on
  it — diarizers swap labels after cross-talk, and a misattributed
  quote in a declaration is worse than no quote.

### Fallback if pyannote gating is unavailable

Record speakers on separate channels (two devices, or a stereo
recorder with two lav mics). Then channel = speaker, and either
`whisper-cli --diarize` on the stereo file suffices, or transcribe
each channel separately.

## Transcript sidecar conventions

For transcripts of evidence audio, regardless of pipeline:

- Save a speaker-attributed transcript as a same-named `.txt` sidecar
  next to the audio asset, opening with a provenance header: source
  file and origin, generation date, tool + model, and the banner
  "MACHINE TRANSCRIPT — VERIFY AGAINST AUDIO BEFORE CITING IN ANY
  FILING."
- Keep the raw machine output as a same-named `.srt` (timestamps,
  unedited) alongside.
- Speaker labels are inferred by the reviewing human/agent and must
  be marked as inferred. Mark uncertain words with [likely "..."] and
  editorial notes in brackets.
- Example layout:
  `assets/calls/advisor_call_recording_jun23.{mp3,txt,srt}` — audio,
  cleaned attributed transcript, and raw timestamped output side by
  side.
