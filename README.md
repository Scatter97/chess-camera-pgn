# Physical Chess Camera → Timed PGN (Revision 6)

This Windows/laptop app watches a normal physical chess game and a Lichess
clock running on a phone through one fixed camera. It saves the moves and each
player's remaining time as a PGN file.

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
changes alone, so use Q, R, B, or N before confirming.

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

## Controls

| Key | Action |
| --- | --- |
| Enter | Accept the selected move |
| Left / Right | Choose another legal candidate |
| Q / R / B / N | Select the promotion piece |
| U | Undo the last recorded move and resynchronize |
| A | Turn high-confidence automatic acceptance on/off |
| B | Toggle Bullet Mode before a game |
| S | Start a new game from the standard position |
| C | Recalibrate the board and phone |
| K | Recalibrate only the phone screen |
| F | Swap which phone half belongs to White |
| Esc | Finish and close |

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
clock OCR is in `clock_reader.py`. The interface and camera loop are in
`app.py`.
