from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import chess
import chess.pgn
import cv2
import numpy as np

import app
import pregame_ui
from pregame_ui import Button

REVISION = 35
GAMES_DIR = Path('games')


@dataclass
class HistoryGame:
    path: Path
    white: str
    black: str
    result: str
    event: str
    date: str
    time_control: str
    termination: str
    plies: int
    white_accuracy: float | None = None
    black_accuracy: float | None = None

    @property
    def moves(self) -> int:
        return (self.plies + 1) // 2


def _put(image, text, xy, color=(240, 240, 240), scale=0.55, thickness=1):
    cv2.putText(image, text, xy, cv2.FONT_HERSHEY_SIMPLEX, scale, (8, 8, 8), thickness + 3, cv2.LINE_AA)
    cv2.putText(image, text, xy, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


def _read_analysis_for(pgn_path: Path) -> tuple[float | None, float | None]:
    candidates = [
        pgn_path.with_suffix('.analysis.json'),
        GAMES_DIR / f'{pgn_path.stem}_analysis.json',
    ]
    if pgn_path.name == 'latest_game.pgn':
        candidates.insert(0, GAMES_DIR / 'latest_analysis.json')
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            return float(data.get('white_accuracy')), float(data.get('black_accuracy'))
        except (OSError, ValueError, TypeError, AttributeError):
            pass
    return None, None


def load_history() -> list[HistoryGame]:
    GAMES_DIR.mkdir(exist_ok=True)
    games: list[HistoryGame] = []
    seen: set[Path] = set()
    paths = sorted(GAMES_DIR.glob('*.pgn'), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in paths:
        try:
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            with path.open(encoding='utf-8', errors='replace') as handle:
                game = chess.pgn.read_game(handle)
            if game is None:
                continue
            headers = game.headers
            plies = sum(1 for _ in game.mainline_moves())
            wa, ba = _read_analysis_for(path)
            games.append(HistoryGame(
                path=path,
                white=headers.get('White', 'White'),
                black=headers.get('Black', 'Black'),
                result=headers.get('Result', '*'),
                event=headers.get('Event', 'Recorded OTB Game'),
                date=headers.get('Date', path.stem.replace('game_', '').split('_')[0]),
                time_control=headers.get('TimeControl', 'Not recorded'),
                termination=headers.get('Termination', 'Not recorded'),
                plies=plies,
                white_accuracy=wa,
                black_accuracy=ba,
            ))
        except (OSError, ValueError):
            continue
    return games


def _review_game(item: HistoryGame) -> None:
    try:
        with item.path.open(encoding='utf-8', errors='replace') as handle:
            game = chess.pgn.read_game(handle)
        if game is None:
            app.show_result_popup('Cannot review game', 'The selected PGN could not be read.')
            return
        moves = list(game.mainline_moves())
        engine = app.find_stockfish(None)
        if engine is None:
            app.show_result_popup('Stockfish not found', 'Choose a UCI engine in Game Settings before reviewing this game.')
            return
        review = app.analyze_game(moves, engine, progress=app.show_analysis_progress)
        report_path = item.path.with_suffix('.analysis.json')
        app.save_analysis_report(review, report_path)
        try:
            cv2.destroyWindow('Stockfish post-game analysis')
        except cv2.error:
            pass
        app.show_game_review(review, moves, item.white, item.black)
    except Exception as exc:
        app.show_result_popup('Review failed', str(exc))


def show_game_history() -> None:
    window = 'Chess Camera - Game History'
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 1180, 760)
    selected = 0
    scroll = 0
    click_queue: list[str] = []
    buttons: list[Button] = []

    def mouse(event, x, y, flags, _data):
        nonlocal scroll
        if event == cv2.EVENT_MOUSEWHEEL:
            delta = (int(flags) >> 16) & 0xFFFF
            if delta & 0x8000:
                delta -= 0x10000
            scroll += -1 if delta > 0 else 1
        elif event == cv2.EVENT_LBUTTONUP:
            action = pregame_ui.clicked_action(buttons, x, y)
            if action:
                click_queue.append(action)

    cv2.setMouseCallback(window, mouse)
    while True:
        games = load_history()
        visible = 8
        scroll = max(0, min(scroll, max(0, len(games) - visible)))
        if games:
            selected = max(0, min(selected, len(games) - 1))
            if selected < scroll:
                scroll = selected
            if selected >= scroll + visible:
                scroll = selected - visible + 1

        view = np.zeros((760, 1180, 3), dtype=np.uint8)
        view[:] = (28, 31, 37)
        _put(view, 'Game History', (35, 48), (100, 220, 255), 0.95, 2)
        _put(view, 'Recorded over-the-board games', (35, 80), (165, 175, 190), 0.50)
        buttons = []

        if not games:
            _put(view, 'No completed games found in the games folder.', (40, 145), scale=0.62)
        for row, item in enumerate(games[scroll:scroll + visible]):
            index = scroll + row
            y = 110 + row * 70
            active = index == selected
            fill = (52, 90, 72) if active else (43, 47, 55)
            cv2.rectangle(view, (35, y), (770, y + 58), fill, -1)
            cv2.rectangle(view, (35, y), (770, y + 58), (120, 255, 170) if active else (85, 92, 105), 2)
            _put(view, f'{item.white[:20]}  {item.result}  {item.black[:20]}', (50, y + 25), scale=0.58)
            _put(view, f'{item.date}   {item.moves} moves   {item.time_control}', (50, y + 48), (165, 175, 190), 0.43)
            buttons.append(Button(f'select_{index}', '', 35, y, 735, 58))

        back = Button('back', 'BACK', 35, 690, 170, 48)
        up = Button('up', 'UP', 225, 690, 110, 48, enabled=scroll > 0)
        down = Button('down', 'DOWN', 350, 690, 110, 48, enabled=scroll + visible < len(games))
        buttons.extend((back, up, down))
        for button in (back, up, down):
            pregame_ui.draw_button(view, button)

        if games:
            item = games[selected]
            _put(view, 'GAME DETAILS', (820, 115), (100, 220, 255), 0.58)
            details = [
                f'White: {item.white}', f'Black: {item.black}', f'Result: {item.result}',
                f'How it ended: {item.termination}', f'Moves: {item.moves}',
                f'Time control: {item.time_control}', f'Date: {item.date}', f'Event: {item.event}',
                f"White accuracy: {item.white_accuracy:.1f}%" if item.white_accuracy is not None else 'White accuracy: Not reviewed',
                f"Black accuracy: {item.black_accuracy:.1f}%" if item.black_accuracy is not None else 'Black accuracy: Not reviewed',
            ]
            for i, line in enumerate(details):
                _put(view, line[:43], (820, 160 + i * 38), scale=0.50)
            review = Button('review', 'REVIEW WITH STOCKFISH', 820, 585, 315, 55, active=True)
            buttons.append(review)
            pregame_ui.draw_button(view, review)

        cv2.imshow(window, view)
        key = cv2.waitKey(25) & 0xFF
        action = click_queue.pop(0) if click_queue else None
        if action and action.startswith('select_'):
            selected = int(action.split('_', 1)[1])
        elif action == 'up' or key in (82, ord('w')):
            scroll -= 1
        elif action == 'down' or key in (84, ord('s')):
            scroll += 1
        elif action == 'review' and games:
            _review_game(games[selected])
            cv2.namedWindow(window, cv2.WINDOW_NORMAL)
            cv2.setMouseCallback(window, mouse)
        elif action == 'back' or key == 27:
            cv2.destroyWindow(window)
            return


def board_options_menu() -> str | None:
    window = 'Board Options'
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 480, 270)
    buttons = [
        Button('profile_rename', 'Rename preset', 65, 78, 350, 52),
        Button('profile_reset_training', 'Reset training', 65, 145, 350, 52),
        Button('cancel', 'Cancel', 155, 212, 170, 42),
    ]
    queue: list[str] = []
    def mouse(event, x, y, _flags, _data):
        if event == cv2.EVENT_LBUTTONUP:
            action = pregame_ui.clicked_action(buttons, x, y)
            if action:
                queue.append(action)
    cv2.setMouseCallback(window, mouse)
    while True:
        view = np.zeros((270, 480, 3), dtype=np.uint8); view[:] = (28, 31, 37)
        _put(view, 'Board Options', (65, 48), (100, 220, 255), 0.80, 2)
        for b in buttons: pregame_ui.draw_button(view, b)
        cv2.imshow(window, view)
        key = cv2.waitKey(20) & 0xFF
        action = queue.pop(0) if queue else None
        if action in {'profile_rename', 'profile_reset_training'}:
            cv2.destroyWindow(window); return action
        if action == 'cancel' or key == 27:
            cv2.destroyWindow(window); return None


