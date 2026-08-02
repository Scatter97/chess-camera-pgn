# Knightboard desktop packages

This folder contains the reproducible build definitions for the three desktop packages:

- Windows portable folder containing `Knightboard.exe`
- Debian/Ubuntu `.deb` package
- macOS `Knightboard.app` and `.dmg`

Generated binaries are intentionally published as GitHub Actions artifacts instead of being committed to Git. The packaged dependencies are large and differ by operating system and processor architecture.

## Packaged data locations

Source checkouts continue to store generated files beside the repository. Installed packages use writable per-user folders:

- Windows: `%LOCALAPPDATA%\Knightboard`
- Debian/Linux: `${XDG_DATA_HOME:-~/.local/share}/knightboard`
- macOS: `~/Library/Application Support/Knightboard`

These folders contain settings, board profiles, games, generated opening books, custom piece packs, custom sound packs, and optional engines.

## Why `frozen_app.py` is generated

The development version currently applies the 0.39 reliability state-machine changes through `runtime_app_patch.py` when it starts. A frozen PyInstaller program cannot safely reopen and recompile its own source file. `prepare_frozen_sources.py` therefore applies the same patch during the build and writes `build/generated/frozen_app.py`. `frozen_entry.py` loads that already-patched module.

## Windows

Run from a Windows command prompt:

```bat
build_windows_exe.bat
```

Output:

```text
dist\Knightboard\Knightboard.exe
release\Knightboard-<version>-Windows-x64.zip
```

The executable is an onedir PyInstaller build. Keep `Knightboard.exe` beside the generated `_internal` folder. The ZIP contains the complete portable application.

## Debian, Ubuntu, Zorin OS, and Linux Mint

Install the local build requirements first:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-tk dpkg-dev libgl1 libglib2.0-0
```

Then run:

```bash
chmod +x packaging/build_deb.sh
./packaging/build_deb.sh
```

Output:

```text
release/knightboard_<version>_<architecture>.deb
```

Install it with:

```bash
sudo apt install ./release/knightboard_<version>_amd64.deb
```

The package installs the application under `/opt/knightboard`, the launcher as `/usr/bin/knightboard`, and a desktop-menu entry.

## macOS

Use Python 3.12 on the Mac that will run the build:

```bash
chmod +x packaging/build_macos.sh
./packaging/build_macos.sh
```

Outputs:

```text
dist/Knightboard.app
release/Knightboard-<version>-macOS.dmg
release/Knightboard-<version>-macOS-app.zip
```

The local script applies an ad-hoc signature. A public build should use an Apple Developer ID certificate and Apple notarization. Intel and Apple Silicon packages must be built on the matching architecture unless a universal dependency set is prepared.

## GitHub Actions

`.github/workflows/build-installers.yml` builds all three packages. Open the repository's **Actions** tab, select **Build desktop installers**, and run the workflow. Each operating-system job uploads its package as an artifact.

## Important testing

Before publishing a package, test:

- First launch and camera permission
- Camera selection and calibration
- Live detection and illegal-move correction
- Manual virtual-board synchronization
- Windows move sounds
- Custom PNG and WAV packs
- Game and training-data persistence after restarting
- Stockfish file selection and post-game review
