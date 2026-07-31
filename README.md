# Chess Camera

**Current test release: 0.39.7**

Chess Camera watches a normal physical chess game through one fixed camera, records legal moves, tracks clock information, and saves the result as a PGN file. It also includes local game history, Stockfish review, Chess960 generation, an opening explorer, board training, illegal-move correction, manual board synchronization, piece themes, and move sounds.

The app is designed for Windows, Debian-based Linux distributions, and macOS. Camera processing, saved games, board training, opening books, piece packs, sound packs, and engine analysis stay on the local computer.

## Main features

- Record over-the-board chess games from a camera.
- Save legal moves, player names, event information, results, and clock times as PGN.
- Use Lichess clock OCR or the configurable built-in chess clock.
- Use optional 64-Square Local Detection to ignore unrelated board movement.
- Set a confidence threshold for automatic move approval.
- Correct a legal move that was mistaken for an illegal position.
- Manually synchronize the virtual board with the physical board during a game.
- Restore yellow move highlights over the calibrated camera preview.
- Use the included Classic Vector piece set or custom transparent PNG piece packs.
- Use the included Classic Wood and Soft Digital sound packs or custom WAV packs.
- Review saved games with a local UCI engine such as Stockfish.
- Browse game history, copy PGNs, and delete games with confirmation.
- Generate any of the 960 legal Chess960 starting positions.
- Explore opening moves using the included CC0-derived book or another Polyglot `.bin` book.
- Save separate board profiles for different boards, pieces, camera positions, and lighting conditions.
- Improve recognition with guided move training and confirmed-move learning.

## Current main menu

Chess Camera opens on a scalable feature-card menu:

- **Start OTB Game**
- **Game History**
- **Chess960 Generator**
- **Opening Explorer**
- **Settings**
- A reserved card for future features
- **Exit**

The displayed version comes from `version.py`, which is the single source of truth for the app version.

## Three-step recording workflow

### 1. Calibrate

For the first recorded game after each app launch, Chess Camera asks for fresh board calibration. Click the exact four corners of the 8×8 playing grid in this order:

1. Image top-left
2. Image top-right
3. Image bottom-right
4. Image bottom-left

When Lichess OCR is used, also click the four visible corners of the phone screen. Click the lit display edges rather than the phone case.

Additional games and rematches in the same app session reuse the current calibration. Manual recalibration remains available from game setup.

### 2. Configure the game

The game-setup screen includes clickable controls for:

- White and Black player names
- Event name
- Lichess OCR or built-in clock
- Shared or separate starting times and increments
- Pinned time-control presets
- Normal, Fast, or Bullet detection
- Manual or automatic move confirmation
- Camera-controlled or player-controlled built-in clock switching
- Which OCR display belongs to White
- Camera placement on any side of the board
- Board and phone recalibration
- Optional three-frame Accuracy Boost
- A labeled 64-square calibration check
- Board profiles and guided move training
- Learning on or off

Use the compact two-arrow button to swap the White and Black player names. This changes the PGN player assignment only; it does not change camera orientation or clock mapping.

Press **Back** or **Esc** on the initial setup page to return to the main menu.

### 3. Play and save

Click **Start Game** after setup. The match screen shows:

- The live virtual board
- Player names
- Clock information
- Recorded move list
- Detection status
- Yellow origin and destination highlights over the camera preview
- A separate board-stability strip above the camera preview
- Controls for corrections, manual board synchronization, clock adjustments, draw claims, resignations, and game completion

When the game finishes, Chess Camera saves the PGN in `games/` and offers:

- **Rematch** — keeps the players, event, and time control while allowing edits before the next game
- **Main Menu** — returns to the feature grid

## Detection modes

### Normal

Uses the longest stability delay and is intended for reliable general recording.

### Fast

Uses a shorter stability delay for quicker games while keeping more checking than Bullet mode.

### Bullet (Beta)

Uses the shortest delay and is experimental. It is more sensitive to camera movement, hands, reflections, and unusual pieces.

The green stability bar above the camera image is a stillness timer, not an accuracy score.

## 64-Square Local Detection

Open **Settings → Experimental Features** and turn **64-SQUARE BETA** on or off.

The feature divides the calibrated board into 64 local regions. It can ignore moving or blocked regions that are unrelated to a complete legal move. Large dense changes, such as paper covering half the board, are treated as obstructions and are prevented from becoming fake moves.

Sensitivity choices:

- **Low** — strictest evidence requirements and strongest obstruction rejection
- **Normal** — balanced move detection and false-positive protection
- **High** — accepts weaker visual evidence but may be more affected by shadows or hands

