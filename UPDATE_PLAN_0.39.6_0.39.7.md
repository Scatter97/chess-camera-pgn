# Update Plan: 0.39.6 and 0.39.7

## 0.39.6 Advanced Detection & Board Sync

### Automatic high-confidence move approval
- Add Advanced Detection setting for automatic move approval.
- User-selectable confidence threshold.
- Only automatically approve legal moves.
- Keep optional stricter requirements for captures and promotions.
- Show confidence information during detection.

### Restore camera preview move highlights
- Bring back yellow move highlights on the camera preview.
- Highlight detected starting and ending squares.
- Show detected move and confidence status.

### Manual Board Edit Mode
- Add a manual board editing option during games.
- Reuse the same virtual board drag-and-drop interface as illegal move correction.
- Allow users to synchronize the online board with the physical board.
- Update FEN/PGN state after saving changes.
- Update camera reference so manual changes are not detected as new moves.

---

## 0.39.7 Chess Appearance System

### Realistic chess pieces
- Replace text pieces with image-based chess piece icons.
- Use the same piece theme across:
  - Live game board
  - Stockfish analysis
  - Review board
  - Illegal move correction
  - Manual edit board

### Custom piece packs
- Add support for user-imported piece themes.
- Support a standard folder format containing 12 piece images.
- Add piece theme selection in settings.

### Piece sounds
- Add optional chess move sounds.
- Support sound packs.
- Package the app with 1-2 default piece sound packs.
- Allow users to add custom sound packs later.

These features will only be implemented after review and approval.