# Physical Chess Camera → Timed PGN

## Rev. 35 (Main Menu Update)

Chess Camera records a normal physical chess game from one fixed camera and saves the moves as PGN. It can also record remaining clock time from either Lichess OCR or the built-in chess clock.

Revision 35 is the main version of the project.

## Main menu

The app opens on a scalable feature grid instead of immediately entering calibration or game setup.

Current feature cards:

- **Start OTB Game**
- **Game History**
- **Chess960 Generator**
- **Opening Explorer**
- **Settings**
- A reserved card for future features
- **Exit**

The grid can be expanded or rearranged as new tools are added.

## Chess960 generator

The Chess960 generator creates one of the 960 legal starting positions and shows:

- The position number
- The full starting board
- The White back-rank order
- The FEN
- Generate Another and Copy FEN controls

It uses the same virtual-board and piece renderer as live play and Stockfish analysis.

## Opening Explorer

Opening Explorer uses the `python-chess` Polyglot opening-book integration through `chess.polyglot`.

Choose a local Polyglot `.bin` book, then click one of the displayed weighted moves to continue exploring the position. The explorer includes:

- The same virtual-board and piece renderer used elsewhere in the app
- Weighted book moves and percentages
- Clickable move selection
- Back Move
- Reset
- Current FEN
- A saved opening-book path in `camera_config.json`

You can place a `.bin` file inside `books/` for automatic detection, or choose one from another folder. No opening-book database is bundled with Chess Camera.

## Starting a recorded game

The first Recorded OTB Game after each app launch requires a fresh board calibration. This prevents an old calibration from being reused after the board or camera has moved.

Additional games and rematches during the same app session reuse the current calibration. You can still manually select **Recalibrate board** at any time.

After calibration, the game-setup page lets you configure:

- White and Black player names
- Event name
- Lichess OCR or built-in clock
- Shared or separate time controls
- Normal, Fast, or Bullet detection
- Manual or automatic confirmation
- Camera orientation
- Board profiles and guided move training
- Accuracy Boost

When a player or event text box is selected, an **X** appears inside that active field to clear it.

Press **Back** or **Esc** on the initial setup page to return to the main menu.

## Board profiles

Use **Board options** to open a separate menu containing:

- **Rename preset**
- **Reset training**
- **Close**

The Board Options window can be closed with its Close button, Escape, or the window’s X. Creating a new board profile asks for its name.

## Game history

Game History lists recorded games and can display:

- White and Black players
- Result
- How the game ended
- Number of moves
- Time control
- Date
- Event
- White and Black accuracy after analysis

The selected game can be:

- Reviewed with Stockfish
- Copied to the clipboard as PGN
- Deleted after a confirmation popup

Deleting a game also removes its matching saved analysis files when available.

## Post-game flow

After a completed game is saved, choose:

- **Rematch** — keeps both player names, the event, and the time control, then returns to game setup so they can still be edited.
- **Main Menu** — returns to the Revision 35 home screen.

## Stockfish analysis

Open **Settings** from the main menu and choose a trusted UCI-compatible engine executable, such as Stockfish.

The review screen includes:

- White and Black accuracy
- Average centipawn loss
- Move classifications
- Stockfish’s suggested move
- A clickable and scrollable move list
- A left-side evaluation bar

Stockfish is not bundled with this repository.

## Launching the app

### Windows

Double-click:

```text
run_windows.bat
```

Or use:

```text
run_revision35_windows.bat
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

The launchers create a local `.venv` environment and install the required Python packages on the first launch.

## Calibration guidance

For board calibration, click the exact four corners of the 8×8 playing grid in this order:

1. Image top-left
2. Image top-right
3. Image bottom-right
4. Image bottom-left

Keep visible space around every board edge. The app adds an exterior detection margin automatically to help recognize tall pieces near the first rank, eighth rank, and outside files when the camera is angled.

For phone calibration, click the lit screen edges rather than the phone case.

## Saved local data

The app stores data locally in files and folders such as:

- `camera_config.json`
- `board_profiles/`
- `books/`
- `games/`

Camera video is not uploaded or saved by the learning system.

## Compatibility

Revision 35 keeps the existing camera detection, clock handling, move correction, PGN export, board learning, and Stockfish review features developed in earlier revisions.

Older revision details remain available in the repository’s Git history.