## Confidence-based automatic approval

Open **Settings → Advanced Detection** to enable confidence-based auto-approval and choose a threshold from 50% to 99%.

- Legal moves at or above the selected confidence are accepted automatically.
- Lower-confidence moves remain available for manual approval.
- The advanced setting overrides the ordinary pregame Manual/Automatic choice while enabled.

## Accuracy Boost

Accuracy Boost compares three stable full-resolution frames and requires agreement before accepting a move. It can compensate for small camera shifts and brightness changes. Accuracy Boost is intended for Normal and Fast modes and is disabled in Bullet mode.

## Automatic detection correction

When automatic confirmation records the wrong legal move, use **Detection wrong** before another move is recorded.

Chess Camera can remove the incorrect move, preserve the recorded move time, show alternative candidates, save negative training feedback, and return to automatic confirmation for the following move.

## Illegal-move recovery

When the camera detects an illegal physical position, the warning pauses the built-in clock. The warning offers:

- **Restored – Resume** — use after physically restoring the last recorded position
- **Move Was Legal – Fix Board** — drag the virtual board to the actual legal position and continue

The correction editor validates exactly one legal move, updates the PGN, applies the correct clock switch and increment, and resumes the game.

## Manual virtual-board synchronization

Use **Edit Virtual Board** from the live game when the physical board and virtual board no longer match.

The editor pauses detection and the built-in clock. Drag one or more legal moves, then use:

- **Save Board Sync**
- **Undo Edit**
- **Reset**
- **Cancel**

Saving records the selected legal move sequence, updates the PGN and virtual position, refreshes the camera reference, and resumes the correct player’s clock.

## Piece themes and move sounds

Open **Settings → Board Appearance and Sounds** to select the piece pack, sound pack, sound status, and camera move highlights.

### Included piece pack

- **Classic Vector** — an original Staunton-inspired transparent PNG set

### Custom piece packs

Create a folder under `piece_packs/` containing these twelve transparent PNG files:

```text
wK.png  wQ.png  wR.png  wB.png  wN.png  wP.png
bK.png  bQ.png  bR.png  bB.png  bN.png  bP.png
```

Images around 128×128 pixels are recommended.

### Included sound packs

- **Classic Wood**
- **Soft Digital**

### Custom sound packs

Create a folder under `sound_packs/` containing WAV files named:

```text
move.wav
capture.wav
check.wav
castle.wav
promotion.wav
```

Only `move.wav` is required. Missing event sounds fall back to `move.wav`.

## Clock options

### Lichess OCR

Chess Camera reads the two displays from a phone running a Lichess clock. OCR is read-only; Lichess remains responsible for its clock and flag behavior.

### Built-in clock

The built-in clock supports shared or separate time controls, increments, pinned presets, camera-controlled or keyboard-controlled switching, midgame adjustments, and automatic timeout results.

## Board profiles and training

Each board profile can store:

- Board and phone calibration
- Camera orientation and clock-side mapping
- Learned move signatures
- Rejected detection examples
- Per-square camera-noise measurements

Use **Settings → Advanced Board Training** to manage learning, undo cleanup, rejected examples, sample counts, and training-data clearing.

Training data is stored as compact local JSON measurements. Camera video is not uploaded or saved by the learning system.

## Game History and Stockfish review

Game History displays the players, result, finish reason, move count, time control, date, event, and available accuracy information.

The review screen includes estimated accuracy, average centipawn loss, move classifications, engine evaluation, Stockfish’s suggested move, a suggested-move arrow, a clickable and scrollable move list, an evaluation bar, and a virtual board that follows the selected move.

Stockfish is optional and is not bundled. Open **Settings** and choose a trusted UCI-compatible engine executable.

## Chess960 Generator

The Chess960 Generator creates one of the 960 legal starting positions and shows the position number, board, back-rank order, FEN, and controls to generate another position or copy the FEN.

## Opening Explorer

Opening Explorer uses `python-chess` Polyglot support and includes a built-in CC0-derived opening source, automatic generation of `books/chess_camera_default.bin`, optional custom Polyglot books, weighted counts, clickable moves, reset, back move, and current FEN.

## Prebuilt desktop packages

The repository contains build definitions for three desktop package types. Generated binaries are uploaded as GitHub Actions artifacts rather than committed directly because PyInstaller dependencies are large and platform-specific.

Open the repository’s **Actions** tab, select **Build desktop installers**, open a successful run, and download the matching artifact.

### Windows EXE

Expected artifact:

