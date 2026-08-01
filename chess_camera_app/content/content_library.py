from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import chess.syzygy

from chess_camera_app.analysis.opening_book_builder import build_polyglot_book_from_tsvs


CONTENT_STORAGE_KEY = "content_storage_path"
OPENING_BOOK_MODE_KEY = "opening_book_mode"
OPENING_BOOK_PATH_KEY = "opening_book_path"
ENDGAME_TABLEBASE_MODE_KEY = "endgame_tablebase_mode"
ENDGAME_TABLEBASE_PATH_KEY = "endgame_tablebase_path"

DEFAULT_LIBRARY_DIRECTORY = Path("content_library")
OPENING_PACKAGE_ID = "lichess-opening-names"
TABLEBASE_PACKAGE_ID = "syzygy-3-4-5"

LICHESS_OPENINGS_COMMIT = "51b886249b9e418498d25b6e39b926c3de99c29a"
LICHESS_OPENING_SOURCE_BASE = (
    "https://raw.githubusercontent.com/lichess-org/chess-openings/"
    f"{LICHESS_OPENINGS_COMMIT}"
)
SYZYGY_WDL_INDEX = "https://tablebase.lichess.ovh/tables/standard/3-4-5-wdl/"
SYZYGY_DTZ_INDEX = "https://tablebase.lichess.ovh/tables/standard/3-4-5-dtz/"

ALLOWED_DOWNLOAD_HOSTS = {
    "raw.githubusercontent.com",
    "tablebase.lichess.ovh",
}
USER_AGENT = "ChessCamera/0.41 (+https://github.com/Scatter97/chess-camera-pgn)"
DOWNLOAD_CHUNK_SIZE = 1024 * 1024
MIN_TABLEBASE_FREE_BYTES = 1_250_000_000
TABLEBASE_FILENAME = re.compile(r"^[A-Za-z0-9]+v[A-Za-z0-9]+\.rtb[zw]$")


class ContentLibraryError(RuntimeError):
    pass


class DownloadCancelled(ContentLibraryError):
    pass


@dataclass(frozen=True)
class DownloadSource:
    name: str
    url: str
    git_blob_sha1: str | None = None
    sha256: str | None = None


@dataclass(frozen=True)
class ProgressInfo:
    stage: str
    label: str
    item_index: int
    item_count: int
    bytes_done: int
    bytes_total: int | None


ProgressCallback = Callable[[ProgressInfo], bool | None]


OPENING_SOURCES = (
    DownloadSource(
        "a.tsv",
        f"{LICHESS_OPENING_SOURCE_BASE}/a.tsv",
        git_blob_sha1="9f0a8ccf697dd4be1e6d67d24ed84f8eaa989d7d",
    ),
    DownloadSource(
        "b.tsv",
        f"{LICHESS_OPENING_SOURCE_BASE}/b.tsv",
        git_blob_sha1="c493779fdb2075493d1ff89c3df0a710a0b46c51",
    ),
    DownloadSource(
        "c.tsv",
        f"{LICHESS_OPENING_SOURCE_BASE}/c.tsv",
        git_blob_sha1="bc9dec3c7fef0fc0f4d040262ca127a6308cc96d",
    ),
    DownloadSource(
        "d.tsv",
        f"{LICHESS_OPENING_SOURCE_BASE}/d.tsv",
        git_blob_sha1="8a59e70b76a2709a9af8b2b1691353706fa27d3a",
    ),
    DownloadSource(
        "e.tsv",
        f"{LICHESS_OPENING_SOURCE_BASE}/e.tsv",
        git_blob_sha1="e146724353ddf4aca28f13b2a7757a5e513e864a",
    ),
)


def _load_config(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, TypeError, ValueError):
        return {}


def _save_config(path: Path, data: dict[str, object]) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def configured_library_root(config_path: Path) -> Path:
    data = _load_config(config_path)
    configured = data.get(CONTENT_STORAGE_KEY)
    if isinstance(configured, str) and configured.strip():
        return Path(configured).expanduser().resolve()
    return DEFAULT_LIBRARY_DIRECTORY.resolve()


def set_library_root(config_path: Path, directory: Path) -> Path:
    root = directory.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    data = _load_config(config_path)
    data[CONTENT_STORAGE_KEY] = str(root)
    _save_config(config_path, data)
    return root


def _package_directory(config_path: Path, category: str, package_id: str) -> Path:
    return configured_library_root(config_path) / category / package_id


def opening_package_directory(config_path: Path) -> Path:
    return _package_directory(config_path, "openings", OPENING_PACKAGE_ID)


