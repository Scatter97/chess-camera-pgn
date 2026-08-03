from __future__ import annotations

import cv2
import numpy as np

from chess_camera_app.core import app
from chess_camera_app.core import app_navigation as navigation
from chess_camera_app.calibration import calibration_cleanup
from chess_camera_app.calibration import calibration_ui
from chess_camera_app.calibration import camera_advanced
from chess_camera_app.analysis import chess960_generator
from chess_camera_app.content import content_manager_ui
from chess_camera_app.analysis import endgame_explorer
from chess_camera_app.ui import feature_settings
# Try to import the new Qt based UI. If unavailable we fall back to the original OpenCV UI.
try:
    from chess_camera_app.ui.qt_ui import QtApp
    _HAS_QT_UI = True
except Exception:  # pragma: no cover
    _HAS_QT_UI = False
from chess_camera_app.ui import game_history
from chess_camera_app.game import game_session
from chess_camera_app.game import bot_games
from chess_camera_app.detection import local64_occlusion_fix
from chess_camera_app.detection import local_detection
from chess_camera_app.detection import local_detection_runtime
from chess_camera_app.ui import multi_move_settings
from chess_camera_app.analysis import opening_explorer
from chess_camera_app.ui import piece_theme_system
from chess_camera_app.ui import pregame_ui
from chess_camera_app.game import promotion_popup
from chess_camera_app.ui import review_ui_fix
from chess_camera_app.runtime import runtime_0397_patch
from chess_camera_app.runtime import runtime_multi_move_patch
from chess_camera_app.ui import training_settings
from chess_camera_app.ui import ui_support as ui
from chess_camera_app.ui import visual_system
from chess_camera_app.ui.pregame_ui import Button
from chess_camera_app.core.version import APP_VERSION, VERSION_LABEL


CAMERA_CONFIG_KEYS = (
    "camera_index",
    "camera_name",
    "detection_fps",
    "detection_resolution",
    "camera_debug_overlay",
    "local_detection_beta",
    "local_detection_sensitivity",
    "advanced_auto_accept_enabled",
    "advanced_auto_accept_threshold",
    "piece_pack",
    "sound_pack",
    "piece_sounds_enabled",
    "move_highlights_enabled",
    "content_storage_path",
    "opening_book_mode",
    "opening_book_path",
    "endgame_tablebase_mode",
    "endgame_tablebase_path",
)


def home_screen() -> str:
    """Show a scalable feature grid with room for future tools."""
    window = VERSION_LABEL
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 1120, 760)

    buttons = [
        Button("start", "RECORD OTB GAME", 55, 220, 310, 92, active=True),
        Button("history", "GAME HISTORY", 405, 220, 310, 92),
        Button("chess960", "CHESS960", 755, 220, 310, 92),
        Button("opening", "OPENING EXPLORER", 55, 405, 310, 92),
        Button("endgame", "ENDGAME EXPLORER", 405, 405, 310, 92),
        Button("settings", "SETTINGS & LIBRARIES", 755, 405, 310, 92),
        Button("virtual_bot", "VIRTUAL BOT GAME", 230, 575, 310, 72),
        Button("otb_bot", "OTB BOT GAME", 580, 575, 310, 72),
        Button("exit", "EXIT KNIGHTBOARD", 430, 684, 260, 44),
    ]
    queue: list[str] = []

    def mouse(event: int, x: int, y: int, _flags: int, _data: object) -> None:
        if event == cv2.EVENT_LBUTTONUP:
            action = pregame_ui.clicked_action(buttons, x, y)
            if action:
                queue.append(action)

    cv2.setMouseCallback(window, mouse)
    while True:
        view = visual_system.canvas(760, 1120)
        visual_system.brand_header(view, "Your offline chess studio", VERSION_LABEL)
        ui._put(view, "Play, record, analyse, and explore — all locally.", (57, 124), visual_system.TEXT, 0.69, 2)
        ui._put(
            view,
            "Your games, camera data, engines and chess libraries stay on your computer.",
            (57, 158), visual_system.MUTED, 0.48,
        )

        for left, top, right, bottom in ((35, 195, 385, 350), (385, 195, 735, 350),
                                         (735, 195, 1085, 350), (35, 380, 385, 535),
                                         (385, 380, 735, 535), (735, 380, 1085, 535)):
            visual_system.card(view, left, top, right, bottom)

        for button in buttons:
            pregame_ui.draw_button(view, button)

        descriptions = [
            ("Camera recording, clocks and PGN", 75, 337),
            ("Saved games, accuracy and review", 425, 337),
            ("Generate a legal random start", 775, 337),
            ("Names, moves and local theory", 75, 522),
            ("Local Syzygy tablebase analysis", 425, 522),
            ("Appearance, engine and data", 775, 522),
        ]
        for text, x, y in descriptions:
            ui._put(view, text, (x, y), visual_system.MUTED, 0.40)

        ui._put(
            view,
            "Knightboard v0.50  •  Local-first chess tools",
            (300, 725),
            visual_system.MUTED,
            0.42,
        )

        cv2.imshow(window, view)
        key = cv2.waitKey(25) & 0xFF
        action = queue.pop(0) if queue else None
        if action in {
            "start",
            "history",
            "chess960",
            "opening",
            "endgame",
            "settings",
            "virtual_bot",
            "otb_bot",
            "exit",
        }:
            cv2.destroyWindow(window)
            return action
        if key == 27:
            cv2.destroyWindow(window)
            return "exit"
        try:
            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                return "exit"
        except cv2.error:
            return "exit"