```text
ChessCamera-0.39.7-Windows-x64.zip
```

After extracting it, launch:

```text
ChessCamera.exe
```

`ChessCamera.exe` must remain beside its `_internal` folder. The full portable folder is included in the ZIP.

### Debian/Ubuntu installer

Expected artifact:

```text
chess-camera_0.39.7_amd64.deb
```

Install it with:

```bash
sudo apt install ./chess-camera_0.39.7_amd64.deb
```

It installs the application under `/opt/chess-camera`, adds the `chess-camera` command, and creates an application-menu shortcut.

### macOS app and DMG

Expected artifacts:

```text
ChessCamera-0.39.7-macOS.dmg
ChessCamera-0.39.7-macOS-app.zip
```

The DMG contains:

```text
ChessCamera.app
Applications shortcut
```

The automated build is ad-hoc signed. Public distribution without Gatekeeper warnings requires an Apple Developer ID signature and Apple notarization.

## Building the packages yourself

### Windows

```text
build_windows_exe.bat
```

Outputs:

```text
dist\ChessCamera\ChessCamera.exe
release\ChessCamera-<version>-Windows-x64.zip
```

### Debian/Linux

```bash
chmod +x packaging/build_deb.sh
./packaging/build_deb.sh
```

Output:

```text
release/chess-camera_<version>_<architecture>.deb
```

### macOS

```bash
chmod +x packaging/build_macos.sh
./packaging/build_macos.sh
```

Outputs:

```text
dist/ChessCamera.app
release/ChessCamera-<version>-macOS.dmg
release/ChessCamera-<version>-macOS-app.zip
```

More details are in `packaging/README.md`.

## Running from source

### Windows

Install Python and Git, clone the repository, then double-click:

```text
run_windows.bat
```

### Ubuntu/Linux

```bash
sudo apt update
sudo apt install python3 python3-venv python3-tk git

git clone https://github.com/Scatter97/chess-camera-pgn.git
cd chess-camera-pgn
chmod +x run_ubuntu.sh
./run_ubuntu.sh
```

### macOS

```bash
git clone https://github.com/Scatter97/chess-camera-pgn.git
cd chess-camera-pgn
chmod +x run_mac.command
./run_mac.command
```

## Packaged data locations

Source checkouts keep generated data in the repository folder. Installed packages use writable user folders:

- Windows: `%LOCALAPPDATA%\ChessCamera`
- Debian/Linux: `${XDG_DATA_HOME:-~/.local/share}/chess-camera`
- macOS: `~/Library/Application Support/ChessCamera`

These locations contain settings, games, profiles, generated books, custom piece packs, custom sound packs, and optional engines.

## Project structure

Important files include:

- `chess_camera.py` — main application entry point and feature menu
- `app.py` — camera recording, calibration, clocks, move tracking, and review UI
- `runtime_app_patch.py` — 0.39 reliability state-machine patch used by source runs
- `runtime_paths.py` — writable data paths for packaged applications
- `feature_settings.py` — advanced detection, appearance, and sound settings
- `piece_theme_system.py` — piece-pack loading, bundled themes, and move sounds
- `manual_board_sync.py` — live legal-move board synchronization editor
- `app_navigation.py` — settings, rematches, navigation, clipboard, and engine selection
- `game_session.py` — consolidated setup and recorded-game session flow
- `game_history.py` — saved-game browser and review entry point
- `chess960_generator.py` — Chess960 tool
- `opening_explorer.py` — built-in and custom Polyglot explorer
- `version.py` — current version
- `CHANGELOG.md` — release history
- `build_windows_exe.bat` — Windows EXE/ZIP build
- `packaging/ChessCamera.spec` — shared PyInstaller definition
- `packaging/build_deb.sh` — Debian package build
- `packaging/build_macos.sh` — `ChessCamera.app` and DMG build
- `.github/workflows/build-installers.yml` — automated multi-platform package builds

## Current limitations

- Physical camera behavior depends on lighting, camera position, board contrast, reflections, and piece shape.
- Bullet and 64-square detection remain experimental.
- Lichess OCR quality depends on phone-screen visibility and glare.
- Stockfish analysis requires a separately installed UCI engine.
- The macOS Actions package is not Apple-notarized.
- Camera, OpenCV windows, audio, custom packs, and physical-board synchronization should be tested on each target operating system before public release.

## License

Copyright © 2026 Joshua Wang. All rights reserved.

No permission is granted to use, copy, modify, distribute, sublicense, sell, or create derivative works from this source code without prior written permission from the copyright holder.