def install_setup_patches() -> None:
    original_render = app.render_setup_screen
    original_clicked = app.clicked_action

    def render(*args, **kwargs):
        view, buttons = original_render(*args, **kwargs)
        buttons = [b for b in buttons if b.action not in {'profile_rename', 'profile_reset_training', 'swap_players'}]
        cv2.rectangle(view, (420, 132), (535, 218), (28, 31, 37), -1)
        swap = Button('swap_players', '', 463, 145, 58, 58)
        buttons.append(swap); pregame_ui.draw_button(view, swap)
        cv2.arrowedLine(view, (480, 190), (480, 158), (120, 255, 170), 3, cv2.LINE_AA, tipLength=.3)
        cv2.arrowedLine(view, (503, 158), (503, 190), (120, 220, 255), 3, cv2.LINE_AA, tipLength=.3)
        cv2.rectangle(view, (145, 767), (540, 820), (28, 31, 37), -1)
        options = Button('board_options', 'Board options', 155, 772, 375, 42)
        buttons.append(options); pregame_ui.draw_button(view, options)
        return view, buttons

    def clicked(buttons, x, y):
        action = original_clicked(buttons, x, y)
        if action == 'board_options':
            return board_options_menu()
        return action

    app.render_setup_screen = render
    app.clicked_action = clicked

    original_create = app.BoardProfileStore.create_from
    def create_named(store, source):
        created = original_create(store, source)
        name = app.prompt_for_text('Create new board', 'Board name', created.name)
        if name:
            try:
                store.rename(created, name)
            except (ValueError, OSError):
                pass
        return created
    app.BoardProfileStore.create_from = create_named


