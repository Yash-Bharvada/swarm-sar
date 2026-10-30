# SWARM SAR — The Fieldbook

A separate static learning website for the existing Swarm SAR project. It does
not change the simulator, training configuration, checkpoint or application.

The edition has 74 reader pages across 16 chapters, 12,174 words, original
project captures, interactive teaching diagrams, twelve hackathon question
cards and a searchable inventory of all 421 tracked files in the reviewed
project snapshot. It includes 74 English audio tracks, a complete chaptered
M4B, an illustrated PDF, transcript and downloadable file atlas.

Narration is synthetic English speech (Samantha, macOS system TTS). The static
audio files play without relying on browser speech synthesis. Audio playback
supports speed, seeking, 15-second jumps, page completion/automatic turns and
media session controls. Reading position, bookmarks and preferences remain in
browser local storage. No server or account is required by the reader itself.

## Run locally

From this directory:

```sh
python3 scripts/serve.py
```

Open http://127.0.0.1:8088. This server supports HTTP byte ranges for audio seeking. The reader fetches `book.json`, so serve it over HTTP
rather than opening `index.html` with a file URL.

## Rebuild the manuscript and inventory

From the parent project root:

```sh
.venv/bin/python guide-site/scripts/build_book.py
.venv/bin/python guide-site/scripts/generate_audio.py
.venv/bin/python guide-site/scripts/build_print.py
```

`build_book.py` reads the original project Git inventory, copies readable text
into `dist/source/`, catalogs binaries without executing or embedding them,
and preserves original screenshot/GIF assets. Rebuilding requires the original
parent repository. `generate_audio.py` requires macOS `say`, Samantha and
Homebrew FFmpeg; it reuses unchanged audio tracks using narration hashes.

The checked-in `dist/` is ready to serve independently. It needs no npm install
or build. `scripts/qa_book.py` checks the reader in installed Google Chrome,
creates the complete PDF, and records browser/integrity verification.

## Editorial scope

Reviewed project source: `83cd96ce7a5651ee77f5816a7ab47844bc0cbf7a`.
Edition: 30 October 2026. Team: Om Rashiya, Yash Bharvada, Purva Shah, Pankti Akbari.

The manuscript distinguishes browser heuristics, Python PPO execution and the
separate ROS physics demo. It describes the checked-in learner as cooperative
type-shared PPO, not standard centralized-critic MAPPO. All benchmark numbers
retain development/historical scope. Supplied ROS captures retain their
host-policy provenance limitation. No individual team roles are invented.
