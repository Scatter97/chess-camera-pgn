# Chess Camera

**Current release: 0.36.1**

Chess Camera watches a normal physical chess game through one fixed camera, records legal moves, tracks clock information, and saves the result as a PGN file. It also includes local game history, Stockfish review, a Chess960 starting-position generator, and an opening explorer that supports both a built-in book and user-selected Polyglot books.

The app is designed for Windows, Ubuntu/Linux, and macOS. Camera processing, saved games, board training, opening books, and engine analysis remain on the local computer.

## Main features

- Record over-the-board chess games from a camera.
- Save legal moves, player names, event information, results, and clock times as PGN.
- Use Lichess clock OCR or the configurable built-in chess clock.
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

For the first recorded game after each app launch, Chess Camera asks for fresh board calibration. This prevents a saved calibration from being reused after the camera or board has moved.

Click the exact four corners of the 8×8 playing grid in this order:

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

Select the White, Black, or Event text field to show an **X** inside the active field. Click it to clear that field.

Use the compact two-arrow button to swap the White and Black player names. This changes the PGN player assignment only; it does not change camera orientation or clock mapping.

Press **Back** or **Esc** on the initial setup page to return to the main menu.

### 3. Play and save

Click **Start Game** after the setup is complete. The match screen shows:

- The live virtual board
- Player names
- Clock information
- Recorded move list
- Detection status
- A separate board-stability strip above the camera preview
- Controls for corrections, clock adjustments, draw claims, resignations, and game completion

When the game finishes, Chess Camera saves the PGN in `games/` and offers:

- **Rematch** — keeps the players, event, and time control while allowing edits before the next game
- **Main Menu** — returns to the feature grid

## Camera orientation and edge detection

The camera does not need to be positioned behind White. In game setup, choose where White appears in the image:

- Bottom
- Top
- Left
- Right

Chess Camera rotates the corrected camera image internally so chess coordinates and the virtual board stay consistent.

The corrected board includes an exterior detection margin around the 8×8 grid. This provides extra visual evidence for tall pieces near the first rank, eighth rank, `a`-file, and `h`-file when the camera is angled.

Keep some visible table around every side of the physical board. The margin cannot recover a piece top that is already outside the original camera frame.

Use **Check all 64 squares** before playing. Confirm that the labeled grid follows the physical square boundaries and that the orientation is correct.

## Detection modes

### Normal

Uses the longest stability delay and is intended for the most reliable general recording.

### Fast

Uses a shorter stability delay for quicker games while keeping more checking than Bullet mode.

### Bullet (Beta)

Uses the shortest delay and is experimental. It is more sensitive to camera movement, hands, reflections, and unusual pieces.

The green stability bar above the camera image is a stillness timer, not an accuracy score. It fills while the board remains stable and resets when movement is detected.

## Accuracy Boost

Accuracy Boost compares three stable full-resolution frames and requires agreement before accepting a move. It can:

- Correct small camera shifts
- Compensate for whole-frame brightness changes
- Use a median frame as the next reference
- Retry silently when readings disagree

Accuracy Boost is intended for Normal and Fast modes and is disabled in Bullet mode.

## Automatic detection correction

When automatic confirmation records the wrong legal move, use **Detection wrong** before another move is recorded.

Chess Camera can:

1. Remove the incorrect move from the virtual board and PGN
2. Preserve the recorded move time and clock switch
3. Show alternative legal candidates
4. Record the selected correction with stronger positive training
5. Save the rejected signature as negative feedback
6. Return to automatic confirmation for the next move

The correction control is available only for the latest automatically accepted move.

## Illegal-move recovery

When the camera detects an illegal physical position, the warning pauses the built-in clock. Restore the pieces to the last recorded legal position and leave the board still.

The warning normally closes automatically after the restored position is recognized. A clickable **Dismiss warning** control is also available when camera noise prevents automatic recovery.

