# Physical Chess Camera → Timed PGN (Revision 12)

This Windows/laptop app watches a normal physical chess game and a Lichess
clock running on a phone through one fixed camera. It saves the moves and each
player's remaining time as a PGN file. The clock can come from Lichess OCR or
from a configurable clock built into the app.

## Three-step workflow

Revision 9 changes startup into a guided process:

1. **Calibration:** Click the four board corners, then the four phone-screen
   corners. Saved calibration is reused on later launches.
2. **Game settings:** Enter the White player, Black player, and event names.
   Choose all game options with clickable buttons.
3. **Play:** Click **Start Game**. The match screen opens with the virtual board,
   clocks, player names, move list, and controls.

The game-settings screen contains clickable choices for:

- Lichess OCR or the built-in clock;
- Normal or Bullet detection;
- manual or automatic move confirmation;
- which OCR clock display belongs to White;
- separate starting times and increments for White and Black;
- camera-controlled or player-controlled built-in clock switching;
- board or phone recalibration.

Player and event names are included in the saved PGN headers.

## Automatic or manual built-in clock switching

Revision 12 adds a **Clock switch** choice to the pre-game settings when the
built-in clock is selected:

- **Camera automatic:** the camera stops the player’s clock when the move is
  detected and accepted. This is the original behavior.
- **Player button:** the match screen shows **End White Turn** or
  **End Black Turn**. The player clicks it after completing the physical move.
  Their clock stops immediately, their increment is added, and the opponent’s
  clock starts.

In Player button mode, the camera move cannot be accepted until the correct
player has pressed the clock button. If automatic confirmation or Bullet Mode
is active and the camera already has a move waiting, pressing the clock button
also accepts that move. If the clock was pressed accidentally before the move
was accepted, click **Undo** to cancel that clock press.

This setting only affects the built-in clock. Lichess OCR continues to read the
phone clock, which the players operate on the phone itself.

## Match-screen layout

The virtual chessboard is now the largest part of the match screen. A separate
panel gives the player names, large clocks, current turn, recent moves, and
status messages. The corrected camera footage is kept as a small 300×300
diagnostic preview.

The match screen has clickable buttons for accepting or cycling through move
candidates, choosing a promotion piece, undoing, opening a new game's settings,
offering a draw, resigning, and finishing/saving. Keyboard shortcuts remain
available as backups.

## Game endings and draw rules

Revision 11 detects and records completed-game results:

- **Checkmate:** a popup says whether White or Black won.
- **Stalemate:** an automatic draw popup appears.
- **Insufficient material:** an automatic draw popup appears.
- **Threefold repetition:** White and Black are asked separately whether they
  agree to a draw. Both must select Yes.
- **Fivefold repetition:** the game is declared an automatic draw.
- **50-move rule:** White and Black are asked separately whether they agree to
  a draw. Both must select Yes.
- **75-move rule:** the game is declared an automatic draw.

The built-in clock pauses while a draw or resignation confirmation is open.
The **Offer draw** button asks the opponent to accept or decline. The
**Resign** button asks the player whose turn it is to confirm, then awards the
win to the opponent. The final `1-0`, `0-1`, or `1/2-1/2` result is saved in
the PGN.

It is designed for a camera beside the table, looking down at the board and
phone at roughly 45°. Four clicked board corners create a square top-down board.
Four clicked phone-screen corners separately correct the phone's perspective.
The phone may stand vertically beside the board with the clock text sideways.

## How it works

The first version does **not** need to identify the design of every chess piece.
It compares the board before and after each move, measures which squares
changed, and matches those squares against the moves that are legal in the
current position.

This means:

- the game must start from the normal chess starting position;
- the camera and board must not move during the game;
- the entire board must stay visible;
- a player should remove their hand after completing each move;
- move confirmation is manual by default for reliability.

Castling, captures, en passant, checks, checkmates, and promotion are supported.
For promotion, the camera cannot see which new piece was selected from square
changes alone. Revision 10 automatically opens a promotion popup with clickable
Queen, Rook, Bishop, and Knight choices. Press Enter to choose Queen by
default. The match-screen promotion buttons and Q/R/B/N shortcuts remain
available if the selection needs to be corrected before accepting the move.

## Lichess phone-clock recognition

Revision 3 reads the two large Lichess clock displays. It removes the center
control strip, rotates each sideways player display, and runs local OCR on the
digits. Clock recognition happens on the laptop; it does not upload camera
frames.

