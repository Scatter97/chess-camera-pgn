# Knightboard

### Your offline chess studio

**Current release: 0.50.0**

Knightboard is a local-first chess client for recording, reviewing, exploring, and improving your games without an online account. Camera-based over-the-board recording is one part of the app: Knightboard also gives you a local game library, engine review, opening and endgame explorers, Chess960, bot games, board training, custom themes, sounds, and optional downloadable chess data.

The application is designed for Windows, Debian-based Linux distributions, and macOS. Camera processing, games, training data, engines, opening books, and tablebases remain on the local computer.

## What Knightboard does

- **Play:** start Virtual Bot Games, OTB Bot Games, Chess960 positions, or record a physical game through a camera.
- **Record:** recognize legal over-the-board moves, optionally read clocks, and save complete PGNs locally.
- **Review:** analyse saved games with a local UCI engine, evaluation bars, suggested moves, accuracy, classifications, and centipawn loss.
- **Explore:** use local opening books and Syzygy endgame tablebases; no positions are sent online.
- **Personalise:** save board profiles, train detection, choose piece/sound packs, and manage local chess libraries.

## Feature details

- Record physical chess games from a camera and save legal PGN moves.
- Use Lichess clock OCR or the configurable built-in chess clock.
- Use Normal, Fast, Bullet, Accuracy Boost, and optional 64-square local detection.
- Configure a confidence threshold for automatic move approval.
- Correct a legal move mistaken for an illegal position.
- Manually synchronize the virtual board through one or more legal moves.
- Save board profiles and improve recognition with guided training.
- Review games with a separately installed Stockfish or another UCI engine.
- Browse game history, copy PGNs, and delete saved games with confirmation.
- Generate Chess960 starting positions.
- Explore built-in, downloaded, or custom Polyglot opening books.
- Explore downloaded or custom local Syzygy tablebases.
- Download optional opening and endgame libraries after installation.
- Use bundled or custom piece and sound packs.

## Knightboard home

- **Record OTB Game**
- **Game History**
- **Chess960 Generator**
- **Opening Explorer**
- **Endgame Explorer**
- **Settings & Libraries**
- **Virtual Bot Game**
- **OTB Bot Game**
- **Exit**

The displayed version is read from `chess_camera_app/core/version.py`.

## Project layout

The root contains the launcher, packaging files, documentation, tests, and
build scripts. Application code is grouped in `chess_camera_app/`:

```text
chess_camera_app/
├── analysis/       Stockfish, opening, endgame, and Chess960 tools
├── calibration/    Board and camera calibration
├── content/        Downloadable opening and tablebase data
├── core/           App state, navigation, and version information
├── detection/      Camera, OCR, Local64, and square detection
├── game/           PGN, clocks, rules, corrections, and recovery
├── runtime/        Runtime patching and user-data paths
└── ui/             Setup, settings, history, and visual themes
```

Run the app exactly as before with `python chess_camera.py`.

## Recording workflow

### 1. Calibrate

For the first recorded game after each launch, click the four board corners in this order:

1. Image top-left
2. Image top-right
3. Image bottom-right
4. Image bottom-left

When clock OCR is enabled, also calibrate the visible phone or clock display. Later games in the same session can reuse the current calibration.

### 2. Configure

Game setup includes player names, event name, clock source, time controls, detection mode, camera orientation, board profile, learning, calibration tools, Accuracy Boost, and move-confirmation behavior.

### 3. Play and save

The game screen shows the virtual board, player names, clocks, recorded moves, detection status, camera preview, stability information, and controls for correction, board synchronization, clocks, draws, resignation, and game completion.

Games are saved under `games/` as `latest_game.pgn` and timestamped PGN files.

## Detection and correction

### Detection modes

- **Normal** uses the longest stability delay.
- **Fast** reduces the delay while keeping normal validation.
- **Bullet (Beta)** uses the shortest delay and is more sensitive to hands, lighting, reflections, and camera movement.
- **Accuracy Boost** compares multiple stable frames before accepting a move.
- **64-Square Local Detection (Beta)** analyzes local square regions and can ignore unrelated movement or broad occlusion.

### Confidence auto-approval

Open **Settings → Advanced Detection** to enable confidence-based approval and choose a threshold from 50% to 99%. Moves below the threshold remain available for manual confirmation.

