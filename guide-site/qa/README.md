# Fieldbook verification

The final local browser run passed 178 checks in installed Google Chrome,
with no browser script errors. See `verification.json` for individual results.

Verified scope:

- All 74 reader pages fit desktop (1600 px) and mobile (390 px) viewports
  without horizontal overflow.
- Page buttons, keyboard navigation, contents, book search, empty states,
  bookmarks and reading-position persistence.
- Repository search and actual line-numbered source loading.
- Interactive reward, PPO clipping and packet-loss calculations.
- Real AAC narration playback, pause, speed changes and automatic page advance.
- Original screenshot loading and expanded image viewing.
- Every cited project path and readable source payload exists.
- Every page has a measured, nonzero audio track; the complete M4B has 74
  chapter markers and approximately 92.7 minutes of English synthetic speech.
- The complete illustrated PDF has 74 pages.

The largest static asset is the complete 32 kbps audiobook, below 25 MiB.
The local preview server supports HTTP byte ranges so audio seeking can be
tested correctly. A basic Python `http.server` lacks this support.

These checks validate the learning website. They do not rerun the original
project's model benchmarks or the ROS/Gazebo physics experiments. The book
retains those historical records with their original scope.

The screenshots here are captures of the working book website. Mission images
inside the book are original project captures copied from `docs/media/`.
