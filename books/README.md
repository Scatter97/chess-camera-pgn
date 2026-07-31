# Opening books

Chess Camera 0.36 includes a small built-in opening-book source:

```text
default_openings.tsv
```

Opening Explorer automatically converts it into:

```text
chess_camera_default.bin
```

The generated `.bin` file is local and ignored by Git because it can be rebuilt at any time.

## Source and license

The bundled opening lines were curated from `lichess-org/chess-openings`, an aggregated opening-name dataset released under the CC0 Public Domain Dedication. The source TSV remains human-readable so its moves can be inspected and edited.

## Using another book

Open **Opening Explorer → Choose Book...** and select a readable Polyglot `.bin` file. Chess Camera remembers that custom path.

Select **Use Built-in** to switch back. If the custom file is moved or deleted, the explorer automatically falls back to the included book.

Only use custom book files that you are permitted to use. A book being freely downloadable does not automatically mean it may be redistributed.

## Rebuilding from the bundled source

The app rebuilds the book automatically when needed. It can also be generated manually:

```powershell
.\.venv\Scripts\python.exe -c "from pathlib import Path; from opening_book_builder import build_polyglot_book_from_tsv; build_polyglot_book_from_tsv(Path('books/default_openings.tsv'), Path('books/chess_camera_default.bin'))"
```

## Building from the full Lichess dataset

Clone or download `lichess-org/chess-openings`, then run:

```powershell
.\.venv\Scripts\python.exe tools\build_default_book.py `
  vendor\lichess-openings `
  books\chess_camera_default.bin
```

The tool reads `a.tsv` through `e.tsv`, converts their PGN lines to UCI, counts repeated position-and-move pairs, and writes a sorted Polyglot book.