### Detection wrong

Use **Detection wrong** immediately after an incorrect automatic legal move. The app removes the move, restores its training state, records rejection evidence when enabled, and presents alternatives.

### Illegal-move recovery

When no legal move explains the physical position, the built-in clock pauses. The player can restore the previous position or open **Move Was Legal – Fix Board**, drag the virtual board to exactly one legal move, validate it, update the PGN, and resume the correct clock.

### Manual board synchronization

Use **Edit Virtual Board** to add one or more legal moves when the physical and virtual boards no longer match. The editor supports save, undo, reset, and cancel. Saved moves update the PGN and reset the camera reference.

## Data and Libraries

Open:

```text
Settings
└── Data and Libraries
```

The manager installs optional datasets after the app is installed, so large files are not included in every installer.

It supports:

- Resumable downloads using `.part` files and HTTP Range requests
- Cancellation while preserving resumable data
- Configurable storage location
- Activate, verify, update, and remove controls
- Local package metadata and SHA-256 checksums
- Offline use after successful installation

### Expanded opening package

The optional opening package downloads the five ECO TSV files from `lichess-org/chess-openings` at pinned commit:

```text
51b886249b9e418498d25b6e39b926c3de99c29a
```

Each source file is checked against its pinned Git blob object ID before Knightboard converts the PGN lines into a local Polyglot book. The source dataset is CC0.

Opening Explorer can use:

- The included small book
- The downloaded expanded opening-name book
- A user-selected custom Polyglot `.bin` book

The generated weights describe how often position/move pairs occur in the imported theory lines. They are not live online win-rate statistics.

### Syzygy 3/4/5-piece package

The optional Syzygy package downloads standard 3/4/5-piece WDL and DTZ data from the Lichess tablebase mirror. It is approximately 939 MB and requires at least 1.25 GB of free storage before downloading.

Endgame Explorer can use:

- The downloaded 3/4/5-piece package
- A custom Syzygy folder, including larger six- or seven-piece collections

The downloaded package gives exact local results for covered positions with five or fewer pieces. No position is sent online.

The tablebase manager downloads through HTTPS, records a local SHA-256 checksum for every file, and verifies that `python-chess` can load the installed directory. The mirror does not provide a complete signed SHA-256 catalog through this downloader, so the initial local checksums detect later corruption or modification but are not claimed as independent source-hash verification.

Detailed architecture, storage, integrity notes, and the hands-on test checklist are in [`CONTENT_LIBRARY.md`](CONTENT_LIBRARY.md).

## Opening Explorer

Opening Explorer displays weighted legal book moves, allows moves to be played directly, and supports reset, back move, and current FEN. Buttons allow switching among built-in, downloaded, and custom books or opening Data Manager directly.

## Endgame Explorer

Endgame Explorer loads legal FEN positions, probes local Syzygy data, displays exact WDL and DTZ values, and provides clickable root moves. Positions with castling rights, invalid positions, unsupported piece counts, and uncovered material are reported safely.

## Game history and engine review

Game History shows players, result, finish reason, move count, time control, date, event, and available accuracy values.

The review screen can show estimated accuracy, average centipawn loss, classifications, engine evaluation, suggested moves and arrows, a clickable scrollable move list, evaluation bar, and the virtual position at each move.

Stockfish is not bundled. Select a trusted UCI engine executable through Settings.

## Clocks

### Lichess OCR

Clock OCR reads a calibrated phone or clock display. OCR is read-only and may leave a PGN clock value unknown when confidence is insufficient.

### Built-in clock

The built-in clock supports shared or asymmetric starting times, separate increments, presets, manual or camera-controlled switching, midgame adjustment, undo, correction pauses, and timeout results.

## Board profiles and training

Board profiles can store calibration, camera orientation, clock mapping, learned move signatures, rejected examples, and local camera-noise information.

Open **Settings → Advanced Board Training** to control learning, undo cleanup, rejected samples, and training reset. Training stores compact measurements rather than video.

## Appearance and sounds

Open **Settings → Board Appearance and Sounds**.

### Piece packs

The included **Classic Vector** pack is used on live, correction, synchronization, history, and review boards.

A custom pack under `piece_packs/<pack name>/` should contain:

