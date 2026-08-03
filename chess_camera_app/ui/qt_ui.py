
"""
Qt based UI for Knightboard.

This module provides a minimal Qt5/Qt6 (via PySide6) replacement for the
original OpenCV‑based UI.  It is intentionally lightweight – the goal is to
demonstrate a modern, themable UI that can be expanded to cover the full
feature set of the application.

A typical workflow:

    from chess_camera_app.ui.qt_ui import QtApp
    QtApp().run()

The UI currently shows a simple start screen with large buttons that map to
the same actions as the original `home_screen`.  Clicking a button will emit
the corresponding action string, which the main entry point can handle in the
same way as before.

All heavy‑lifting (camera handling, detection, engine integration) remains
in the existing modules; this file only deals with presentation.
"""

import sys
import os
from pathlib import Path

# Prefer PySide6 (Qt6) but fall back to PySide2 if unavailable.
try:
    from PySide6.QtWidgets import (
        QApplication,
        QWidget,
        QPushButton,
        QVBoxLayout,
        QLabel,
        QMessageBox,
    )
    from PySide6.QtGui import QIcon, QFont
    from PySide6.QtCore import Qt, Signal, Slot
except ImportError:
    try:
        from PySide2.QtWidgets import (
            QApplication,
            QWidget,
            QPushButton,
            QVBoxLayout,
            QLabel,
            QMessageBox,
        )
        from PySide2.QtGui import QIcon, QFont
        from PySide2.QtCore import Qt, Signal, Slot
    except ImportError as e:
        raise ImportError(
            "Qt UI requires PySide6 (or PySide2). Install with `pip install PySide6`."
        ) from e


class QtApp(QWidget):
    \"\"\"Main window for the modern UI.

    The window emits the selected action via the ``action_selected`` signal,
    mirroring the strings returned by the original OpenCV home screen.
    \"\"\"

    action_selected = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Knightboard – Modern UI")
        self.setMinimumSize(800, 600)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)

        header = QLabel("Your offline chess studio")
        header_font = QFont("Arial", 24, QFont.Bold)
        header.setFont(header_font)
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Define buttons and the action they correspond to.
        buttons = [
            ("RECORD OTB GAME", "start"),
            ("GAME HISTORY", "history"),
            ("CHESS960", "chess960"),
            ("OPENING EXPLORER", "opening"),
            ("ENDGAME EXPLORER", "endgame"),
            ("SETTINGS & LIBRARIES", "settings"),
            ("VIRTUAL BOT GAME", "virtual_bot"),
            ("OTB BOT GAME", "otb_bot"),
            ("EXIT KNIGHTBOARD", "exit"),
        ]

        btn_font = QFont("Arial", 14)

        for label, action in buttons:
            btn = QPushButton(label)
            btn.setFont(btn_font)
            btn.setMinimumHeight(40)
            btn.clicked.connect(self._make_handler(action))
            layout.addWidget(btn)

        self.setLayout(layout)

    def _make_handler(self, action: str):
        @Slot()
        def handler():
            # Emit the selected action; the main program will decide what to do.
            self.action_selected.emit(action)

        return handler

    def run(self):
        \"\"\"Start the Qt event loop.\n\n        The function blocks until the window is closed.  It returns the
        last selected action (or ``\"exit\"`` if the window was closed without a
        selection).\"\"\"
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)

        # Store the result in a mutable container.
        result = {"action": "exit"}

        @Slot(str)
        def capture(action):
            result["action"] = action
            # Close the window after a selection so the caller can continue.
            self.close()

        self.action_selected.connect(capture)
        self.show()
        app.exec_()
        return result["action"]


def main():
    \"\"\"Convenient entry point for ``python -m chess_camera_app.ui.qt_ui``.\"\"\"
    qt_app = QtApp()
    selected = qt_app.run()
    # For demonstration we simply print the selected action.
    print(f\"Selected action: {selected}\")


if __name__ == \"__main__\":
    main()
