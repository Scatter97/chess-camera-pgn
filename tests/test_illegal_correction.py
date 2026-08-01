import chess

from chess_camera_app.game import illegal_correction


def test_virtual_square_mapping() -> None:
    assert illegal_correction.virtual_square_at(50, 40) == chess.A8
    assert illegal_correction.virtual_square_at(50, 559) == chess.A1
    assert illegal_correction.virtual_square_at(569, 559) == chess.H1
    assert illegal_correction.virtual_square_at(10, 10) is None


def test_drag_and_validate_one_legal_move() -> None:
    base = chess.Board()
    edited = base.copy(stack=False)

    assert illegal_correction.apply_drag(edited, chess.E2, chess.E4)
    assert illegal_correction.matching_legal_move(base, edited) == chess.Move.from_uci(
        "e2e4"
    )


def test_castling_drag_applies_complete_position() -> None:
    base = chess.Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    edited = base.copy(stack=False)

    assert illegal_correction.apply_drag(edited, chess.E1, chess.G1)
    assert edited.piece_at(chess.F1) == chess.Piece(chess.ROOK, chess.WHITE)
    assert illegal_correction.matching_legal_move(base, edited) == chess.Move.from_uci(
        "e1g1"
    )
