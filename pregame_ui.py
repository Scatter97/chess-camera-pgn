from __future__ import annotations

from dataclasses import dataclass, replace

import cv2
import numpy as np

from builtin_clock import ClockSettings


SETUP_WIDTH = 1100
SETUP_HEIGHT = 920


@dataclass(frozen=True)
class GameSetup:
    white_name: str = "White"
    black_name: str = "Black"
    event_name: str = "Camera-recorded game"
    clock_source: str = "ocr"
    fast_mode: bool = False
    bullet_mode: bool = False
    accuracy_boost: bool = False
    white_camera_edge: str = "bottom"
    auto_accept: bool = False
    bottom_clock_is_white: bool = True
    manual_clock_switch: bool = False
    separate_time_controls: bool = False
    profile_name: str = "Default board"
    profile_samples: int = 0
    learning_enabled: bool = True
    engine_name: str = "Auto-detect"
    clock_settings: ClockSettings = ClockSettings()

    def pgn_headers(self) -> dict[str, str]:
        return {
            "Event": self.event_name.strip() or "Camera-recorded game",
            "White": self.white_name.strip() or "White",
            "Black": self.black_name.strip() or "Black",
        }


@dataclass(frozen=True)
class Button:
    action: str
    label: str
    x: int
    y: int
    width: int
    height: int
    active: bool = False
    enabled: bool = True

    def contains(self, x: int, y: int) -> bool:
        return (
            self.enabled
            and self.x <= x < self.x + self.width
            and self.y <= y < self.y + self.height
        )


def draw_text(
    image: np.ndarray,
    text: str,
    position: tuple[int, int],
    color: tuple[int, int, int] = (240, 240, 240),
    scale: float = 0.58,
    thickness: int = 1,
) -> None:
    cv2.putText(
        image,
        text,
        position,
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        (8, 8, 8),
        thickness + 3,
        cv2.LINE_AA,
    )
    cv2.putText(
        image,
        text,
        position,
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        color,
        thickness,
        cv2.LINE_AA,
    )