When a move is accepted, the stopped time for the player who just moved is
written in standard PGN clock form:

```pgn
1. e4 {[%clk 0:00:59]} e5 {[%clk 0:00:57]}
```

The app displays each recognized clock and OCR confidence. A reading below 70%
confidence is omitted instead of guessed. The move itself is still saved.

The default mapping assumes the phone half nearest White is the bottom clock.
Press `F` if the displayed White and Black clocks are reversed.

## Lichess OCR or built-in clock

Revision 8 added a clock-source choice. Lichess OCR remains the default. In
Revision 9, select the source and configure it on the clickable pre-game screen.
White and Black each have their own:

- starting minutes and seconds;
- Fischer increment, from 0 to 60 seconds per move.

The starting times and increments may be different. For example, White can
start with `3:00 + 2` while Black starts with `5:00 + 0`.

After selecting or configuring the clock, click **Start Game** to reset the
position and start White's clock. The app charges time until the camera detects that the
move is complete, then adds that player's increment and starts the opponent's
clock. The resulting time is written to the same standard `[%clk ...]` PGN tag
used by OCR.

Clock source, detection, confirmation, player information, and time controls
are all pre-game settings. Click **New game** to return to that screen. Undo
restores the clock to the moment before the removed move and resumes the correct
player.

### Non-blocking clock processing

Revision 5 runs OCR on a dedicated background worker. Clock recognition no
longer pauses the camera preview, board analysis, illegal-move warning, or
controls.

Each accepted move submits a copy of that exact camera frame as a prioritized
clock job. The result is linked back to that move with an internal token before
the PGN is updated. Optional preview readings are skipped whenever the OCR
worker is busy, so they cannot build an unnecessary queue.

On the development benchmark, board analysis took about 20 ms while reading
both clocks took about 1.1 seconds. Revision 5 allows those operations to run at
the same time. The camera interface can therefore remain responsive while the
clock tag appears shortly afterward.

## Optional Bullet Mode

Revision 6 adds a lower-latency mode for games with moves around one second
apart. Normal accuracy mode remains the default every time the app starts.

Press `B` before the game to enable Bullet Mode. Press it again before starting
to return to normal mode. The app displays an orange **BULLET - LOWER ACCURACY**
indicator while it is active.

Bullet Mode:

- detects the Lichess active side changing as an extra move boundary;
- waits about 0.12 seconds after the clock switch before reading the board;
- falls back to a 0.22-second board-stability window if the clock colors cannot
  be detected;
- automatically records the best legal match;
- reduces the post-move cooldown to 0.18 seconds;
- keeps clock OCR in the background.

Mode changes are blocked after moves have been recorded so one PGN cannot
silently mix two detection strategies. Press `S` to begin a fresh game before
changing modes.

Bullet Mode can handle much faster play, but hands, shadows, glare, or pieces
hiding squares are more likely to cause an incorrect match. Normal mode is
recommended whenever speed is not essential.

## Live virtual chessboard

Revision 7 adds a virtual board beside the corrected camera view. It is driven
by the same legal game state used to create the PGN, so it updates after every
accepted move rather than trying to redraw directly from a noisy camera frame.

The virtual board:

- keeps White at the bottom;
- displays all recorded pieces and positions;
- highlights the origin and destination of the latest move;
- shows whose turn it is;
- highlights check, checkmate, and stalemate states;
- returns to the previous position when `U` undoes a move;
- resets to the standard position when `S` starts a new game.

Pieces use high-contrast circles and standard `K`, `Q`, `R`, `B`, `N`, and `P`
labels so the display works consistently on both Windows and Ubuntu without
requiring a separate chess-symbol font.

## Illegal-move warning

Revision 2 checks whether the stable physical-board change can be explained by
any move that is legal in the recorded position. If it cannot, the whole app
shows a large red **ILLEGAL MOVE** warning.

Recording pauses while this warning is visible. Return all moved pieces to the
last legal position. Once the camera sees that the board has been restored, the
warning disappears automatically and the game can continue.

Because this is camera-based detection, a hand, strong moving shadow, or an
obstructed square can occasionally look like an illegal move. Keep hands clear
after moving and use even lighting.

## Supported systems

Revision 4 automatically selects the native camera backend:

- Ubuntu/Linux: Video4Linux2 (V4L2)
- Windows: DirectShow
- macOS: AVFoundation

