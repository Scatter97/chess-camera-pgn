# Chess Camera 0.41 Content Library

Chess Camera 0.41 adds an in-app **Data and Libraries** manager for optional opening and endgame data. Large datasets are downloaded after installation instead of being stored in Git or added to every desktop installer.

## Open the manager

```text
Settings
└── Data and Libraries
```

The same manager can also be opened from Opening Explorer and Endgame Explorer.

## Available packages

### Expanded Lichess Opening Names

The opening package downloads the five ECO TSV files from the public `lichess-org/chess-openings` project at a pinned Git commit. Each source file is checked against its pinned Git blob SHA-1 before Chess Camera converts the PGN lines into a local Polyglot book.

Source commit:

```text
51b886249b9e418498d25b6e39b926c3de99c29a
```

The generated book is stored as:

```text
content_library/openings/lichess-opening-names/lichess_opening_names.bin
```

The package contains opening names and theory lines. Its Polyglot weights represent how often a position/move pair appears in the imported opening lines; they are not live player win rates.

After installation, Opening Explorer can switch among:

- Built-in small book
- Downloaded expanded book
- User-selected custom Polyglot `.bin` book

### Syzygy 3/4/5-Piece Tablebases

The tablebase package mirrors the standard 3/4/5-piece WDL and DTZ files from the Lichess tablebase server. It is approximately 939 MB and requires at least 1.25 GB of free space before installation starts.

The files are stored under:

```text
content_library/tablebases/syzygy-3-4-5/
```

After installation, Endgame Explorer automatically supports exact local results for covered positions with five or fewer pieces. A user-selected custom Syzygy folder remains supported and can contain larger six- or seven-piece collections.

## Download behavior

Downloads use HTTPS and an explicit host allowlist:

```text
raw.githubusercontent.com
tablebase.lichess.ovh
```

Large files are written to `.part` files. When the server supports HTTP Range requests, an interrupted or cancelled download resumes from the existing partial file. When Range resume is unavailable, only that file restarts.

The manager supports:

- Download or update
- Cancel while keeping resumable partial files
- Activate a downloaded package
- Verify installed files
- Remove installed data
- Change the storage location

After a package has been downloaded, Opening Explorer and Endgame Explorer work offline.

## Integrity model

### Opening package

The opening source is pinned to one Git commit. The five downloaded TSV files are verified against their exact Git blob object IDs before conversion. Chess Camera also records SHA-256 checksums for the source files and generated Polyglot book in `package.json`.

### Tablebase package

The tablebase package is downloaded from the official Lichess HTTPS tablebase mirror. Chess Camera records a SHA-256 checksum for every downloaded file, verifies those checksums on request, and asks `python-chess` to load the installed directory before marking installation successful.

The Lichess directory listing does not provide a complete signed SHA-256 catalog through this downloader. The first local checksum records the bytes received over HTTPS; later verification detects local corruption or modification. This should not be described as independent source-hash verification.

## Storage locations

The default content library is located inside the normal Chess Camera data folder.

### Windows packaged app

```text
%LOCALAPPDATA%\ChessCamera\content_library
```

### Debian/Linux packaged app

```text
${XDG_DATA_HOME:-~/.local/share}/chess-camera/content_library
```

### macOS packaged app

```text
~/Library/Application Support/ChessCamera/content_library
```

### Source checkout

```text
<repository>/content_library
```

The user may choose another folder, including a secondary drive. Changing the configured storage location does not automatically move previously downloaded data.

## Configuration keys

The manager stores these values in `camera_config.json`:

```text
content_storage_path
opening_book_mode
opening_book_path
endgame_tablebase_mode
endgame_tablebase_path
```

Valid opening modes are:

```text
builtin
downloaded
custom
```

Valid endgame modes are:

```text
downloaded
custom
```

When a selected file or folder is missing, the explorers fall back safely instead of preventing the rest of the application from starting.

## Main implementation files

```text
content_library.py
content_manager_ui.py
opening_book_builder.py
opening_explorer.py
endgame_explorer.py
runtime_paths.py
```

## Release and packaging policy

No opening database archive or Syzygy tablebase file is committed to the repository. Windows, Debian, and macOS installers contain the download framework only. This keeps installers reasonably sized and lets users decide whether to use around 1 GB of storage for the tablebases.

## Testing checklist

Before merging this feature into `main`, test:

1. Fresh opening-package download.
2. Opening-package cancellation and resume.
3. Opening-package verification and removal.
4. Opening Explorer switching among built-in, downloaded, and custom books.
5. Fresh Syzygy download on a drive with enough space.
6. Syzygy cancellation and resume.
7. Syzygy verification and removal.
8. Exact probing of known three-, four-, and five-piece positions.
9. Custom six- or seven-piece folder selection after the downloaded package is installed.
10. Changing the content storage folder.
11. Windows, Debian, and macOS packaged builds.
12. Offline explorer use after a successful download.

Network downloads and graphical progress windows require hands-on testing. Automated tests use local fake responses and do not download the approximately 939 MB tablebase package during CI.