def downloaded_opening_book(config_path: Path) -> Path | None:
    package = opening_package_directory(config_path)
    candidate = package / "lichess_opening_names.bin"
    manifest = package / "package.json"
    return candidate if candidate.is_file() and manifest.is_file() else None


def tablebase_package_directory(config_path: Path) -> Path:
    return _package_directory(config_path, "tablebases", TABLEBASE_PACKAGE_ID)


def downloaded_tablebase_directory(config_path: Path) -> Path | None:
    candidate = tablebase_package_directory(config_path)
    manifest = candidate / "package.json"
    if not candidate.is_dir() or not manifest.is_file():
        return None
    if not any(candidate.glob("*.rtbw")) or not any(candidate.glob("*.rtbz")):
        return None
    return candidate


def active_tablebase_directory(config_path: Path) -> tuple[Path | None, str]:
    data = _load_config(config_path)
    mode = data.get(ENDGAME_TABLEBASE_MODE_KEY)
    configured = data.get(ENDGAME_TABLEBASE_PATH_KEY)
    custom = Path(configured).expanduser() if isinstance(configured, str) else None
    downloaded = downloaded_tablebase_directory(config_path)

    if mode == "custom" and custom is not None and custom.is_dir():
        return custom, "custom"
    if mode == "downloaded" and downloaded is not None:
        return downloaded, "downloaded"
    if custom is not None and custom.is_dir():
        return custom, "custom"
    if downloaded is not None:
        return downloaded, "downloaded"
    return None, "none"


def activate_downloaded_opening(config_path: Path) -> bool:
    path = downloaded_opening_book(config_path)
    if path is None:
        return False
    data = _load_config(config_path)
    data[OPENING_BOOK_MODE_KEY] = "downloaded"
    data[OPENING_BOOK_PATH_KEY] = str(path)
    _save_config(config_path, data)
    return True


def activate_downloaded_tablebase(config_path: Path) -> bool:
    path = downloaded_tablebase_directory(config_path)
    if path is None:
        return False
    data = _load_config(config_path)
    data[ENDGAME_TABLEBASE_MODE_KEY] = "downloaded"
    _save_config(config_path, data)
    return True


def activate_custom_tablebase(config_path: Path, directory: Path) -> None:
    data = _load_config(config_path)
    data[ENDGAME_TABLEBASE_MODE_KEY] = "custom"
    data[ENDGAME_TABLEBASE_PATH_KEY] = str(directory.expanduser().resolve())
    _save_config(config_path, data)


def _validate_download_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_DOWNLOAD_HOSTS:
        raise ContentLibraryError(f"Download host is not allowed: {url}")


