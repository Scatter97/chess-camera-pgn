# Physical Chess Camera → Timed PGN

## Chess Camera 0.36

Chess Camera records a physical chess game from one fixed camera and saves the moves as PGN. It can also record remaining clock time from Lichess OCR or the built-in chess clock.

Version `0.36` adds a built-in opening book while continuing to support user-selected Polyglot books.

## Main menu

The app opens on a scalable feature grid with:

- **Start OTB Game**
- **Game History**
- **Chess960 Generator**
- **Opening Explorer**
- **Settings**
- A reserved card for future features
- **Exit**

## Chess960 generator

The Chess960 generator creates one of the 960 legal starting positions and shows:

- The position number
- The full starting board
- The White back-rank order
- The FEN
- Generate Another and Copy FEN controls

It uses the same virtual-board and piece renderer as live play and Stockfish analysis.

## Opening Explorer

Opening Explorer uses `python-chess` through `chess.polyglot`.

Version `0.36` includes a small built-in opening-book source at:

```text
books/default_openings.tsv
```

When Opening Explorer is first opened, Chess Camera automatically generates this local Polyglot book:

```text
books/chess_camera_default.bin
```

The generated `.bin` file is ignored by Git because it can be recreated from the bundled source.

Opening Explorer supports:

- The included built-in book
- **Choose Book...** for another Polyglot `.bin` file
- **Use Built-in** to switch back
- Automatic fallback if a custom book is moved or deleted
- Weighted move percentages
- Clickable moves
- Back Move and Reset
- Current FEN
- The same board and piece renderer used elsewhere in the app

The selected mode and custom-book path are stored locally in `camera_config.json`.

The bundled opening lines were curated from the public-domain/CC0 `lichess-org/chess-openings` dataset. See `books/README.md` for source and rebuilding information.

## Building a larger default book

A build tool is included for generating a larger Polyglot book from a local clone of the full `lichess-org/chess-openings` dataset:

```powershell
.\.venv\Scripts\python.exe tools\build_default_book.py `
  vendor\lichess-openings `
  books\chess_camera_default.bin
```

The tool reads `a.tsv` through `e.tsv`, converts the PGN lines to UCI moves, and writes a weighted Polyglot book.

## Starting a recorded game

The first OTB game after each app launch requires a fresh board calibration. Additional games and rematches in the same session reuse the current calibration unless you manually choose **Recalibrate board**.

The game-setup page supports:

- White and Black player names
- Event name
- Lichess OCR or built-in clock
- Shared or separate time controls
- Normal, Fast, or Bullet detection
- Manual or automatic confirmation
- Camera orientation
- Board profiles and guided move training
- Accuracy Boost

When a player or event field is active, an **X** appears to clear it. Press **Back** or **Esc** on the initial setup page to return to the main menu.

## Board profiles

**Board options** contains:

- **Rename preset**
- **Reset training**
- **Close**

The window closes through its Close button, Escape, or the window X. Creating a new board profile asks for its name.

## Game history and Stockfish review

Game History can display players, result, ending method, move count, time control, date, event, and both accuracies after analysis.

A saved game can be:

- Reviewed with Stockfish
- Copied as PGN
- Deleted after confirmation

The Stockfish review includes accuracy, average centipawn loss, move classifications, suggested moves, a clickable move list, and a left-side evaluation bar.

Stockfish is not bundled. Choose a trusted UCI-compatible engine executable through **Settings**.

## Launching the app

### Windows

Double-click:

```text
run_windows.bat
```

### Ubuntu

```bash
chmod +x run_ubuntu.sh
./run_ubuntu.sh
```

### macOS

```bash
chmod +x run_mac.command
./run_mac.command
```

The launchers create a local `.venv`, install required packages on first launch, and start `chess_camera.py`.

The older `run_revision35_*` launchers remain as compatibility shortcuts and start the same current version.

## Versioning

- Major features and substantial updates use `0.xx`, such as `0.36` and `0.37`.
- Small visual changes and bug fixes use `0.xx.xx`, such as `0.36.1`.

`version.py` is the single source of truth. See `VERSIONING.md` and `CHANGELOG.md`.

## Saved local data

The app stores data locally in files and folders such as:

- `camera_config.json`
- `board_profiles/`
- `books/chess_camera_default.bin`
- `games/`

Camera video is not uploaded or saved by the learning system.

## Calibration guidance

For board calibration, click the exact four corners of the 8×8 playing grid in this order:

1. Image top-left
2. Image top-right
3. Image bottom-right
4. Image bottom-left

Keep visible space around every board edge. For phone calibration, click the lit screen edges rather than the phone case.
