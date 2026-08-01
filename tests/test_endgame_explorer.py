from __future__ import annotations

from pathlib import Path

import chess

from chess_camera_app.analysis import endgame_explorer as explorer


class _FakeTablebase:
    def probe_wdl(self, board: chess.Board) -> int:
        return 2

    def probe_dtz(self, board: chess.Board) -> int:
        return 7


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


def test_probe_position_derives_root_moves_without_probe_root() -> None:
    board = chess.Board("8/8/8/8/8/8/4K3/7k w - - 0 1")

    result = explorer.probe_position(_FakeTablebase(), board)

    assert result.wdl == 2
    assert result.dtz == 7
    assert result.moves
    assert all(item.wdl == -2 for item in result.moves)


def test_fen_loading_rejects_invalid_positions() -> None:
    board, message = explorer._fen_board("not a FEN")

    assert board is None
    assert message is not None


def test_result_label_reports_the_winning_colour() -> None:
    white_to_move = chess.Board("8/8/8/8/8/8/4K3/7k w - - 0 1")
    black_to_move = chess.Board("8/8/8/8/8/8/4K3/7k b - - 0 1")

    assert explorer._result_label(white_to_move, 2) == "WHITE WINS"
    assert explorer._result_label(white_to_move, -2) == "BLACK WINS"
    assert explorer._result_label(black_to_move, 2) == "BLACK WINS"
    assert explorer._result_label(white_to_move, 0) == "DRAW"


def test_position_editor_drag_places_moves_and_removes_pieces() -> None:
    board = chess.Board.empty()
    white_king = chess.Piece(chess.KING, chess.WHITE)

    explorer._apply_editor_drag(board, white_king, None, chess.E1)
    assert board.piece_at(chess.E1) == white_king

    explorer._apply_editor_drag(board, white_king, chess.E1, chess.E2)
    assert board.piece_at(chess.E1) is None
    assert board.piece_at(chess.E2) == white_king

    explorer._apply_editor_drag(board, white_king, chess.E2, None)
    assert board.piece_at(chess.E2) is None