Only dismiss the warning after restoring the physical position. Dismissing it while the board still shows an illegal arrangement would make that arrangement the new camera reference.

## Clock options

### Lichess OCR

Chess Camera reads the two clock displays from a phone running a Lichess clock. OCR is read-only; Lichess remains responsible for its clock and flag behavior.

### Built-in clock

The built-in clock supports:

- Shared or separate player time controls
- Starting minutes and increments
- Pinned presets such as 1+0, 3+0, 3+2, 5+0, 10+0, and 15+10
- Camera-controlled or keyboard-controlled clock switching
- Midgame clock adjustment
- Automatic timeout results

When a built-in clock reaches `0:00`, the app stops both clocks, identifies the player who flagged, saves the appropriate result, and prevents additional moves.

During a built-in-clock game, **Adjust clocks** pauses play and lets White and Black receive independent minute or second changes. Confirm to save the new times or cancel to discard them.

## Board profiles and guided training

Each board profile can store its own:

- Board calibration
- Phone calibration
- Camera orientation
- Clock-side mapping
- Learned move signatures
- Per-square camera-noise measurements

Use separate profiles for different physical boards, piece sets, camera positions, or lighting arrangements.

Creating a new board asks for the board name. Use **Board options** for:

- **Rename preset**
- **Reset training**
- **Close**

Resetting training clears learned positive examples, negative feedback, and camera-noise learning for that profile while preserving its calibration and orientation settings.

Guided training requests specific legal moves from a known starting position. Record each requested move after removing your hand from the board. Manually confirmed moves during ordinary games can also improve the active profile.

Training data is stored as compact local JSON measurements. Camera video is not uploaded or saved by the learning system.

## Game History

Game History displays saved recorded games with information such as:

- White and Black players
- Result
- How the game ended
- Number of moves
- Time control
- Date
- Event
- White and Black accuracy after analysis

Available actions include:

- **Review with Stockfish**
- **Copy PGN**
- **Delete** with confirmation

Deleting a game also removes matching saved analysis files when available.

## Stockfish and UCI analysis

Stockfish is optional and is not bundled with this repository.

Open **Settings** and choose a trusted UCI-compatible engine executable. Chess Camera validates the selected engine, saves its path in `camera_config.json`, and reuses it for future reviews.

The review screen includes:

- Estimated White and Black accuracy
- Average centipawn loss for each player
- Move classifications
- Engine evaluation for each move
- Stockfish's suggested move
- A green suggested-move arrow
- A clickable and scrollable move list
- A left-side evaluation bar with signed White-perspective values
- A virtual board that follows the selected move

Analysis runs locally after the game and does not consume engine processing time during camera recording.

### Installing Stockfish

Download Stockfish from its official website, extract it, then select the executable through **Settings → Choose Engine File**.

Alternative detection methods remain available:

- Put a Stockfish executable in an `engines/` folder
- Add the `stockfish` command to the system PATH
- Pass an engine path through the command line

Examples:

```text
run_windows.bat --engine "C:\path\to\stockfish.exe"
./run_ubuntu.sh --engine "/path/to/stockfish"
./run_mac.command --engine "/path/to/stockfish"
```

On Ubuntu or macOS, a manually downloaded engine may need executable permission:

```bash
chmod +x /path/to/stockfish
```

## Chess960 Generator

The Chess960 Generator creates one of the 960 legal starting positions and shows:

- The Chess960 position number
- The full starting board
- The White back-rank order
- The FEN
- **Generate Another**
- **Copy FEN**
- **Back**

Press Space or `R` to generate another position. The generator uses the same virtual-board and piece renderer as live play and Stockfish analysis.

## Opening Explorer

Opening Explorer uses `python-chess` Polyglot support through `chess.polyglot`.

It includes:

