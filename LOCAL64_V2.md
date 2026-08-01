# 64-Square Detection V2

This experimental overhaul keeps the existing 64-square move analysis but replaces whole-board stability gating with sixteen independent 2x2 movement zones.

## Goals

- A hand moving over an unrelated area must not prevent a clear move from being analyzed.
- A motionless hand, sleeve, paper, phone, or other object must be treated as blocked/unknown rather than as a piece change.
- The detector must preserve enough recent partial-board evidence to help multi-move recovery.
- Existing legal-move ranking, Accuracy Boost, automatic approval, correction, training, and custom sensitivity settings remain available.

## Zone states

Each 2x2 zone is classified as:

- `CLEAR` — stable and available for move evidence.
- `MOVING` — pixels are changing between recent frames.
- `BLOCKED` — a broad connected difference is likely an obstruction.
- `RECOVERING` — the obstruction or movement ended, but the zone must remain clear briefly before use.

Only clear zones contribute square-change evidence. A legal move can be evaluated as soon as every zone containing its required squares is clear; activity elsewhere is masked instead of restarting the whole-board timer.

## Temporal buffer

The runtime stores a ten-second rolling buffer of reduced warped-board snapshots and per-zone state metadata.

Capture intervals:

- Normal: 0.30 seconds
- Fast: 0.20 seconds
- Bullet: 0.12 seconds
- Additional snapshot whenever any zone changes state

The buffer stores only warped board images, not the full camera frame. Frames older than ten seconds are discarded.

## Multi-move recovery integration

When `multi_move_recovery` is present, V2 automatically adds its temporal evidence to the existing legal sequence search. Clear zone transitions become timestamped square events. Squares that are hidden in the newest frame may use the most recent trustworthy transition evidence, while blocked zones remain unknown rather than being assumed unchanged.

This improves candidate order and confidence without inventing moves or individual clock times. Ambiguous candidates still require confirmation under the existing multi-move recovery rules.

## Debug display

The camera diagnostics panel includes a 4x4 zone map:

- Green: clear
- Yellow: moving
- Red: blocked
- Purple: recovering

The map also shows how many snapshots are currently buffered.

## Required physical tests

Before merging, test:

1. Make a move, then move the hand over an unrelated zone.
2. Leave a stationary hand over one square and over an entire 2x2 zone.
3. Move a sleeve, paper, or phone across several zones.
4. Normal moves whose origin and destination are in different zones.
5. Captures, castling, en passant, and promotions.
6. Accuracy Boost and confidence-based automatic approval.
7. Illegal-move correction and manual board synchronization.
8. Two and three missed half-moves with different zones blocked at different times.
9. Normal, Fast, and Bullet detection modes.
10. Camera angles from every side of the board.

Keep the feature experimental until these camera tests pass.