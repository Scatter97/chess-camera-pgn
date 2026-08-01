from __future__ import annotations

from chess_camera_app.game import promotion_popup


def test_inline_promotion_actions_are_hidden() -> None:
    assert promotion_popup.is_inline_promotion_action("promote_q")
    assert promotion_popup.is_inline_promotion_action("promote_r")
    assert promotion_popup.is_inline_promotion_action("promote_b")
    assert promotion_popup.is_inline_promotion_action("promote_n")


def test_modal_promotion_actions_remain_visible() -> None:
    assert not promotion_popup.is_inline_promotion_action("queen")
    assert not promotion_popup.is_inline_promotion_action("rook")
    assert not promotion_popup.is_inline_promotion_action("bishop")
    assert not promotion_popup.is_inline_promotion_action("knight")
