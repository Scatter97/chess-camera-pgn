from __future__ import annotations

from pathlib import Path

import chess

import endgame_explorer as explorer


class _FakeTablebase:
    def probe_wdl(self, board: chess.Board) -> int:
        return 2

    def probe_dtz(self, board: chess.Board) -> int:
        return 7

    def probe_root(self, board: chess.Board) -> list[tuple[chess.Move, int, int]]:
        return [
            (chess.Move.from_uci("e2e3"), 2, 7),
            (chess.Move.from_uci("e2e4"), 1, 2),
        ]


def test_tablebase_folder_requires_syzygy_files(tmp_path: Path) -> None:
    assert explorer._contains_tablebase_files(tmp_path) is False

    (tmp_path / "KQvK.rtbw").touch()

    assert explorer._contains_tablebase_files(tmp_path) is False

    (tmp_path / "KQvK.rtbz").touch()

    assert explorer._contains_tablebase_files(tmp_path) is True


def test_candidate_position_rejects_castling_and_eight_pieces() -> None:
    starting_position = chess.Board()
    covered, message = explorer._position_is_covered_candidate(starting_position)

    assert covered is False
    assert message == "Syzygy supports positions with up to 7 pieces."

    castling_position = chess.Board("7k/8/8/8/8/8/8/R3K2R w KQ - 0 1")
    covered, message = explorer._position_is_covered_candidate(castling_position)

    assert covered is False
    assert message == "Syzygy tablebases do not cover positions with castling rights."


def test_probe_position_normalizes_and_orders_root_moves() -> None:
    board = chess.Board("8/8/8/8/8/8/4K3/7k w - - 0 1")

    result = explorer.probe_position(_FakeTablebase(), board)

    assert result.wdl == 2
    assert result.dtz == 7
    assert [item.move.uci() for item in result.moves] == ["e2e3", "e2e4"]


def test_fen_loading_rejects_invalid_positions() -> None:
    board, message = explorer._fen_board("not a FEN")

    assert board is None
    assert message is not None