def _notify(progress: ProgressCallback | None, info: ProgressInfo) -> None:
    if progress is not None and progress(info) is False:
        raise DownloadCancelled("Download cancelled by the user.")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(DOWNLOAD_CHUNK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def git_blob_sha1(path: Path) -> str:
    size = path.stat().st_size
    digest = hashlib.sha1(usedforsecurity=False)
    digest.update(f"blob {size}\0".encode("ascii"))
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(DOWNLOAD_CHUNK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify_source(path: Path, source: DownloadSource) -> str:
    actual_sha256 = sha256_file(path)
    if source.sha256 and actual_sha256.lower() != source.sha256.lower():
        raise ContentLibraryError(f"SHA-256 verification failed for {source.name}.")
    if source.git_blob_sha1:
        actual_blob = git_blob_sha1(path)
        if actual_blob.lower() != source.git_blob_sha1.lower():
            raise ContentLibraryError(
                f"Pinned Git source verification failed for {source.name}."
            )
    return actual_sha256


def download_source(
    source: DownloadSource,
    destination: Path,
    *,
    progress: ProgressCallback | None = None,
    item_index: int = 1,
    item_count: int = 1,
    stage: str = "Downloading",
) -> str:
    """Download one file with HTTP Range resume and integrity checking."""
    _validate_download_url(source.url)
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.is_file():
        try:
            return _verify_source(destination, source)
        except ContentLibraryError:
            destination.unlink(missing_ok=True)

    partial = destination.with_suffix(destination.suffix + ".part")
    existing = partial.stat().st_size if partial.is_file() else 0
    headers = {"User-Agent": USER_AGENT}
    if existing:
        headers["Range"] = f"bytes={existing}-"

    request = urllib.request.Request(source.url, headers=headers)
    try:
        response = urllib.request.urlopen(request, timeout=45)
    except (OSError, urllib.error.URLError) as error:
        raise ContentLibraryError(f"Could not download {source.name}: {error}") from error

    with response:
        final_url = response.geturl()
        _validate_download_url(final_url)
        status = getattr(response, "status", None)
        append = existing > 0 and status == 206
        if existing and not append:
            existing = 0
            partial.unlink(missing_ok=True)

        content_length = response.headers.get("Content-Length")
        remaining = int(content_length) if content_length and content_length.isdigit() else None
        total = existing + remaining if remaining is not None else None
        completed = existing
        mode = "ab" if append else "wb"
        with partial.open(mode) as output:
            while True:
                block = response.read(DOWNLOAD_CHUNK_SIZE)
                if not block:
                    break
                output.write(block)
                completed += len(block)
                _notify(
                    progress,
                    ProgressInfo(
                        stage=stage,
                        label=source.name,
                        item_index=item_index,
                        item_count=item_count,
                        bytes_done=completed,
                        bytes_total=total,
                    ),
                )

    if total is not None and completed != total:
        raise ContentLibraryError(
            f"Download ended early for {source.name}: received {completed} of {total} bytes."
        )

    partial.replace(destination)
    try:
        return _verify_source(destination, source)
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def install_opening_package(
    config_path: Path,
    progress: ProgressCallback | None = None,
) -> Path:
    """Download the pinned CC0 Lichess opening-name dataset and build a book."""
    package = opening_package_directory(config_path)
    sources_directory = package / "sources"
    package.mkdir(parents=True, exist_ok=True)
    (package / "package.json").unlink(missing_ok=True)
    downloaded: list[Path] = []
    hashes: dict[str, str] = {}

    for index, source in enumerate(OPENING_SOURCES, start=1):
        path = sources_directory / source.name
        hashes[source.name] = download_source(
            source,
            path,
            progress=progress,
            item_index=index,
            item_count=len(OPENING_SOURCES),
            stage="Downloading opening data",
        )
        downloaded.append(path)

    _notify(
        progress,
        ProgressInfo(
            stage="Building opening book",
            label="Converting opening lines to Polyglot",
            item_index=len(OPENING_SOURCES),
            item_count=len(OPENING_SOURCES),
            bytes_done=0,
            bytes_total=None,
        ),
    )
    output = package / "lichess_opening_names.bin"
    record_count = build_polyglot_book_from_tsvs(downloaded, output)
    metadata = {
        "package_id": OPENING_PACKAGE_ID,
        "source": "lichess-org/chess-openings",
        "source_commit": LICHESS_OPENINGS_COMMIT,
        "license": "CC0-1.0",
        "installed_at": int(time.time()),
        "record_count": record_count,
        "files": hashes,
        "book_sha256": sha256_file(output),
    }
    (package / "package.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    activate_downloaded_opening(config_path)
    return output


def _index_filenames(index_url: str, extension: str) -> list[str]:
    _validate_download_url(index_url)
    request = urllib.request.Request(index_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            _validate_download_url(response.geturl())
            document = response.read().decode("utf-8", errors="replace")
    except (OSError, urllib.error.URLError) as error:
        raise ContentLibraryError(f"Could not read tablebase index: {error}") from error

    names: set[str] = set()
    for href in re.findall(r"href=[\"']([^\"']+)[\"']", document, flags=re.I):
        decoded = urllib.parse.unquote(href)
        parsed = urllib.parse.urlparse(decoded)
        if parsed.query or parsed.fragment:
            continue
        if "/" in parsed.path.strip("/"):
            continue
        name = parsed.path.strip("/")
        if name.endswith(extension) and TABLEBASE_FILENAME.fullmatch(name):
            names.add(name)
    if not names:
        raise ContentLibraryError(f"The tablebase server returned no {extension} files.")
    return sorted(names)


def _tablebase_sources() -> list[DownloadSource]:
    wdl = [
        DownloadSource(name, urllib.parse.urljoin(SYZYGY_WDL_INDEX, name))
        for name in _index_filenames(SYZYGY_WDL_INDEX, ".rtbw")
    ]
    dtz = [
        DownloadSource(name, urllib.parse.urljoin(SYZYGY_DTZ_INDEX, name))
        for name in _index_filenames(SYZYGY_DTZ_INDEX, ".rtbz")
    ]
    return [*wdl, *dtz]


def _validate_tablebase_directory(directory: Path) -> int:
    try:
        with chess.syzygy.Tablebase() as tablebase:
            count = int(tablebase.add_directory(str(directory)))
    except Exception as error:
        raise ContentLibraryError(
            f"Downloaded tablebase files could not be opened: {error}"
        ) from error
    if count < 2:
        raise ContentLibraryError("No usable WDL/DTZ tables were installed.")
    return count


def install_tablebase_package(
    config_path: Path,
    progress: ProgressCallback | None = None,
) -> Path:
    """Mirror the official Lichess 3/4/5-piece Syzygy directories locally."""
    package = tablebase_package_directory(config_path)
    package.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(package).free
    if free < MIN_TABLEBASE_FREE_BYTES:
        raise ContentLibraryError(
            "At least 1.25 GB of free storage is required for the 3/4/5-piece "
            "Syzygy package."
        )

    (package / "package.json").unlink(missing_ok=True)
    sources = _tablebase_sources()
    hashes: dict[str, str] = {}
    for index, source in enumerate(sources, start=1):
        hashes[source.name] = download_source(
            source,
            package / source.name,
            progress=progress,
            item_index=index,
            item_count=len(sources),
            stage="Downloading Syzygy tablebases",
        )

    table_count = _validate_tablebase_directory(package)
    metadata = {
        "package_id": TABLEBASE_PACKAGE_ID,
        "source": "tablebase.lichess.ovh",
        "license_note": "Syzygy-generated tablebase data may be freely redistributed.",
        "installed_at": int(time.time()),
        "table_count": table_count,
        "verification": (
            "HTTPS source, completed transfers, python-chess table loading, and "
            "locally recorded SHA-256 checksums"
        ),
        "files": hashes,
    }
    (package / "package.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    activate_downloaded_tablebase(config_path)
    return package


def verify_installed_package(
    config_path: Path,
    package_id: str,
    progress: ProgressCallback | None = None,
) -> tuple[bool, str]:
    if package_id == OPENING_PACKAGE_ID:
        package = opening_package_directory(config_path)
        metadata_path = package / "package.json"
        book = downloaded_opening_book(config_path)
        if book is None or not metadata_path.is_file():
            return False, "Opening package is not installed."
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            expected = str(metadata.get("book_sha256", ""))
            _notify(
                progress,
                ProgressInfo("Verifying", book.name, 1, 1, 0, book.stat().st_size),
            )
            actual = sha256_file(book)
            return actual == expected, (
                "Opening package verified."
                if actual == expected
                else "Opening package checksum does not match."
            )
        except (OSError, TypeError, ValueError) as error:
            return False, f"Could not verify opening package: {error}"

    if package_id == TABLEBASE_PACKAGE_ID:
        package = downloaded_tablebase_directory(config_path)
        if package is None:
            return False, "Tablebase package is not installed."
        metadata_path = package / "package.json"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            expected_files = metadata.get("files", {})
            if not isinstance(expected_files, dict) or not expected_files:
                return False, "Tablebase metadata is invalid."
            items = sorted(expected_files.items())
            for index, (name, expected) in enumerate(items, start=1):
                path = package / str(name)
                if not path.is_file() or sha256_file(path) != str(expected):
                    return False, f"Tablebase verification failed for {name}."
                _notify(
                    progress,
                    ProgressInfo(
                        "Verifying tablebases",
                        str(name),
                        index,
                        len(items),
                        path.stat().st_size,
                        path.stat().st_size,
                    ),
                )
            _validate_tablebase_directory(package)
            return True, "Tablebase package verified."
        except (OSError, TypeError, ValueError, ContentLibraryError) as error:
            return False, f"Could not verify tablebase package: {error}"

    return False, f"Unknown package: {package_id}"


def remove_package(config_path: Path, package_id: str) -> None:
    if package_id == OPENING_PACKAGE_ID:
        directory = opening_package_directory(config_path)
        data = _load_config(config_path)
        if data.get(OPENING_BOOK_MODE_KEY) == "downloaded":
            data[OPENING_BOOK_MODE_KEY] = "builtin"
            data.pop(OPENING_BOOK_PATH_KEY, None)
            _save_config(config_path, data)
    elif package_id == TABLEBASE_PACKAGE_ID:
        directory = tablebase_package_directory(config_path)
        data = _load_config(config_path)
        if data.get(ENDGAME_TABLEBASE_MODE_KEY) == "downloaded":
            data[ENDGAME_TABLEBASE_MODE_KEY] = "custom"
            _save_config(config_path, data)
    else:
        raise ContentLibraryError(f"Unknown package: {package_id}")

    if directory.exists():
        shutil.rmtree(directory)


def package_size(directory: Path) -> int:
    if not directory.exists():
        return 0
    return sum(path.stat().st_size for path in directory.rglob("*") if path.is_file())


def format_bytes(value: int) -> str:
    amount = float(max(0, value))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024.0 or unit == "TB":
            return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024.0
    return f"{amount:.1f} TB"
