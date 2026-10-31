# SWARM SAR — The Fieldbook

A separate static learning website for the existing Swarm SAR project. It does
not change the simulator, training configuration, checkpoint or application.

The edition has 91 reader pages across 20 chapters, original
project captures, interactive teaching diagrams, fifteen hackathon question
cards and a searchable inventory of reviewed project files in the source snapshot (generated fieldbook outputs excluded). It includes 91 English audio tracks, a complete chaptered
M4B, an illustrated PDF, transcript and downloadable file atlas.

Narration is synthetic English speech (Samantha, macOS system TTS). The static
audio files play without relying on browser speech synthesis. Audio playback
supports speed, seeking, 15-second jumps, page completion/automatic turns and
media session controls. Reading position, bookmarks and preferences remain in
browser local storage. No server or account is required by the reader itself.

## Published audiobook

Public reader: https://swarmsar.vercel.app

Vercel project: `swarmsar`, scope: `rashiyaom-gmailcoms-projects`.
Deploy the existing static edition from the parent repository with:

```sh
vercel deploy guide-site/dist --project swarmsar --prod --yes
```

Deploy only `dist/`. There is no framework build or server dependency. The
production reader, recorded narration, audio byte-range seeking, search,
mobile layout and PDF/M4B downloads were checked on the public URL.
Deployment evidence: `artifacts/audiobook_vercel/validation.json` in the parent
repository. The manuscript records its reviewed source revision below.

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

Reviewed project source: see `dist/book.json` → `revision`; atlas entries include content hashes.
Edition: 31 October 2026. Team: Om Rashiya, Yash Bharvada, Purva Shah, Pankti Akbari.

The manuscript distinguishes browser heuristics, Python PPO execution, the original ROS physics demo, and the new rover SLAM source integration. Extended chapters explain map/intent sharing, the 3D observatory, frozen large-map experiments and one-command startup. Live Linux SLAM is still explicitly unverified. It describes the checked-in learner as cooperative
type-shared PPO, not standard centralized-critic MAPPO. All benchmark numbers
retain development/historical scope. Supplied ROS captures retain their
host-policy provenance limitation. No individual team roles are invented.