def home_screen() -> str:
    window = f'Chess Camera Revision {REVISION}'
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 960, 640)
    buttons = [
        Button('start', 'START RECORDED OTB GAME', 220, 210, 520, 82, active=True),
        Button('history', 'GAME HISTORY', 220, 320, 520, 72),
        Button('exit', 'EXIT', 350, 465, 260, 58),
    ]
    queue: list[str] = []
    def mouse(event, x, y, _flags, _data):
        if event == cv2.EVENT_LBUTTONUP:
            action = pregame_ui.clicked_action(buttons, x, y)
            if action: queue.append(action)
    cv2.setMouseCallback(window, mouse)
    while True:
        view = np.zeros((640, 960, 3), dtype=np.uint8); view[:] = (28, 31, 37)
        _put(view, 'Chess Camera', (70, 90), (100, 220, 255), 1.25, 2)
        _put(view, 'Revision 35', (72, 130), (120, 255, 170), 0.65)
        _put(view, 'Record physical chess games and review them locally.', (72, 168), (165, 175, 190), 0.54)
        for button in buttons: pregame_ui.draw_button(view, button)
        _put(view, 'More features can be added here later.', (305, 585), (135, 145, 160), 0.45)
        cv2.imshow(window, view)
        key = cv2.waitKey(25) & 0xFF
        action = queue.pop(0) if queue else None
        if action in {'start', 'history', 'exit'}:
            cv2.destroyWindow(window); return action
        if key == 27: cv2.destroyWindow(window); return 'exit'


def main() -> None:
    install_setup_patches()
    while True:
        action = home_screen()
        if action == 'history':
            show_game_history(); continue
        if action == 'start':
            app.main(); return
        return


if __name__ == '__main__':
    main()
