from __future__ import annotations

from pathlib import Path
from types import ModuleType
from typing import Callable

import cv2
import numpy as np

from chess_camera_app.content import content_library
from chess_camera_app.ui.pregame_ui import Button, clicked_action, draw_button


MANAGER_WINDOW = "Chess Camera - Data and Libraries"


def _choose_storage_directory(current: Path) -> tuple[Path | None, str | None]:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        return None, "The folder picker is unavailable. On Ubuntu, install python3-tk."

    root: object | None = None
    try:
        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except tk.TclError:
            pass
        selected = filedialog.askdirectory(
            parent=root,
            title="Choose Chess Camera content storage folder",
            initialdir=str(current if current.exists() else Path.cwd()),
        )
    except tk.TclError as error:
        return None, f"Could not open the folder picker: {error}"
    finally:
        if root is not None:
            try:
                root.destroy()  # type: ignore[attr-defined]
            except tk.TclError:
                pass

    if not selected:
        return None, None
    return Path(selected), None


class ProgressDialog:
    def __init__(self, app_module: ModuleType, title: str) -> None:
        self.app = app_module
        self.title = title
        self.window = "Chess Camera - Content Download"
        self.cancelled = False
        self.button = Button("cancel", "CANCEL", 285, 350, 210, 52)
        cv2.namedWindow(self.window, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window, 780, 440)

        def mouse(event: int, x: int, y: int, _flags: int, _data: object) -> None:
            if event == cv2.EVENT_LBUTTONUP and self.button.contains(x, y):
                self.cancelled = True

        cv2.setMouseCallback(self.window, mouse)

    def close(self) -> None:
        try:
            cv2.destroyWindow(self.window)
            cv2.waitKey(1)
        except cv2.error:
            pass

    def __call__(self, info: content_library.ProgressInfo) -> bool:
        view = np.zeros((440, 780, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        self.app.put_text(view, self.title, (40, 58), (100, 220, 255), 0.88)
        self.app.put_text(
            view,
            info.stage[:70],
            (40, 105),
            (120, 255, 170),
            0.60,
        )
        self.app.put_text(
            view,
            info.label[:76],
            (40, 145),
            (220, 225, 235),
            0.50,
        )
        self.app.put_text(
            view,
            f"File {info.item_index} of {info.item_count}",
            (40, 188),
            (175, 185, 200),
            0.48,
        )

        left, right, y = 40, 740, 250
        cv2.line(view, (left, y), (right, y), (72, 78, 88), 18)
        if info.bytes_total and info.bytes_total > 0:
            fraction = min(1.0, max(0.0, info.bytes_done / info.bytes_total))
            cv2.line(
                view,
                (left, y),
                (left + int((right - left) * fraction), y),
                (78, 150, 105),
                18,
            )
            detail = (
                f"{content_library.format_bytes(info.bytes_done)} / "
                f"{content_library.format_bytes(info.bytes_total)}  "
                f"({fraction:.0%})"
            )
        else:
            fraction = info.item_index / max(1, info.item_count)
            cv2.line(
                view,
                (left, y),
                (left + int((right - left) * fraction), y),
                (78, 150, 105),
                18,
            )
            detail = content_library.format_bytes(info.bytes_done)
        self.app.put_text(view, detail, (40, 295), (185, 195, 210), 0.50)
        self.app.put_text(
            view,
            "Downloads can be resumed after cancellation or interruption.",
            (40, 325),
            (145, 155, 170),
            0.42,
        )
        draw_button(view, self.button)
        cv2.imshow(self.window, view)
        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            self.cancelled = True
        try:
            if cv2.getWindowProperty(self.window, cv2.WND_PROP_VISIBLE) < 1:
                self.cancelled = True
        except cv2.error:
            self.cancelled = True
        return not self.cancelled


def _run_with_progress(
    app_module: ModuleType,
    title: str,
    operation: Callable[[content_library.ProgressCallback], object],
) -> tuple[object | None, str | None]:
    dialog = ProgressDialog(app_module, title)
    try:
        return operation(dialog), None
    except content_library.DownloadCancelled:
        return None, "Download cancelled. Partial files were kept for resume."
    except content_library.ContentLibraryError as error:
        return None, str(error)
    except Exception as error:
        return None, f"Content operation failed: {error}"
    finally:
        dialog.close()


def _package_primary_button(
    action: str,
    installed: bool,
    missing_label: str,
    x: int,
    y: int,
    width: int,
    height: int,
) -> Button:
    if installed:
        return Button(action, "INSTALLED", x, y, width, height, enabled=False)
    return Button(action, missing_label, x, y, width, height)


def show_content_manager(app_module: ModuleType, navigation_module: ModuleType) -> None:
    config_path = app_module.CONFIG_PATH
    queue: list[str] = []
    buttons: list[Button] = []
    message = (
        "Optional data is stored outside the installer and remains available offline."
    )

    cv2.namedWindow(MANAGER_WINDOW, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(MANAGER_WINDOW, 1060, 760)

    def mouse(event: int, x: int, y: int, _flags: int, _data: object) -> None:
        if event == cv2.EVENT_LBUTTONUP:
            action = clicked_action(buttons, x, y)
            if action:
                queue.append(action)

    cv2.setMouseCallback(MANAGER_WINDOW, mouse)

    while True:
        root = content_library.configured_library_root(config_path)
        opening_path = content_library.downloaded_opening_book(config_path)
        tablebase_path = content_library.downloaded_tablebase_directory(config_path)
        opening_size = content_library.package_size(
            content_library.opening_package_directory(config_path)
        )
        tablebase_size = content_library.package_size(
            content_library.tablebase_package_directory(config_path)
        )

        view = np.zeros((760, 1060, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        app_module.put_text(
            view,
            "Data and Libraries",
            (42, 58),
            (100, 220, 255),
            0.98,
        )
        app_module.put_text(
            view,
            "Download optional opening and endgame data after installing Chess Camera.",
            (42, 94),
            (175, 185, 200),
            0.48,
        )
        app_module.put_text(
            view,
            f"Storage: {str(root)[:92]}",
            (42, 130),
            (145, 155, 170),
            0.42,
        )
        storage = Button("storage", "CHANGE STORAGE LOCATION", 765, 104, 250, 42)
        draw_button(view, storage)

        # Opening package card.
        cv2.rectangle(view, (35, 170), (1025, 365), (39, 43, 50), -1)
        cv2.rectangle(view, (35, 170), (1025, 365), (72, 78, 88), 2)
        app_module.put_text(
            view,
            "Expanded Lichess Opening Names",
            (58, 210),
            (120, 220, 255),
            0.72,
        )
        app_module.put_text(
            view,
            "Pinned CC0 opening-name dataset, converted locally to a Polyglot book.",
            (58, 244),
            (190, 198, 210),
            0.46,
        )
        app_module.put_text(
            view,
            "Source files are verified against the pinned Git commit before building.",
            (58, 273),
            (160, 170, 185),
            0.42,
        )
        opening_status = (
            f"INSTALLED  {content_library.format_bytes(opening_size)}"
            if opening_path is not None
            else "NOT INSTALLED"
        )
        app_module.put_text(
            view,
            opening_status,
            (58, 326),
            (120, 255, 170) if opening_path else (180, 190, 205),
            0.54,
        )
        opening_install = _package_primary_button(
            "opening_install",
            opening_path is not None,
            "DOWNLOAD",
            600,
            202,
            190,
            46,
        )
        opening_activate = Button(
            "opening_activate",
            "USE IN EXPLORER",
            805,
            202,
            190,
            46,
            enabled=opening_path is not None,
        )
        opening_verify = Button(
            "opening_verify",
            "VERIFY",
            600,
            270,
            190,
            42,
            enabled=opening_path is not None,
        )
        opening_remove = Button(
            "opening_remove",
            "REMOVE",
            805,
            270,
            190,
            42,
            enabled=opening_path is not None,
        )

        # Tablebase package card.
        cv2.rectangle(view, (35, 390), (1025, 615), (39, 43, 50), -1)
        cv2.rectangle(view, (35, 390), (1025, 615), (72, 78, 88), 2)
        app_module.put_text(
            view,
            "Syzygy 3/4/5-Piece Tablebases",
            (58, 430),
            (120, 220, 255),
            0.72,
        )
        app_module.put_text(
            view,
            "Exact offline WDL and DTZ data from the Lichess tablebase mirror.",
            (58, 464),
            (190, 198, 210),
            0.46,
        )
        app_module.put_text(
            view,
            "About 939 MB. Downloads resume and local SHA-256 checksums are retained.",
            (58, 493),
            (160, 170, 185),
            0.42,
        )
        app_module.put_text(
            view,
            "A custom Syzygy folder can still be selected in Endgame Explorer.",
            (58, 520),
            (160, 170, 185),
            0.42,
        )
        tablebase_status = (
            f"INSTALLED  {content_library.format_bytes(tablebase_size)}"
            if tablebase_path is not None
            else "NOT INSTALLED"
        )
        app_module.put_text(
            view,
            tablebase_status,
            (58, 576),
            (120, 255, 170) if tablebase_path else (180, 190, 205),
            0.54,
        )
        tablebase_install = _package_primary_button(
            "tablebase_install",
            tablebase_path is not None,
            "DOWNLOAD (~1 GB)",
            600,
            425,
            190,
            46,
        )
        tablebase_activate = Button(
            "tablebase_activate",
            "USE IN EXPLORER",
            805,
            425,
            190,
            46,
            enabled=tablebase_path is not None,
        )
        tablebase_verify = Button(
            "tablebase_verify",
            "VERIFY",
            600,
            493,
            190,
            42,
            enabled=tablebase_path is not None,
        )
        tablebase_remove = Button(
            "tablebase_remove",
            "REMOVE",
            805,
            493,
            190,
            42,
            enabled=tablebase_path is not None,
        )

        back = Button("back", "BACK", 790, 675, 225, 52)
        buttons = [
            storage,
            opening_install,
            opening_activate,
            opening_verify,
            opening_remove,
            tablebase_install,
            tablebase_activate,
            tablebase_verify,
            tablebase_remove,
            back,
        ]
        for button in buttons[1:]:
            draw_button(view, button)
        app_module.put_text(
            view,
            message[:112],
            (42, 710),
            (120, 220, 255),
            0.41,
        )

        cv2.imshow(MANAGER_WINDOW, view)
        key = cv2.waitKey(25) & 0xFF
        action = queue.pop(0) if queue else None

        if action == "storage":
            selected, error = _choose_storage_directory(root)
            cv2.namedWindow(MANAGER_WINDOW, cv2.WINDOW_NORMAL)
            cv2.setMouseCallback(MANAGER_WINDOW, mouse)
            if error:
                message = error
            elif selected is not None:
                content_library.set_library_root(config_path, selected)
                message = "Storage location changed. Existing packages were not moved."
        elif action == "opening_install":
            cv2.destroyWindow(MANAGER_WINDOW)
            result, error = _run_with_progress(
                app_module,
                "Expanded Opening Database",
                lambda progress: content_library.install_opening_package(
                    config_path, progress
                ),
            )
            cv2.namedWindow(MANAGER_WINDOW, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(MANAGER_WINDOW, 1060, 760)
            cv2.setMouseCallback(MANAGER_WINDOW, mouse)
            message = error or f"Opening database installed: {Path(str(result)).name}"
        elif action == "opening_activate":
            message = (
                "Downloaded opening database selected."
                if content_library.activate_downloaded_opening(config_path)
                else "The downloaded opening database could not be found."
            )
        elif action == "opening_verify":
            cv2.destroyWindow(MANAGER_WINDOW)
            result, error = _run_with_progress(
                app_module,
                "Verify Opening Database",
                lambda progress: content_library.verify_installed_package(
                    config_path,
                    content_library.OPENING_PACKAGE_ID,
                    progress,
                ),
            )
            cv2.namedWindow(MANAGER_WINDOW, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(MANAGER_WINDOW, 1060, 760)
            cv2.setMouseCallback(MANAGER_WINDOW, mouse)
            message = error or (str(result[1]) if isinstance(result, tuple) else "Verified.")
        elif action == "opening_remove":
            if app_module.ask_yes_no(
                "Remove opening database?",
                "Delete the downloaded opening database from this computer?",
            ):
                content_library.remove_package(config_path, content_library.OPENING_PACKAGE_ID)
                message = "Downloaded opening database removed."
        elif action == "tablebase_install":
            accepted = app_module.ask_yes_no(
                "Download Syzygy tablebases?",
                "Download approximately 939 MB of 3/4/5-piece tablebases? "
                "The app may take several minutes and needs at least 1.25 GB free.",
            )
            if accepted:
                cv2.destroyWindow(MANAGER_WINDOW)
                result, error = _run_with_progress(
                    app_module,
                    "Syzygy 3/4/5-Piece Tablebases",
                    lambda progress: content_library.install_tablebase_package(
                        config_path, progress
                    ),
                )
                cv2.namedWindow(MANAGER_WINDOW, cv2.WINDOW_NORMAL)
                cv2.resizeWindow(MANAGER_WINDOW, 1060, 760)
                cv2.setMouseCallback(MANAGER_WINDOW, mouse)
                message = error or f"Tablebases installed in {result}"
        elif action == "tablebase_activate":
            if content_library.activate_downloaded_tablebase(config_path):
                cv2.destroyWindow(MANAGER_WINDOW)
                from chess_camera_app.analysis import endgame_explorer

                endgame_explorer.show_endgame_explorer()
                cv2.namedWindow(MANAGER_WINDOW, cv2.WINDOW_NORMAL)
                cv2.resizeWindow(MANAGER_WINDOW, 1060, 760)
                cv2.setMouseCallback(MANAGER_WINDOW, mouse)
                message = "Returned from Endgame Explorer."
            else:
                message = "The downloaded tablebase package could not be found."
        elif action == "tablebase_verify":
            cv2.destroyWindow(MANAGER_WINDOW)
            result, error = _run_with_progress(
                app_module,
                "Verify Syzygy Tablebases",
                lambda progress: content_library.verify_installed_package(
                    config_path,
                    content_library.TABLEBASE_PACKAGE_ID,
                    progress,
                ),
            )
            cv2.namedWindow(MANAGER_WINDOW, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(MANAGER_WINDOW, 1060, 760)
            cv2.setMouseCallback(MANAGER_WINDOW, mouse)
            message = error or (str(result[1]) if isinstance(result, tuple) else "Verified.")
        elif action == "tablebase_remove":
            if app_module.ask_yes_no(
                "Remove tablebases?",
                "Delete all downloaded 3/4/5-piece Syzygy files from this computer?",
            ):
                content_library.remove_package(config_path, content_library.TABLEBASE_PACKAGE_ID)
                message = "Downloaded Syzygy tablebases removed."
        elif action == "back" or key == 27:
            cv2.destroyWindow(MANAGER_WINDOW)
            return

        try:
            if cv2.getWindowProperty(MANAGER_WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                return
        except cv2.error:
            return


def install(app_module: ModuleType, navigation_module: ModuleType) -> None:
    """Add Data and Libraries above the existing settings screens."""
    if getattr(navigation_module, "_content_manager_installed", False):
        return
    original_settings = navigation_module.settings_screen

    def settings_with_content() -> None:
        window = "Chess Camera - Settings and Libraries"
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window, 780, 470)
        queue: list[str] = []
        buttons = [
            Button("app_settings", "APP SETTINGS", 85, 135, 610, 70),
            Button("content", "DATA AND LIBRARIES", 85, 235, 610, 70, active=True),
            Button("back", "BACK", 255, 370, 270, 58),
        ]

        def mouse(event: int, x: int, y: int, _flags: int, _data: object) -> None:
            if event == cv2.EVENT_LBUTTONUP:
                action = clicked_action(buttons, x, y)
                if action:
                    queue.append(action)

        cv2.setMouseCallback(window, mouse)
        while True:
            view = np.zeros((470, 780, 3), dtype=np.uint8)
            view[:] = (28, 31, 37)
            app_module.put_text(view, "Settings", (85, 70), (100, 220, 255), 1.0)
            app_module.put_text(
                view,
                "Configure the app or install optional offline chess data.",
                (85, 106),
                (175, 185, 200),
                0.47,
            )
            for button in buttons:
                draw_button(view, button)
            cv2.imshow(window, view)
            key = cv2.waitKey(25) & 0xFF
            action = queue.pop(0) if queue else None
            if action == "app_settings":
                cv2.destroyWindow(window)
                original_settings()
                cv2.namedWindow(window, cv2.WINDOW_NORMAL)
                cv2.resizeWindow(window, 780, 470)
                cv2.setMouseCallback(window, mouse)
            elif action == "content":
                cv2.destroyWindow(window)
                show_content_manager(app_module, navigation_module)
                cv2.namedWindow(window, cv2.WINDOW_NORMAL)
                cv2.resizeWindow(window, 780, 470)
                cv2.setMouseCallback(window, mouse)
            elif action == "back" or key == 27:
                cv2.destroyWindow(window)
                return
            try:
                if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                    return
            except cv2.error:
                return

    navigation_module.settings_screen = settings_with_content
    navigation_module._content_manager_installed = True
