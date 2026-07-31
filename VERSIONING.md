# Chess Camera versioning

`version.py` is the single source of truth for the displayed app version.

## Feature releases

Major features and substantial updates use a two-part `0.xx` version.

Examples:

- `0.36` — built-in opening book and custom-book support
- `0.37` — the next major feature release

The second number increases by one for each feature release.

## Patch releases

Small visual adjustments, minor behavior changes, and bug fixes use a three-part `0.xx.xx` version.

Examples:

- `0.36.1` — first small fix after `0.36`
- `0.36.2` — second small fix after `0.36`

After any number of `0.36.x` patches, the next major feature release becomes `0.37`.

## Release checklist

1. Update `APP_VERSION` in `version.py`.
2. Add the release to `CHANGELOG.md`.
3. Confirm the main menu displays the new version.
4. Run syntax and automated tests where available.
5. Test camera, OpenCV windows, clipboard, engine, and opening-book behavior on a target computer when those features changed.