If the preferred backend cannot open the camera, the app automatically retries
with OpenCV's default backend.

## Fast setup on Ubuntu

These instructions are intended for Ubuntu 22.04 or 24.04 on a desktop session.

1. Open Terminal in the project folder.
2. Install the system packages:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip libgl1 libglib2.0-0 v4l-utils
```

3. Make the launcher executable and run it:

```bash
chmod +x run_ubuntu.sh
./run_ubuntu.sh
```

The first launch creates `.venv` and installs the Python dependencies and
offline OCR models. Later launches reuse that environment.

To choose another camera:

```bash
./run_ubuntu.sh --camera 1
```

To list cameras recognized by Ubuntu:

```bash
v4l2-ctl --list-devices
ls /dev/video*
```

If the camera exists but the app reports permission denied, add your account to
Ubuntu's `video` group, then log out and back in:

```bash
sudo usermod -aG video "$USER"
```

The graphical interface requires a normal Ubuntu desktop session. It will not
display from a text-only SSH session without graphical forwarding.

## Fast setup on Windows

1. Install Python 3.11 or 3.12 from <https://www.python.org/downloads/>.
   During installation, select **Add Python to PATH**.
2. Extract this project.
3. Double-click `run_windows.bat`.
4. The first launch installs the required packages and offline OCR models. It
   can take several minutes. Later launches are much faster.

For a different camera, open Command Prompt in the project folder and run:

```bat
.venv\Scripts\python.exe app.py --camera 1
```

## Camera and board setup

1. Put the camera on a rigid stand. Do not hold it.
2. Aim it about 45° downward. The full board and full lit phone screen must fit
   in the laptop-camera image.
3. Put White's pieces on the side closest to the camera.
4. Place the phone vertically beside the board and open the Lichess clock.
5. Increase the phone brightness enough to keep the digits sharp, but avoid
   glare or reflections.
6. In board calibration, click the four outside corners in this exact order:
   `a8`, `h8`, `h1`, `a1`.
7. In phone calibration, click the four lit-screen corners in this order:
   top-left, top-right, bottom-right, bottom-left as seen by the camera.
8. Press Enter to save each set of corners.
9. Check that the White and Black clock readings shown in the app are correct.
   Press `F` if their sides are reversed.
10. Put every piece in the normal starting position and press `S`.

The saved calibration is reused next time. Press `C` inside the app or launch
with `--recalibrate` if the camera, board, or phone has moved. Press `K` to
recalibrate only the phone.

## Match controls

| Key | Action |
| --- | --- |
| Enter | Accept the selected move |
| Left / Right | Choose another legal candidate |
| Q / R / B / N | Select the promotion piece |
| U | Undo the last recorded move and resynchronize |
| S | Open the pre-game setup for a new game |
| A / B / C / F / G / K / T | Open pre-game setup (legacy shortcuts) |
| Esc | Finish and close |

Every action above also has a clickable button or a clickable pre-game control,
so keyboard shortcuts are optional.

The current game is continually saved to:

```text
games/latest_game.pgn
```

When the app closes, it also creates a timestamped copy in `games/`.

## Important limitations

- This is a functional prototype, not tournament-certified electronic-board
  hardware.
- A camera at 45° can have pieces hide squares behind them. Raise the camera
  and use a slightly steeper angle if possible.
- The clock digits need to remain reasonably large and sharp in the full camera
  frame. A screenshot alone does not prove the final camera distance will work.
- Phone glare, screen flicker, focus blur, or very small digits can prevent OCR.
  The app omits uncertain clock tags rather than inventing times.
- Do not move two pieces as part of one ordinary move. Castling is handled
  because it is a single legal chess move.
- If the suggested move is wrong, use Left/Right before pressing Enter.
- If the board and software ever disagree, physically restore the correct
  position, press `U` if the last move was wrong, and continue.
- Automatic acceptance should only be enabled after testing your lighting,
  board, and camera placement.

## Developer commands

```bash
python -m venv .venv
# Windows:
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest -q
.venv\Scripts\python app.py
```

The main computer-vision and legal-move logic is in `chess_tracker.py`. Lichess
clock OCR is in `clock_reader.py`. Built-in clock logic is in
`builtin_clock.py`. Chess-ending rules are in `game_rules.py`. Clickable setup
components are in `pregame_ui.py`. The interface and camera loop are in
`app.py`.
