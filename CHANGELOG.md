# Changelog

## 0.41

Downloadable chess knowledge release.

- Added **Settings → Data and Libraries** for optional chess data after installation.
- Added a downloadable expanded opening package based on the pinned CC0 Lichess opening-name dataset.
- Added local conversion of downloaded PGN opening lines into a Polyglot book.
- Added built-in, downloaded, and custom opening-book modes in Opening Explorer.
- Added an optional approximately 939 MB Syzygy 3/4/5-piece WDL and DTZ package from the Lichess tablebase mirror.
- Preserved custom Syzygy folder support for user-provided six- and seven-piece collections.
- Added resumable HTTP Range downloads, cancellation, configurable storage, activation, verification, and removal controls.
- Added pinned Git blob verification for opening source files and locally recorded SHA-256 checksums for installed packages.
- Kept all large opening and tablebase files outside Git and outside the default Windows, Debian, and macOS installers.
- Added automated tests for PGN/TSV conversion, package configuration, trusted download hosts, pinned opening-source verification, and tablebase index discovery.

## 0.40

Local endgame tablebase release.

- Added **Endgame Explorer** to the main menu.
- Added local Syzygy tablebase folder selection with persisted configuration.
- Added FEN loading, exact WDL and DTZ result display, and clickable tablebase root moves.
- Kept tablebase analysis local and reported unsupported or uncovered positions without failing the app.

## 0.39.7

Piece appearance and sound release.

- Replaced letter-in-circle virtual pieces with an original Staunton-inspired PNG piece pack.
- Applied the selected piece pack to the live game, illegal correction, manual synchronization, game review, and analysis boards.
- Added support for custom piece packs placed in `piece_packs/<pack name>/` with twelve transparent PNG files.
- Added **Board Appearance and Sounds** settings with piece-pack selection and direct access to the custom-pack folders.
- Added move, capture, check, castling, and promotion sounds.
- Bundled two locally generated sound packs: **Classic Wood** and **Soft Digital**.
- Added support for custom WAV sound packs placed in `sound_packs/<pack name>/`.
- Added sound enable/disable, sound-pack selection, and a test-sound button.
- Restored yellow move highlights over the calibrated camera preview after a move is recorded.
- Added a setting to enable or disable camera move highlights.

## 0.39.6

Advanced detection and board synchronization release.

- Added **Advanced Detection** settings.
- Added an optional confidence-based auto-approval toggle.
- Added a user-adjustable auto-approval threshold from 50% to 99%.
- Moves at or above the selected confidence are accepted automatically; lower-confidence moves stay available for manual approval.
- Added **Edit Virtual Board** during a game.
- Manual board synchronization pauses the built-in clock and uses the existing live virtual-board layout.
- Players can drag one or more legal moves, undo edits, reset the editor, cancel, or save the synchronized position.
- Saved synchronization moves are appended to the PGN, the camera reference is refreshed, and the built-in clock resumes for the correct side.
- Added automated tests for threshold persistence, manual legal-move synchronization, piece packs, sound packs, and runtime source integration.
- Added a GitHub Actions workflow for compilation and pytest checks.

## 0.39

Reliability release.

- Removed the camera calibration inner preview rectangle after calibration cleanup.
- Fixed review-board move navigation so selecting a move immediately updates the virtual board position.
- Removed Game History up/down controls and simplified history navigation.
- Added advanced board training controls under Settings.
- Added undo training cleanup so removed moves can restore the previous training state.
- Added rejected detection examples so false detections improve future filtering without remaining accepted samples.
- Added illegal move recovery mode with a virtual-board editor.
- Added **MOVE WAS LEGAL - FIX BOARD** correction flow with drag-and-drop editing.
- Paused the built-in clock during illegal correction and resumed the correct side after a validated correction.
- Added tests for training rollback, illegal correction drag validation, castling correction, startup patching, and clock behavior.

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
