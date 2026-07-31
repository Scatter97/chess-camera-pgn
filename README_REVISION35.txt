Chess Camera Rev. 35 (Main Menu Update)

Revision 35 is the main version of Chess Camera.

Main additions:
- Scalable feature-grid main menu with reserved space for future tools.
- Start OTB Game, Game History, Chess960 Generator, Opening Explorer, Settings, and Exit.
- Chess960 Generator uses the same virtual-board and piece renderer as live play and Stockfish analysis.
- Opening Explorer uses python-chess chess.polyglot with a user-selected local Polyglot .bin book.
- Opening Explorer supports weighted clickable moves, percentages, Back Move, Reset, current FEN, and saved book selection.
- Fresh board calibration for the first OTB game after each app launch.
- Reuse the current calibration for rematches and later games in the same session.
- Game History with result, ending method, move count, time control, date, event, both accuracies, Stockfish review, Copy PGN, and confirmed deletion.
- Settings page with a file picker for choosing a trusted UCI engine.
- Board Options menu containing Rename preset and Reset training.
- New board creation asks for the board name.
- Smaller icon-only Swap sides control.
- Back and Esc return from initial game setup to the main menu.
- Rematch keeps players, event, and time control while allowing further editing.
- Post-game evaluation bar moved to the left side of the board.
- An X appears inside the active White, Black, or Event text field to clear it.

Opening books:
- Put a permitted Polyglot .bin file in books/ or choose it from Opening Explorer.
- No opening-book database is bundled with the app.

Launchers:
- Windows: run_windows.bat
- Ubuntu: ./run_ubuntu.sh
- macOS: ./run_mac.command

The Revision 35-specific launchers remain available and open the same current build.
