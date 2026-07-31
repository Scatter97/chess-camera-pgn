import chess

import manual_board_sync


def test_manual_sync_applies_legal_drag() -> None:
    board = chess.Board()

    move = manual_board_sync.apply_legal_drag(board, chess.E2, chess.E4)

    assert move == chess.Move.from_uci("e2e4")
    assert board.piece_at(chess.E4) == chess.Piece(chess.PAWN, chess.WHITE)


def test_manual_sync_rejects_illegal_drag() -> None:
    board = chess.Board()

    move = manual_board_sync.apply_legal_drag(board, chess.E2, chess.E5)

    assert move is None
    assert board == chess.Board()


def test_manual_sync_supports_multiple_missed_moves() -> None:
    board = chess.Board()

    first = manual_board_sync.apply_legal_drag(board, chess.E2, chess.E4)
    second = manual_board_sync.apply_legal_drag(board, chess.E7, chess.E5)

    assert first == chess.Move.from_uci("e2e4")
    assert second == chess.Move.from_uci("e7e5")
    assert board.turn == chess.WHITE


def test_manual_sync_uses_selected_promotion_piece() -> None:
    board = chess.Board("8/P7/8/8/8/8/8/k6K w - - 0 1")

    move = manual_board_sync.apply_legal_drag(
        board,
        chess.A7,
        chess.A8,
        lambda: chess.KNIGHT,
    )

    assert move == chess.Move.from_uci("a7a8n")
    assert board.piece_at(chess.A8) == chess.Piece(chess.KNIGHT, chess.WHITE)
