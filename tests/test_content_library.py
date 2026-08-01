from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import chess
import chess.polyglot

from chess_camera_app.content import content_library
from chess_camera_app.analysis.opening_book_builder import build_polyglot_book_from_tsvs


class _FakeResponse:
    def __init__(
        self,
        data: bytes,
        url: str,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._stream = io.BytesIO(data)
        self._url = url
        self.status = status
        self.headers = headers or {"Content-Length": str(len(data))}

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def geturl(self) -> str:
        return self._url

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def _git_blob_sha(data: bytes) -> str:
    digest = hashlib.sha1(usedforsecurity=False)
    digest.update(f"blob {len(data)}\0".encode("ascii"))
    digest.update(data)
    return digest.hexdigest()


def test_builder_combines_pgn_and_uci_tsv_files(tmp_path: Path) -> None:
    pgn_source = tmp_path / "a.tsv"
    pgn_source.write_text(
        "eco\tname\tpgn\n"
        "A00\tKing's Pawn Game\t1. e4 e5 2. Nf3\n",
        encoding="utf-8",
    )
    uci_source = tmp_path / "b.tsv"
    uci_source.write_text(
        "eco\tname\tuci\n"
        "B00\tSicilian Defense\te2e4 c7c5 g1f3\n",
        encoding="utf-8",
    )
    output = tmp_path / "expanded.bin"

    count = build_polyglot_book_from_tsvs([pgn_source, uci_source], output)

    assert count >= 4
    with chess.polyglot.open_reader(str(output)) as reader:
        root_moves = {entry.move for entry in reader.find_all(chess.Board())}
    assert chess.Move.from_uci("e2e4") in root_moves


def test_library_root_and_downloaded_opening_activation(tmp_path: Path) -> None:
    config = tmp_path / "camera_config.json"
    root = tmp_path / "large-data"
    content_library.set_library_root(config, root)
    package = content_library.opening_package_directory(config)
    package.mkdir(parents=True)
    book = package / "lichess_opening_names.bin"
    book.write_bytes(b"book")
    (package / "package.json").write_text("{}", encoding="utf-8")

    assert content_library.activate_downloaded_opening(config) is True
    saved = json.loads(config.read_text(encoding="utf-8"))
    assert Path(saved[content_library.CONTENT_STORAGE_KEY]) == root.resolve()
    assert saved[content_library.OPENING_BOOK_MODE_KEY] == "downloaded"
    assert Path(saved[content_library.OPENING_BOOK_PATH_KEY]) == book


def test_incomplete_tablebase_package_is_not_activated(tmp_path: Path) -> None:
    config = tmp_path / "camera_config.json"
    content_library.set_library_root(config, tmp_path / "data")
    package = content_library.tablebase_package_directory(config)
    package.mkdir(parents=True)
    (package / "KQvK.rtbw").write_bytes(b"incomplete")
    (package / "KQvK.rtbz").write_bytes(b"incomplete")

    assert content_library.downloaded_tablebase_directory(config) is None
    assert content_library.activate_downloaded_tablebase(config) is False


def test_download_source_verifies_pinned_git_blob(
    tmp_path: Path,
    monkeypatch,
) -> None:
    data = b"eco\tname\tpgn\nA00\tTest\t1. e4\n"
    url = "https://raw.githubusercontent.com/example/project/commit/a.tsv"

    def fake_urlopen(_request, timeout: int = 0):
        assert timeout == 45
        return _FakeResponse(data, url)

    monkeypatch.setattr(content_library.urllib.request, "urlopen", fake_urlopen)
    source = content_library.DownloadSource(
        "a.tsv",
        url,
        git_blob_sha1=_git_blob_sha(data),
    )
    destination = tmp_path / "a.tsv"

    actual_sha256 = content_library.download_source(source, destination)

    assert destination.read_bytes() == data
    assert actual_sha256 == hashlib.sha256(data).hexdigest()


def test_tablebase_index_rejects_nested_and_unexpected_links(monkeypatch) -> None:
    url = content_library.SYZYGY_WDL_INDEX
    html = b'''<html><body>
        <a href="KQvK.rtbw">KQvK</a>
        <a href="KRvK.rtbw">KRvK</a>
        <a href="../escape.rtbw">escape</a>
        <a href="folder/KPvK.rtbw">nested</a>
        <a href="KQvK.rtbz">wrong extension</a>
        <a href="notes.txt">notes</a>
    </body></html>'''

    def fake_urlopen(_request, timeout: int = 0):
        assert timeout == 45
        return _FakeResponse(html, url)

    monkeypatch.setattr(content_library.urllib.request, "urlopen", fake_urlopen)

    assert content_library._index_filenames(url, ".rtbw") == [
        "KQvK.rtbw",
        "KRvK.rtbw",
    ]


def test_release_wires_data_manager_and_version() -> None:
    startup = Path("chess_camera.py").read_text(encoding="utf-8")
    version = Path("chess_camera_app/core/version.py").read_text(encoding="utf-8")

    assert "content_manager_ui.install(app, navigation)" in startup
    assert 'APP_VERSION = "0.41.1"' in version