- A built-in CC0-derived opening source
- Automatic generation of `books/chess_camera_default.bin`
- **Choose Book...** for another Polyglot `.bin` file
- **Use Built-in** to switch back
- Automatic fallback when a selected custom book is missing
- Weighted move counts and percentages
- Clickable book moves
- Back Move
- Reset
- Current FEN
- The same board and piece renderer used elsewhere in the app

The selected book mode and custom path are stored in `camera_config.json`.

The included source in `books/default_openings.tsv` is derived from the `lichess-org/chess-openings` dataset, which is released under CC0. See `books/README.md` and `books/NOTICE.txt` for details.

Custom opening books are not copied into the repository. Only use and redistribute book files when their licenses permit it.

## Installation and launching

### Windows

1. Install Python and Git.
2. Clone the repository.
3. Double-click:

```text
run_windows.bat
```

The launcher creates `.venv`, installs `requirements.txt`, and starts `chess_camera.py`.

### Ubuntu/Linux

Install the required system packages:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-tk git
```

Then run:

```bash
git clone https://github.com/Scatter97/chess-camera-pgn.git
cd chess-camera-pgn
chmod +x run_ubuntu.sh
./run_ubuntu.sh
```

### macOS

Install Python 3.11 or 3.12 and Git, then run:

```bash
git clone https://github.com/Scatter97/chess-camera-pgn.git
cd chess-camera-pgn
chmod +x run_mac.command
./run_mac.command
```

The macOS launcher supports Intel and Apple Silicon through the installed Python and OpenCV packages.

## Updating an existing installation

From the repository folder:

```bash
git switch main
git pull --ff-only
```

Then launch the app normally.

## Local files and privacy

Chess Camera stores local settings and generated data in files and folders such as:

- `camera_config.json`
- `board_profiles/`
- `books/chess_camera_default.bin`
- `games/`
- `engines/`
- `.venv/`

These generated folders and local configuration files are excluded from Git where appropriate.

Camera processing happens locally. The app does not require uploading camera video, board training data, saved PGNs, or engine analysis to an online service.

## Project structure

Important current files include:

- `chess_camera.py` — main application entry point and feature menu
- `app.py` — camera recording, calibration, clocks, move tracking, and review UI
- `app_navigation.py` — settings, rematches, navigation state, clipboard, and engine selection
- `game_session.py` — consolidated setup UI and recorded-game session flow
- `game_history.py` — saved-game browser, deletion, and evaluation-bar placement
- `ui_support.py` — shared drawing, history loading, and profile-name support
- `chess960_generator.py` — Chess960 tool
- `opening_explorer.py` — built-in and custom Polyglot explorer
- `opening_book_builder.py` — Polyglot book generation
- `version.py` — current version
- `VERSIONING.md` — release-number rules
- `CHANGELOG.md` — release history

## Versioning

Chess Camera uses this release format:

- Major features and substantial updates: `0.xx`
- Small visual changes, cleanup, and bug fixes: `0.xx.xx`

Examples:

- `0.36` — built-in opening book and custom-book support
- `0.36.1` — module cleanup and restored detailed documentation
- `0.37` — next major feature release

See `VERSIONING.md` for the release checklist.

## Current limitations

- Physical camera behavior depends on lighting, camera position, board contrast, reflections, and piece shape.
- Bullet detection is experimental and may be less reliable.
- Lichess OCR quality depends on phone-screen visibility and glare.
- Stockfish analysis requires a separately installed UCI engine.
- Opening-book percentages represent the weights stored in the selected Polyglot book; they are not automatically global online-play statistics.
- Camera, OpenCV window, clipboard, OCR, engine, and physical-board behavior should be tested on the target computer after relevant changes.

## Release history

Older revision-era development details remain available in Git history. Current releases and user-facing changes are summarized in `CHANGELOG.md`.

## License

Copyright © 2026 Joshua Wang. All rights reserved.

No permission is granted to use, copy, modify, distribute, sublicense, sell, or create derivative works from this source code without prior written permission from the copyright holder.
