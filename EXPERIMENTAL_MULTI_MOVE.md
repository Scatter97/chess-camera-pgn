# Experimental Multi-Move Recovery

This framework lives only on the `experimental/multi-move-recovery` branch. It is not part of `main` and should remain experimental until it has been tested with a physical board, camera, clocks, captures, castling, and promotions.

## Goal

When the camera reaches a stable position that cannot be explained by one legal move, Chess Camera can search for a legal sequence of two or three half-moves that may have occurred before detection completed.

Example:

```text
Last recorded position: White to move
Physical moves: e2-e4, e7-e5, g1-f3
Camera finally becomes stable after all three moves
Recovered sequence: e4, e5, Nf3
```

## Enabling the experiment

1. Open **Settings**.
2. Open **Advanced Detection**.
3. Open **Experimental Multi-Move Recovery**.
4. Turn **Multi-Move Recovery** on.
5. Keep automatic acceptance off during initial testing.

Recommended test settings:

```text
Multi-Move Recovery: ON
Maximum recovery: 3 half-moves
Auto-accept certain sequences: OFF
```

## Runtime flow

```text
Stable camera frame
        |
        v
Try normal one-move detection
        |
        +-- one legal move fits --> existing move confirmation flow
        |
        v
One move does not fit
        |
        v
Search legal sequences of depth 2 and 3
        |
        v
Score final board changes + movement-event order
        |
        +-- no strong result --> existing illegal/correction flow
        |
        v
Show top recovered sequences
        |
        +-- player cancels --> existing illegal/correction flow
        |
        v
Validate every move again, append to PGN, resynchronize camera
```

## Core modules

### `multi_move_recovery.py`

Contains:

- Saved experimental settings
- Rolling movement-event buffer
- Legal sequence beam search
- Final-position scoring
- Temporal event-order scoring
- Confidence and ambiguity calculation
- Recovery confirmation and preview UI

### `runtime_multi_move_patch.py`

Builds on `runtime_0397_patch.py` and injects the experimental recovery path before the normal illegal-position warning.

### `multi_move_settings.py`

Adds the isolated experimental settings screen without changing the stable advanced-detection screen.

### `tests/test_multi_move_recovery.py`

Covers:

- Two-half-move recovery
- Three-half-move recovery
- Temporal move-order evidence
- Ambiguous transpositions
- Settings validation
- Runtime source-patch compilation
- Experimental startup wiring

## Search model

The search starts from the last confirmed `chess.Board` and expands every legal move up to the selected depth.

A beam keeps only the strongest partial candidates at every depth. The default beam width is 140 candidates, which avoids searching every possible branch at depth three.

Each candidate receives four main measurements:

```text
Final position fit       72%
Temporal event evidence  20%
Change quality            8%
Length penalty            small
```

### Final-position fit

The final virtual board is compared with the squares that visibly changed between the last accepted reference frame and the current stable frame.

The score combines:

- How much observed change is explained by the candidate position
- How many expected final squares are visible
- Whether expected squares contain strong visual change

### Temporal event evidence

`FrameEventBuffer` watches movement bursts between stable periods. When movement stops, it records the squares affected by that burst.

For three missed moves, the buffer may contain:

```text
Event 1: e2, e4
Event 2: e7, e5
Event 3: g1, f3
```

Candidate move-square sets are aligned with those events in chronological order. This can distinguish sequences that reach the same final position through different move orders.

## Ambiguity protection

A recovered sequence is marked ambiguous when:

- The top two candidates are too close
- Different move orders reach the same final position and timing evidence is weak
- A promotion is involved

Ambiguous sequences cannot be automatically accepted. The player must choose a candidate or return to the normal correction flow.

## PGN and clocks

Recovered moves are appended to the PGN in legal order.

The program does not invent individual clock readings. Recovered moves receive unknown clock values because the exact time after each missed move may not be available.

For the built-in clock, the clock is paused while the recovery dialog is open and resumes for the side to move after the sequence is accepted.

## Training data

Recovered moves are not added as normal positive training samples. Their training snapshots are stored as `None` so uncertain reconstruction does not teach the normal one-move detector incorrect signatures.

## Current limits

- Maximum search depth is three half-moves.
- Exact move order can remain unknowable when intermediate movement events were not captured.
- Piece identity is inferred through legal chess state, not a dedicated camera piece classifier.
- Promotion type remains ambiguous from square-change evidence alone.
- Exact individual clock times cannot be reconstructed reliably.
- The feature is disabled by default.

## Testing the branch on Ubuntu

```bash
git fetch origin
git switch experimental/multi-move-recovery
git pull --ff-only
./run_ubuntu.sh
```

Return to stable `main` with:

```bash
git switch main
git pull --ff-only
./run_ubuntu.sh
```

Before switching branches during physical testing, keep copies of important local `games/`, `board_profiles/`, and `camera_config.json` data.

## Test scenarios

1. `e4`, `e5` before detection settles.
2. `e4`, `e5`, `Nf3` before detection settles.
3. Two move orders that reach the same final board.
4. One capture within a recovered sequence.
5. Castling as one move in a recovered sequence.
6. En passant in a recovered sequence.
7. Promotion, confirming that automatic acceptance is blocked.
8. Cancel recovery and use the existing correction editor.
9. Accept recovery and verify PGN order and side to move.
10. Switch back to `main` and verify the stable app is unchanged.