def install_camera_config_persistence() -> None:
    """Keep camera, detection, theme, sound, and library settings."""
    original_save = app.save_config

    def save_with_camera_settings(*args: object, **kwargs: object) -> None:
        before = camera_advanced.load_config(app.CONFIG_PATH)
        camera_values = {
            key: before[key]
            for key in CAMERA_CONFIG_KEYS
            if key in before
        }
        original_save(*args, **kwargs)
        if camera_values:
            after = camera_advanced.load_config(app.CONFIG_PATH)
            after.update(camera_values)
            camera_advanced.save_config(app.CONFIG_PATH, after)

    app.save_config = save_with_camera_settings


def install_accuracy_sampling_sync() -> None:
    """Make Accuracy Boost wait for distinct detection samples."""
    original_open = app.open_camera

    def open_with_detection_timing(index: int):
        capture = original_open(index)
        app.ACCURACY_SAMPLE_INTERVAL = max(
            0.06,
            1.0 / max(1, camera_advanced.RUNTIME.target_fps),
        )
        return capture

    app.open_camera = open_with_detection_timing


def main() -> None:
    visual_system.install_window_branding()
    runtime_multi_move_patch.install(app)
    ui.install_clean_highgui_windows()
    ui.install_profile_creation_prompt()
    calibration_cleanup.install(calibration_ui)
    calibration_ui.install(app)

    engine_settings_screen = navigation.settings_screen
    camera_advanced.install(app, navigation)
    local_detection.install(
        app,
        navigation,
        engine_settings_screen,
    )
    local_detection_runtime.install(app)
    local64_occlusion_fix.install()
    install_camera_config_persistence()
    install_accuracy_sampling_sync()

    navigation.install_navigation_patches()
    game_session.install_consolidated_setup_ui()
    promotion_popup.install(app)
    app.draw_evaluation_bar = game_history.draw_evaluation_bar_left
    review_ui_fix.install(app)
    training_settings.install(app, navigation)
    piece_theme_system.install(app)
    feature_settings.install(app, navigation)
    multi_move_settings.install(feature_settings, app)
    content_manager_ui.install(app, navigation)

    # ------------------------------------------------------------
    # UI selection – Qt preferred, OpenCV fallback
    # ------------------------------------------------------------
    if _HAS_QT_UI:
        # QtApp already knows how to launch the selected screen.
        # It will call the appropriate explorer / game logic internally,
        # so we simply start it and then exit the main loop.
        QtApp().run()
        # No further processing is needed – the Qt UI handles the
        # action and returns when the user quits the Qt app.
        return
    else:
        # Fallback to the original OpenCV UI.
        action = home_screen()

        # --------------------------------------------------------
        # Legacy OpenCV‑based action mapping (unchanged)
        # --------------------------------------------------------
        if action == "history":
            game_history.show_game_history()
        elif action == "chess960":
            chess960_generator.show_chess960_generator()
        elif action == "opening":
            opening_explorer.show_opening_explorer()
        elif action == "endgame":
            endgame_explorer.show_endgame_explorer()
        elif action == "virtual_bot":
            bot_games.show_virtual_bot_game()
        elif action == "otb_bot":
            bot_games.show_virtual_bot_game(otb=True)
        elif action == "settings":
            navigation.settings_screen()
        elif action == "start":
            saved = game_session.run_game()
            while saved:
                post_action = navigation.post_game_screen()
                if post_action != "rematch" or navigation.LAST_SETUP is None:
                    break
                navigation.REMATCH_SETUP = navigation.LAST_SETUP
                saved = game_session.run_game()
        else:
            return


if __name__ == "__main__":
    main()
