from pathlib import Path

import chess

from chess_camera_app.analysis.opening_explorer import opening_name


def test_opening_name_uses_the_longest_matching_line(tmp_path: Path) -> None:
    source = tmp_path / "openings.tsv"
    source.write_text(
        "name\tuci\nKing's Pawn\te2e4\nItalian Game\te2e4 e7e5 g1f3 b8c6 f1c4\n",
        encoding="utf-8",
    )
    board = chess.Board()
    for move in ("e2e4", "e7e5", "g1f3", "b8c6", "f1c4"):
        board.push_uci(move)
    assert opening_name(board, source) == "Italian Game"
