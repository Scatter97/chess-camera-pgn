# Physical Chess Camera → Timed PGN

## Rev. 35 (Main Menu Update)

Chess Camera records a normal physical chess game from one fixed camera and saves the moves as PGN. It can also record remaining clock time from either Lichess OCR or the built-in chess clock.

Revision 35 is now the main version of the project.

## Main menu

The app now opens on a main menu instead of immediately entering calibration or game setup.

Available options:

- **Start Recorded OTB Game**
- **Game History**
- **Settings**
- **Exit**

The main page also leaves room for more features later.

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

Press **Back** or **Esc** on the initial setup page to return to the main menu.

## Board profiles

Use **Board options** to open a separate menu containing:

- **Rename preset**
- **Reset training**
- **Close**

Creating a new board profile asks for its name. Board profiles keep their own learning data, orientation, clock mapping, and other board-specific settings.

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
- `games/`

Camera video is not uploaded or saved by the learning system.

## Compatibility

Revision 35 keeps the existing camera detection, clock handling, move correction, PGN export, board learning, and Stockfish review features developed in earlier revisions.

Older revision details remain available in the repository’s Git history.