def draw_button(image: np.ndarray, button: Button) -> None:
    if not button.enabled:
        fill = (52, 55, 61)
        border = (88, 91, 98)
        text_color = (130, 130, 135)
    elif button.active:
        fill = (52, 132, 92)
        border = (120, 255, 170)
        text_color = (255, 255, 255)
    else:
        fill = (58, 63, 73)
        border = (115, 125, 142)
        text_color = (240, 240, 240)

    cv2.rectangle(
        image,
        (button.x, button.y),
        (button.x + button.width, button.y + button.height),
        fill,
        -1,
    )
    cv2.rectangle(
        image,
        (button.x, button.y),
        (button.x + button.width, button.y + button.height),
        border,
        2,
    )
    (text_width, text_height), _ = cv2.getTextSize(
        button.label, cv2.FONT_HERSHEY_SIMPLEX, 0.53, 1
    )
    text_x = button.x + max(8, (button.width - text_width) // 2)
    text_y = button.y + (button.height + text_height) // 2
    draw_text(image, button.label, (text_x, text_y), text_color, 0.53)


def clicked_action(buttons: list[Button], x: int, y: int) -> str | None:
    for button in buttons:
        if button.contains(x, y):
            return button.action
    return None


def _clock_label(seconds: float) -> str:
    safe = max(0, int(seconds))
    return f"{safe // 60}:{safe % 60:02d}"


def _text_field(
    image: np.ndarray,
    buttons: list[Button],
    action: str,
    label: str,
    value: str,
    y: int,
    focused: bool,
) -> None:
    draw_text(image, label, (42, y - 9), (165, 175, 190), 0.48)
    field = Button(action, "", 40, y, 490, 44, active=focused)
    buttons.append(field)
    cv2.rectangle(
        image,
        (field.x, field.y),
        (field.x + field.width, field.y + field.height),
        (46, 50, 58),
        -1,
    )
    cv2.rectangle(
        image,
        (field.x, field.y),
        (field.x + field.width, field.y + field.height),
        (120, 255, 170) if focused else (100, 110, 125),
        2,
    )
    visible = value[-34:]
    draw_text(image, visible or "Click and type", (54, y + 29), scale=0.58)
    if focused:
        text_width = cv2.getTextSize(
            visible, cv2.FONT_HERSHEY_SIMPLEX, 0.58, 1
        )[0][0]
        cv2.line(
            image,
            (56 + text_width, y + 10),
            (56 + text_width, y + 34),
            (120, 255, 170),
            2,
        )


def render_setup_screen(
    setup: GameSetup,
    focused_field: str | None,
    camera_preview: np.ndarray | None = None,
    message: str = "",
) -> tuple[np.ndarray, list[Button]]:
    view = np.zeros((SETUP_HEIGHT, SETUP_WIDTH, 3), dtype=np.uint8)
    view[:] = (28, 31, 37)
    buttons: list[Button] = []

    draw_text(view, "Chess Camera Setup", (40, 45), (100, 220, 255), 0.94, 2)
    draw_text(view, "1  Calibration", (610, 38), (145, 155, 170), 0.52)
    draw_text(view, "2  Game settings", (755, 38), (120, 255, 170), 0.52)
    draw_text(view, "3  Play", (940, 38), (145, 155, 170), 0.52)
    cv2.line(view, (40, 63), (1060, 63), (75, 80, 90), 1)

    draw_text(view, "Player information", (40, 96), (100, 220, 255), 0.68)
    _text_field(
        view,
        buttons,
        "focus_white",
        "WHITE PLAYER",
        setup.white_name,
        122,
        focused_field == "white",
    )
    _text_field(
        view,
        buttons,
        "focus_black",
        "BLACK PLAYER",
        setup.black_name,
        196,
        focused_field == "black",
    )
    _text_field(
        view,
        buttons,
        "focus_event",
        "EVENT",
        setup.event_name,
        270,
        focused_field == "event",
    )

    draw_text(view, "Game options", (40, 354), (100, 220, 255), 0.68)
    option_rows = [
        (
            "Clock",
            [
                Button(
                    "clock_ocr",
                    "Lichess OCR",
                    155,
                    372,
                    175,
                    42,
                    setup.clock_source == "ocr",
                ),
                Button(
                    "clock_builtin",
                    "Built-in",
                    345,
                    372,
                    175,
                    42,
                    setup.clock_source == "builtin",
                ),
            ],
        ),
        (
            "Detection",
            [
                Button(
                    "mode_normal",
                    "Normal",
                    155,
                    426,
                    112,
                    42,
                    not setup.fast_mode and not setup.bullet_mode,
                ),
                Button(
                    "mode_fast",
                    "Fast",
                    281,
                    426,
                    112,
                    42,
                    setup.fast_mode,
                ),
                Button(
                    "mode_bullet",
                    "Bullet",
                    407,
                    426,
                    113,
                    42,
                    setup.bullet_mode,
                ),
            ],
        ),
        (
            "Confirmation",
            [
                Button(
                    "auto_toggle",
                    "Automatic" if setup.auto_accept else "Manual",
                    155,
                    480,
                    365,
                    42,
                    setup.auto_accept,
                    not setup.bullet_mode,
                )
            ],
        ),
        (
            "OCR sides",
            [
                Button(
                    "mapping_bottom",
                    "Bottom = White",
                    155,
                    534,
                    175,
                    42,
                    setup.bottom_clock_is_white,
                    setup.clock_source == "ocr",
                ),
                Button(
                    "mapping_top",
                    "Top = White",
                    345,
                    534,
                    175,
                    42,
                    not setup.bottom_clock_is_white,
                    setup.clock_source == "ocr",
                ),
            ],
        ),
        (
            "Clock switch",
            [
                Button(
                    "clock_switch_camera",
                    "Camera automatic",
                    155,
                    588,
                    175,
                    42,
                    not setup.manual_clock_switch,
                    setup.clock_source == "builtin",
                ),
                Button(
                    "clock_switch_manual",
                    "Player keys A / L",
                    345,
                    588,
                    175,
                    42,
                    setup.manual_clock_switch,
                    setup.clock_source == "builtin",
                ),
            ],
        ),
    ]
    for row, row_buttons in option_rows:
        draw_text(view, row, (42, row_buttons[0].y + 27), scale=0.48)
        for button in row_buttons:
            buttons.append(button)
            draw_button(view, button)

    draw_text(view, "Time control", (600, 96), (100, 220, 255), 0.68)
    enabled = setup.clock_source == "builtin"
    advanced_button = Button(
        "advanced_clock_toggle",
        (
            "Advanced: separate clocks"
            if not setup.separate_time_controls
            else "Use one shared clock"
        ),
        800,
        74,
        260,
        38,
        setup.separate_time_controls,
        enabled,
    )
    buttons.append(advanced_button)
    draw_button(view, advanced_button)
    if setup.separate_time_controls:
        clock_rows = [
            (
                "White",
                setup.clock_settings.white_initial_seconds,
                setup.clock_settings.white_increment_seconds,
                128,
                "white",
            ),
            (
                "Black",
                setup.clock_settings.black_initial_seconds,
                setup.clock_settings.black_increment_seconds,
                294,
                "black",
            ),
        ]
    else:
        clock_rows = [
            (
                "Both players",
                setup.clock_settings.white_initial_seconds,
                setup.clock_settings.white_increment_seconds,
                150,
                "shared",
            )
        ]
    for player, initial, increment, y, prefix in clock_rows:
        draw_text(view, player, (600, y), (235, 235, 235), 0.65)
        draw_text(
            view,
            f"{_clock_label(initial)}  + {int(increment)} sec",
            (890, y),
            (120, 255, 170) if enabled else (135, 140, 150),
            0.61,
        )
        draw_text(view, "Starting time", (600, y + 35), (165, 175, 190), 0.46)
        controls = [
            (f"{prefix}_minus60", "-1m"),
            (f"{prefix}_minus10", "-10s"),
            (f"{prefix}_plus10", "+10s"),
            (f"{prefix}_plus60", "+1m"),
        ]
        for index, (action, label) in enumerate(controls):
            button = Button(
                action,
                label,
                600 + index * 112,
                y + 48,
                100,
                39,
                enabled=enabled,
            )
            buttons.append(button)
            draw_button(view, button)
        draw_text(view, "Increment", (600, y + 114), (165, 175, 190), 0.46)
        for index, (action, label) in enumerate(
            [(f"{prefix}_inc_minus", "-1s"), (f"{prefix}_inc_plus", "+1s")]
        ):
            button = Button(
                action,
                label,
                720 + index * 130,
                y + 96,
                115,
                39,
                enabled=enabled,
            )
            buttons.append(button)
            draw_button(view, button)

    if camera_preview is not None:
        preview = cv2.resize(camera_preview, (172, 97))
        view[483:580, 600:772] = preview
        cv2.rectangle(view, (600, 483), (772, 580), (100, 110, 125), 2)
        draw_text(view, "Live camera", (785, 518), (165, 175, 190), 0.48)
        draw_text(view, "Calibration saved", (785, 546), (120, 255, 170), 0.48)

    draw_text(view, "Accuracy", (600, 621), scale=0.48)
    accuracy_button = Button(
        "accuracy_toggle",
        "Boost ON - 3 frames" if setup.accuracy_boost else "Boost OFF",
        720,
        594,
        340,
        42,
        setup.accuracy_boost,
        not setup.bullet_mode,
    )
    buttons.append(accuracy_button)
    draw_button(view, accuracy_button)

    orientation_buttons = [
        Button(
            f"white_edge_{edge}",
            edge.title(),
            155 + index * 92,
            642,
            84,
            42,
            setup.white_camera_edge == edge,
        )
        for index, edge in enumerate(("bottom", "top", "left", "right"))
    ]
    draw_text(view, "White side", (42, 669), scale=0.48)
    for button in orientation_buttons:
        buttons.append(button)
        draw_button(view, button)
    draw_text(
        view,
        "Select where White appears in the camera image.",
        (600, 669),
        (165, 175, 190),
        0.46,
    )

    draw_text(view, "Board profile", (42, 733), scale=0.48)
    draw_text(
        view,
        f"{setup.profile_name[:22]}  ({setup.profile_samples} samples)",
        (155, 706),
        (120, 255, 170),
        0.52,
    )
    profile_buttons = [
        Button("profile_previous", "< Previous", 155, 722, 112, 42),
        Button("profile_next", "Next >", 278, 722, 100, 42),
        Button("profile_new", "New board", 389, 722, 115, 42),
        Button("profile_train", "Train moves", 515, 722, 140, 42),
        Button(
            "learning_toggle",
            "Learning ON" if setup.learning_enabled else "Learning OFF",
            670,
            722,
            170,
            42,
            setup.learning_enabled,
        ),
    ]
    for button in profile_buttons:
        buttons.append(button)
        draw_button(view, button)
    draw_text(
        view,
        f"Engine: {setup.engine_name[:22]}",
        (855, 706),
        (120, 220, 255),
        0.40,
    )
    engine_button = Button(
        "select_engine",
        "Choose engine...",
        855,
        722,
        205,
        42,
    )
    buttons.append(engine_button)
    draw_button(view, engine_button)
    draw_text(
        view,
        "Profiles keep separate calibration and learn from confirmed moves.",
        (155, 788),
        (165, 175, 190),
        0.43,
    )

    calibration_buttons = [
        Button("calibrate_board", "Recalibrate board", 40, 850, 205, 48),
        Button("calibrate_phone", "Recalibrate phone", 260, 850, 205, 48),
        Button("verify_grid", "Check all 64 squares", 480, 850, 240, 48),
    ]
    for button in calibration_buttons:
        buttons.append(button)
        draw_button(view, button)

    start_button = Button("start", "START GAME", 820, 840, 240, 58, active=True)
    buttons.append(start_button)
    draw_button(view, start_button)
    if message:
        draw_text(view, message[:60], (600, 822), (120, 220, 255), 0.46)

    return view, buttons


def apply_setup_action(setup: GameSetup, action: str) -> GameSetup:
    if action == "clock_ocr":
        return replace(setup, clock_source="ocr")
    if action == "clock_builtin":
        return replace(setup, clock_source="builtin")
    if action == "mode_normal":
        return replace(setup, fast_mode=False, bullet_mode=False)
    if action == "mode_fast":
        return replace(setup, fast_mode=True, bullet_mode=False)
    if action == "mode_bullet":
        return replace(
            setup,
            fast_mode=False,
            bullet_mode=True,
            accuracy_boost=False,
            auto_accept=True,
        )
    if action == "accuracy_toggle" and not setup.bullet_mode:
        return replace(setup, accuracy_boost=not setup.accuracy_boost)
    if action.startswith("white_edge_"):
        edge = action.removeprefix("white_edge_")
        if edge in {"bottom", "top", "left", "right"}:
            return replace(setup, white_camera_edge=edge)
    if action == "auto_toggle" and not setup.bullet_mode:
        return replace(setup, auto_accept=not setup.auto_accept)
    if action == "mapping_bottom":
        return replace(setup, bottom_clock_is_white=True)
    if action == "mapping_top":
        return replace(setup, bottom_clock_is_white=False)
    if action == "clock_switch_camera" and setup.clock_source == "builtin":
        return replace(setup, manual_clock_switch=False)
    if action == "clock_switch_manual" and setup.clock_source == "builtin":
        return replace(setup, manual_clock_switch=True)
    if action == "advanced_clock_toggle" and setup.clock_source == "builtin":
        if setup.separate_time_controls:
            shared = ClockSettings(
                setup.clock_settings.white_initial_seconds,
                setup.clock_settings.white_initial_seconds,
                setup.clock_settings.white_increment_seconds,
                setup.clock_settings.white_increment_seconds,
            )
            return replace(
                setup,
                separate_time_controls=False,
                clock_settings=shared,
            )
        return replace(setup, separate_time_controls=True)
    if action == "learning_toggle":
        return replace(setup, learning_enabled=not setup.learning_enabled)

    settings = setup.clock_settings
    values = {
        "white_initial_seconds": settings.white_initial_seconds,
        "black_initial_seconds": settings.black_initial_seconds,
        "white_increment_seconds": settings.white_increment_seconds,
        "black_increment_seconds": settings.black_increment_seconds,
    }
    adjustments = {
        "shared_minus60": ("shared_initial_seconds", -60),
        "shared_minus10": ("shared_initial_seconds", -10),
        "shared_plus10": ("shared_initial_seconds", 10),
        "shared_plus60": ("shared_initial_seconds", 60),
        "shared_inc_minus": ("shared_increment_seconds", -1),
        "shared_inc_plus": ("shared_increment_seconds", 1),
        "white_minus60": ("white_initial_seconds", -60),
        "white_minus10": ("white_initial_seconds", -10),
        "white_plus10": ("white_initial_seconds", 10),
        "white_plus60": ("white_initial_seconds", 60),
        "black_minus60": ("black_initial_seconds", -60),
        "black_minus10": ("black_initial_seconds", -10),
        "black_plus10": ("black_initial_seconds", 10),
        "black_plus60": ("black_initial_seconds", 60),
        "white_inc_minus": ("white_increment_seconds", -1),
        "white_inc_plus": ("white_increment_seconds", 1),
        "black_inc_minus": ("black_increment_seconds", -1),
        "black_inc_plus": ("black_increment_seconds", 1),
    }
    if action not in adjustments or setup.clock_source != "builtin":
        return setup

    field, amount = adjustments[action]
    if field == "shared_initial_seconds":
        value = min(
            10800,
            max(1, values["white_initial_seconds"] + amount),
        )
        values["white_initial_seconds"] = value
        values["black_initial_seconds"] = value
        return replace(setup, clock_settings=ClockSettings(**values))
    if field == "shared_increment_seconds":
        value = min(
            60,
            max(0, values["white_increment_seconds"] + amount),
        )
        values["white_increment_seconds"] = value
        values["black_increment_seconds"] = value
        return replace(setup, clock_settings=ClockSettings(**values))
    if not setup.separate_time_controls:
        return setup
    maximum = 60 if "increment" in field else 10800
    minimum = 0 if "increment" in field else 1
    values[field] = min(maximum, max(minimum, values[field] + amount))
    return replace(setup, clock_settings=ClockSettings(**values))


def update_text_field(setup: GameSetup, field: str, key: int) -> GameSetup:
    attribute = {
        "white": "white_name",
        "black": "black_name",
        "event": "event_name",
    }.get(field)
    if attribute is None:
        return setup

    value = getattr(setup, attribute)
    if key in (8, 127):
        value = value[:-1]
    elif 32 <= key <= 126 and len(value) < 40:
        value += chr(key)
    return replace(setup, **{attribute: value})
