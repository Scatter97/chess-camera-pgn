# Chess Camera versioning

`version.py` is the single source of truth for the displayed app version.

**Current release: 0.40**

## Feature releases

Major features and substantial updates use a two-part `0.xx` version.

Examples:

- `0.36` — built-in opening book and custom-book support
- `0.37` — the next major feature release

The second number increases by one for each feature release.

## Patch releases

Small visual adjustments, code cleanup, minor behavior changes, documentation restoration, and bug fixes use a three-part `0.xx.xx` version.

Examples:

- `0.36.1` — first patch after `0.36`
- `0.36.2` — second patch after `0.36`

After any number of `0.36.x` patches, the next major feature release becomes `0.37`.

## Release checklist

1. Update `APP_VERSION` in `version.py`.
2. Add the release to `CHANGELOG.md`.
3. Confirm the main menu displays the new version.
4. Update the README when installation, behavior, or user-facing features changed.
5. Run syntax and automated tests where available.
6. Test camera, OpenCV windows, clipboard, engine, OCR, and opening-book behavior on a target computer when those features changed.
