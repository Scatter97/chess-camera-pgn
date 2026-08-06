"""Modern, single-window Qt shell for Knightboard.

The legacy screens use OpenCV windows.  This module provides the navigation
shell around them while keeping the user in one Qt window: selecting a menu
item swaps the current page in a ``QStackedWidget`` instead of closing the
window or opening another one.
"""

import sys

try:
    from PySide6.QtWidgets import (
        QApplication,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QPushButton,
        QStackedWidget,
        QVBoxLayout,
        QWidget,
    )
    from PySide6.QtGui import QFont
    from PySide6.QtCore import Qt, Signal, Slot
except ImportError:
    try:
        from PySide2.QtWidgets import (
            QApplication,
            QFrame,
            QGridLayout,
            QHBoxLayout,
            QLabel,
            QListWidget,
            QPushButton,
            QStackedWidget,
            QVBoxLayout,
            QWidget,
        )
        from PySide2.QtGui import QFont
        from PySide2.QtCore import Qt, Signal, Slot
    except ImportError as exc:
        raise ImportError(
            "Qt UI requires PySide6 (or PySide2). Install with `pip install PySide6`."
        ) from exc


class QtApp(QWidget):
    """Knightboard's in-window navigation shell."""

    action_selected = Signal(str)

    _FEATURES = (
        ("RECORD OTB GAME", "start", "Record an over-the-board game with the camera."),
        ("GAME HISTORY", "history", "Review and manage games saved on this device."),
        ("CHESS960", "chess960", "Start a Chess960 game with a randomized back rank."),
        ("OPENING EXPLORER", "opening", "Explore opening ideas from your local library."),
        ("ENDGAME EXPLORER", "endgame", "Study endgame positions and plans."),
        ("SETTINGS & LIBRARIES", "settings", "Configure cameras, libraries, and preferences."),
        ("VIRTUAL BOT GAME", "virtual_bot", "Play an offline game against a virtual bot."),
        ("OTB BOT GAME", "otb_bot", "Record an OTB game while Knightboard assists."),
    )

    def __init__(self, action_handler=None):
        # QWidget must never be constructed before QApplication.  The old
        # launcher created ``QtApp()`` first, which caused Qt to terminate
        # immediately on some platforms and looked like a tiny window flash.
        if QApplication.instance() is None:
            self._app = QApplication(sys.argv)
        else:
            self._app = QApplication.instance()
        super().__init__()
        self._action_handler = action_handler
        self.setWindowTitle("Knightboard")
        self.setMinimumSize(800, 600)
        self.resize(980, 700)
        self._stack = QStackedWidget()
        self._pages = {}
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(18)

        header = QHBoxLayout()
        brand = QLabel("KNIGHTBOARD")
        brand.setObjectName("brand")
        brand.setFont(QFont("Arial", 20, QFont.Bold))
        header.addWidget(brand)
        header.addStretch()
        version = QLabel("OFFLINE CHESS STUDIO  •  v0.50")
        version.setObjectName("version")
        header.addWidget(version)
        root.addLayout(header)

        self._pages["home"] = self._build_home_page()
        self._stack.addWidget(self._pages["home"])
        root.addWidget(self._stack, 1)
        self._show_page("home")

        self.setStyleSheet(
            """
            QWidget { background: #10131a; color: #eef2f7; }
            QLabel#brand { color: #f6c453; letter-spacing: 2px; }
            QLabel#version, QLabel#muted { color: #8f9bad; }
            QLabel#pageTitle { color: #ffffff; font-size: 28px; font-weight: 700; }
            QLabel#pageDescription { color: #aab4c3; font-size: 15px; }
            QFrame#card { background: #191e28; border: 1px solid #2b3443; border-radius: 12px; }
            QPushButton { background: #202938; border: 1px solid #344258; border-radius: 9px;
                          color: #f2f5f8; padding: 16px; text-align: left; font-size: 14px; }
            QPushButton:hover { background: #2a3850; border-color: #f6c453; }
            QPushButton#primary { background: #f6c453; color: #16191f; font-weight: 700; }
            QPushButton#primary:hover { background: #ffd878; }
            """
        )

    def _build_home_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        title = QLabel("Your offline chess studio")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        subtitle = QLabel("Choose a workspace. Every feature opens inside this window.")
        subtitle.setObjectName("pageDescription")
        layout.addWidget(subtitle)

        grid = QGridLayout()
        grid.setSpacing(12)
        for index, (label, action, description) in enumerate(self._FEATURES):
            button = QPushButton(f"{label}\n{description}")
            button.setMinimumHeight(78)
            button.clicked.connect(self._make_handler(action))
            grid.addWidget(button, index // 2, index % 2)
        layout.addLayout(grid)

        exit_button = QPushButton("EXIT KNIGHTBOARD")
        exit_button.setObjectName("primary")
        exit_button.clicked.connect(self.close)
        layout.addWidget(exit_button)
        return page

    def _build_feature_page(self, action):
        labels = dict((item[1], (item[0], item[2])) for item in self._FEATURES)
        title_text, description = labels[action]
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(14)
        back = QPushButton("←  Back to main menu")
        back.setObjectName("primary")
        back.setMaximumWidth(210)
        back.clicked.connect(lambda: self._show_page("home"))
        layout.addWidget(back, 0, Qt.AlignLeft)

        title = QLabel(title_text)
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        intro = QLabel(description)
        intro.setObjectName("pageDescription")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        status = QLabel("This feature opens directly in Knightboard. Use Back to return to the main menu.")
        status.setObjectName("muted")
        status.setWordWrap(True)
        card_layout.addWidget(status)
        if action == "history":
            games = QListWidget()
            games.setMinimumHeight(180)
            try:
                from chess_camera_app.ui.ui_support import load_history
                entries = load_history()
            except Exception:
                entries = []
            if entries:
                for game in entries:
                    games.addItem(
                        f"{game.white}  vs  {game.black}   •   {game.result}   •   "
                        f"{game.moves} moves   •   {game.date}"
                    )
            else:
                games.addItem("No saved games yet. Record a game to see it here.")
            card_layout.addWidget(games)
        layout.addWidget(card)
        layout.addStretch()
        return page

    def _make_handler(self, action):
        @Slot()
        def handler():
            if action == "exit":
                self.close()
            elif self._action_handler is not None:
                self.hide()
                try:
                    self._action_handler(action)
                finally:
                    self.show()
            else:
                self._show_page(action)
        return handler

    def _show_page(self, action):
        if action not in self._pages:
            self._pages[action] = self._build_feature_page(action)
            self._stack.addWidget(self._pages[action])
        self._stack.setCurrentWidget(self._pages[action])

    def run(self):
        """Run until the user exits; menu navigation never closes the window."""
        app = self._app or QApplication.instance() or QApplication(sys.argv)
        self.show()
        exec_method = getattr(app, "exec", None) or app.exec_
        exec_method()
        return "exit"


def main():
    QtApp().run()


if __name__ == "__main__":
    main()

