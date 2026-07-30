# Physical Chess Camera → Timed PGN (Revision 19)

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
- Normal, Fast, or Bullet detection;
- manual or automatic move confirmation;
- which OCR clock display belongs to White;
- separate starting times and increments for White and Black;
- camera-controlled or player-controlled built-in clock switching;
- board or phone recalibration;
- optional three-frame Accuracy Boost;
- a labeled 64-square calibration check;
- camera placement on any of the board's four sides.

Player and event names are included in the saved PGN headers.

## Revision 19: macOS launcher

macOS now has a dedicated `run_mac.command` launcher. It selects Python 3.11
or 3.12, creates the `.venv` environment on the first launch, installs the
project dependencies, and starts the app. It supports both Intel and Apple
Silicon Macs through Python's native packages and OpenCV's AVFoundation camera
backend.

## Revision 18: larger edge margin

The automatic exterior detection margin is now 100 pixels on every side,
equal to one full corrected-board square. Calibration is unchanged: click the
exact corners of the 8×8 playing grid, and the app adds the margin itself.

## Revision 17: angled pieces and camera orientation

The camera no longer needs to be on White's side. In game settings, use
**White side** to select where White appears in the camera image:
**Bottom**, **Top**, **Left**, or **Right**. The app rotates the corrected board
internally so its chess coordinates and virtual board always remain consistent.

Board calibration now uses the four corners as they appear on the camera:
image top-left, image top-right, image bottom-right, then image bottom-left.
The corner labels no longer depend on which player is nearest the camera.

The corrected camera image also keeps a 100-pixel detection margin outside every
board edge. The first and eighth ranks—and the `a`- and `h`-files when the
camera is beside the board—use these exterior strips as extra visual evidence.
This helps recognize tall pieces whose tops appear to lean outside the flat
64-square grid at an angled camera view.

Keep some visible table around every edge of the board. The extra margin cannot
recover a piece top if it is already outside the original camera frame. Use
**Check all 64 squares** after choosing the White-side setting to confirm the
orientation and board alignment.

## Revision 16: Accuracy Boost

Turn on **Boost ON - 3 frames** in the game-settings screen when accuracy is
more important than the lowest possible delay. It works with Normal and Fast
detection and is automatically disabled in Bullet mode.

Accuracy Boost:

- compares three stable full-resolution board frames and requires at least two
  readings to agree on the same legal move;
- corrects small camera shifts of up to eight pixels;
- compensates for a whole-frame brightness change before comparing squares;
- uses a median of the three frames as the next saved board reference;
- silently retries when the frame readings disagree instead of immediately
  showing an illegal-move warning.

The extra checks normally add about 0.12–0.25 seconds after the selected
stability delay on a powerful laptop. They are especially useful with unusual
pieces, reflections, and the temporary LEGO board used during development.

Click **Check all 64 squares** before starting a game to open a live,
perspective-corrected board with every square labeled. Confirm that the grid
follows the physical board edges. Tall edge pieces may extend into the new
outer margin. If the grid does not follow the board, close the check and click
**Recalibrate board**.

## Illegal-move recovery

Revision 14 pauses the built-in clock when the camera confirms an illegal
position. Return the pieces to the last recorded position and leave the board
still; the red warning then disappears automatically and the same player’s
clock resumes. The restoration check tolerates small camera noise and minor
piece-placement differences.

If a player pressed their A/L clock key before the illegal move was recognized,
that clock press is cancelled so the same player can retry. In Lichess OCR
mode, the app cannot control the phone, so pause and resume the Lichess clock
on the phone itself.

## Automatic or manual built-in clock switching

Revision 13 adds a **Clock switch** choice to the pre-game settings when the
built-in clock is selected:

- **Camera automatic:** the camera stops the player’s clock when the move is
  detected and accepted. This is the original behavior.
- **Player keys A / L:** White presses **A** on the left side of the keyboard,
  and Black presses **L** on the right side. The key is pressed after completing
  the physical move. The player’s clock stops immediately, their increment is
  added, and the opponent’s clock starts.

In Player keys mode, the camera move cannot be accepted until the correct
player has pressed their key. Pressing the wrong player’s key shows a warning
and does not switch the clock. If automatic confirmation or Bullet Mode is
active and the camera already has a move waiting, pressing the correct key also
accepts that move. If a key was pressed accidentally before the move was
accepted, click **Undo** to cancel that clock press.

There is no clickable clock-switch button on the match screen.

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

Revision 15 adds **Fast** detection to the clickable pre-game settings. Fast
mode waits about 0.35 seconds after the board stops moving and uses a
lower-resolution copy only for motion checking. Exact square analysis still
uses the full corrected board image.

The camera preview displays the selected detection mode, live FPS, and a green
stability-progress bar. With automatic confirmation enabled, Fast mode records
only high-confidence moves; lower-confidence moves remain on screen for manual
confirmation instead of being guessed.

Use **Normal** for maximum reliability, **Fast** for ordinary quick games, and
**Bullet** only when the lowest delay matters more than accuracy.

Revision 6 adds a lower-latency mode for games with moves around one second
apart. Normal accuracy mode remains the default every time the app starts.

Select **Bullet** during the pre-game settings. The app displays an orange
**BULLET - LOWER ACCURACY** indicator while it is active.

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

## Fast setup on macOS

1. Install Python 3.11 or 3.12 from
   <https://www.python.org/downloads/macos/>.
2. Download and extract the project.
3. Open Terminal, type `cd ` including the space, drag the extracted
   `chess-camera-pgn` folder into Terminal, and press Return.
4. Make the launcher executable once:

```bash
chmod +x run_mac.command
```

5. Double-click `run_mac.command`. If macOS blocks the first launch,
   Control-click it, choose **Open**, and confirm **Open**.
6. When requested, allow camera access. The setting can later be changed under
   **System Settings → Privacy & Security → Camera**.

The first launch creates `.venv` and installs the required packages. Later
launches start directly. To select another camera, run:

```bash
./run_mac.command --camera 1
```

If camera permission was denied, enable it for Terminal or Python in macOS
Settings, close the app, and launch it again.

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
3. The camera may be on White's side, Black's side, or either side edge.
4. Place the phone vertically beside the board and open the Lichess clock.
5. Increase the phone brightness enough to keep the digits sharp, but avoid
   glare or reflections.
6. In board calibration, click the corners as they appear in the camera:
   image top-left, image top-right, image bottom-right, image bottom-left.
7. In phone calibration, click the four lit-screen corners in this order:
   top-left, top-right, bottom-right, bottom-left as seen by the camera.
8. Press Enter to save each set of corners.
9. In game settings, choose whether White appears at the Bottom, Top, Left, or
   Right of the camera image, then use **Check all 64 squares**.
10. Check that the White and Black clock readings shown in the app are correct.
    Change the OCR sides option if their displays are reversed.
11. Put every piece in the normal starting position and click **Start Game**.

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
