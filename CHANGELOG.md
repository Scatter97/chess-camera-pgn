# Changelog

## 0.38

Major feature release.

- Added **Experimental Features** under the main Settings menu.
- Added an optional **64-Square Local Detection (Beta)** toggle, disabled by default.
- Added Low, Normal, and High local-detection sensitivity settings, with Normal recommended.
- Split board-motion checking into 64 independent square regions so unrelated moving squares can be ignored while the squares involved in a legal move settle.
- Preserved full expected-square handling for captures, castling, en passant, and promotion.
- Kept stable unexpected changes as evidence against a candidate move so extra displaced pieces can still trigger illegal-position recovery.
- Applied local filtering to normal detection, Accuracy Boost consensus, move confidence, legal-move fit, and illegal-position restoration.
- Added a `LOCAL64` indicator to the camera diagnostics while the beta feature is active.
- Removed the permanent Queen, Rook, Bishop, and Knight buttons from the match screen.
- Promotion choices now remain in the dedicated promotion popup that appears when a promotion move is detected.
- Added automated tests for beta settings, square-level motion, candidate filtering, legal-move fit, castling, en passant, and popup-only promotion controls.

## 0.37

Major feature release.

- Added **Advanced Camera Settings** under the main Settings menu.
- Added saved camera selection with friendly Linux device names and `/dev/video*` paths.
- Added camera refresh and a full-speed preview test for checking the selected device.
- Added independently configurable detection frame rates of 3, 5, 10, or 15 FPS.
- Added detection resolutions of 320×240, 640×480, 960×540, or 1280×720.
- Split the live preview from board analysis so every incoming camera frame can be displayed while detection samples at the selected rate.
- Added optional live diagnostics showing measured preview FPS, measured and target detection FPS, input resolution, detection resolution, selected camera, backend, and driver-reported FPS.
- Saved camera settings in `camera_config.json` and preserved them when the existing game-setup configuration is written.
- Kept the `--camera` command-line option as an explicit override of the saved camera selection.
- Added automated tests for settings validation, command-line camera overrides, detection resizing, corner-coordinate scaling, and detection-frame caching.

## 0.36.3

Patch release.

- Added a guided board and phone-screen calibration interface.
- Added a dedicated calibration layout with a scaled camera preview, corner progress, numbered markers, Undo, Reset, Review, and Cancel controls.
- Added automatic source-coordinate mapping so calibration points remain accurate even when the preview is resized.
- Added a corrected perspective preview before calibration is confirmed.
- Added basic geometry validation for crossed, tiny, extremely narrow, or overlapping corner selections.
- Added an optional calibration debug panel showing incoming resolution, camera-reported FPS, and OpenCV backend.
- Kept the original calibration functions available as implementation fallback while installing the new interface at app startup.

## 0.36.2

Patch release.

- Removed Ubuntu/Linux OpenCV Qt toolbar controls from app windows.
- Removed the pixel-coordinate and RGB status readout shown below OpenCV windows.
- Kept all OpenCV windows resizable by combining `WINDOW_NORMAL` with `WINDOW_GUI_NORMAL` on Linux.
- Applied the behavior globally at app startup so the main menu, calibration, setup, history, review, Chess960, and Opening Explorer windows use the cleaner interface.

## 0.36.1

Patch release.

- Removed obsolete Revision 35 entry files, launchers, and legacy notes.
- Renamed the active support code to permanent module names.
- Removed Revision 35-specific imports and navigation action names from the current app.
- Restored a longer, detailed README covering setup, calibration, clocks, detection, training, analysis, Chess960, opening books, installation, privacy, and troubleshooting.
- Updated the displayed version to 0.36.1.
- Updated the macOS launcher so it reads the version from `version.py` instead of hard-coding it.

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