```text
wK.png  wQ.png  wR.png  wB.png  wN.png  wP.png
bK.png  bQ.png  bR.png  bB.png  bN.png  bP.png
```

### Sound packs

Included packs:

- Classic Wood
- Soft Digital

A custom folder under `sound_packs/<pack name>/` may contain:

```text
move.wav
capture.wav
check.wav
castle.wav
promotion.wav
```

Only `move.wav` is required.

## Running from source

### Windows

```powershell
git clone https://github.com/Scatter97/knightboard.git
cd knightboard
run_windows.bat
```

### Ubuntu/Debian

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-tk git
git clone https://github.com/Scatter97/knightboard.git
cd knightboard
chmod +x run_ubuntu.sh
./run_ubuntu.sh
```

### macOS

```bash
git clone https://github.com/Scatter97/knightboard.git
cd knightboard
chmod +x run_mac.command
./run_mac.command
```

## Prebuilt desktop packages

GitHub Actions builds Windows, Debian, and macOS packages. Generated binaries are uploaded as workflow artifacts rather than committed.

Expected 0.50 outputs:

```text
Knightboard-0.50.0-Windows-x64.zip
knightboard_0.50.0_amd64.deb
Knightboard-0.50.0-macOS.dmg
Knightboard-0.50.0-macOS-app.zip
```

The macOS build is ad-hoc signed but not Apple-notarized.

## Building packages

### Windows

```text
build_windows_exe.bat
```

### Debian/Linux

```bash
chmod +x packaging/build_deb.sh
./packaging/build_deb.sh
```

### macOS

```bash
chmod +x packaging/build_macos.sh
./packaging/build_macos.sh
```

See `packaging/README.md` for package details.

## Data locations

Source checkouts store generated data in the repository folder. Packaged applications use:

- Windows: `%LOCALAPPDATA%\Knightboard`
- Debian/Linux: `${XDG_DATA_HOME:-~/.local/share}/knightboard`
- macOS: `~/Library/Application Support/Knightboard`

Knightboard automatically copies existing Chess Camera data into the new folder on first packaged launch without overwriting newer files. This preserves saved games, board profiles, engines, piece packs, sound packs, and downloaded libraries.

The default optional library is under `content_library/` inside that location. Data Manager can point optional libraries to another drive; changing the location does not automatically move existing downloads.

## Important files

- `chess_camera.py` — application entry point and Knightboard home
- `chess_camera_app/core/app.py` — camera game loop, clocks, move confirmation, and PGN recording
- `chess_camera_app/detection/` — square changes, camera input, OCR, and Local64 detection
- `chess_camera_app/content/` — package storage, downloads, and the Data and Libraries interface
- `chess_camera_app/analysis/` — Polyglot conversion, opening/endgame tools, and UCI-engine review
- `chess_camera_app/runtime/` — runtime patches and writable package data folders
- `chess_camera_app/ui/` — advanced settings, history, and visual presentation
- `chess_camera_app/game/` — PGN tracking, clocks, corrections, and synchronization
- `chess_camera_app/core/version.py` — application version
- `CHANGELOG.md` — release history
- `CONTENT_LIBRARY.md` — optional data architecture and test plan
- `packaging/` — Windows, Debian, and macOS builds

## Current limitations

- Camera reliability depends on lighting, reflections, board contrast, camera angle, and piece shape.
- Bullet and 64-square detection remain experimental.
- OCR depends on phone-screen visibility and glare.
- Stockfish requires a separate UCI engine.
- Optional datasets require an internet connection for initial download.
- The approximately 939 MB tablebase download and graphical progress flow require hands-on testing.
- Changing the optional storage location does not move existing files automatically.
- The macOS package is not notarized.
- Camera, downloads, OpenCV windows, sound, custom packs, and physical synchronization should be tested on each target operating system before public release.

## License

Copyright © 2026 Joshua Wang. All rights reserved.

No permission is granted to use, copy, modify, distribute, sublicense, sell, or create derivative works from this source code without prior written permission from the copyright holder. Third-party datasets retain their own licenses and notices.
## Development with OpenHands

This repository can be developed using the OpenHands AI coding assistant. OpenHands can help you explore the codebase, run tests, make changes, and create pull requests directly from the command line.


