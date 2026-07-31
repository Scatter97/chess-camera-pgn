from __future__ import annotations

from types import ModuleType


PROMOTION_ACTIONS = {
    "promote_q",
    "promote_r",
    "promote_b",
    "promote_n",
}


def is_inline_promotion_action(action: object) -> bool:
    return isinstance(action, str) and action in PROMOTION_ACTIONS


def install(target: ModuleType) -> None:
    """Hide the permanent promotion row; the modal chooser remains available."""
    if getattr(target, "_promotion_popup_only_installed", False):
        return

    original_draw_button = target.draw_button
    original_clicked_action = target.clicked_action

    def draw_button(image: object, button: object) -> None:
        if is_inline_promotion_action(getattr(button, "action", None)):
            return
        original_draw_button(image, button)

    def clicked_action(
        buttons: list[object],
        x: int,
        y: int,
    ) -> str | None:
        action = original_clicked_action(buttons, x, y)
        return None if is_inline_promotion_action(action) else action

    target.draw_button = draw_button
    target.clicked_action = clicked_action
    target._promotion_popup_only_installed = True
