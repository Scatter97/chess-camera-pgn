# Changelog

## 0.36

Major feature release.

- Added a built-in CC0-derived opening book source.
- The app automatically generates a local Polyglot `.bin` book when Opening Explorer is first opened.
- Added **Use Built-in** so users can return from a custom book to the included book.
- Kept **Choose Book...** for user-supplied Polyglot books.
- Added validation and automatic fallback when a custom book is missing or unreadable.
- Added a reusable Polyglot book builder and a tool for generating a larger book from the full `lichess-org/chess-openings` dataset.
- Added `chess_camera.py` as the current entry point.
- Added centralized version information in `version.py`.
- Adopted the `0.xx` feature-release and `0.xx.xx` patch-release system.

## 0.35

- Added the scalable main menu.
- Added Game History, Settings, rematches, board options, and engine selection.
- Added the Chess960 generator and Opening Explorer.
- Updated Chess960 to use the live-game and Stockfish-analysis piece renderer.
