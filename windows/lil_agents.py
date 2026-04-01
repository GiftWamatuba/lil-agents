"""
lil agents — Windows version
Tiny AI companions that walk across your desktop.
"""

import sys
import os
import time
import threading
import ctypes
import tkinter as tk

sys.path.insert(0, os.path.dirname(__file__))

try:
    import pystray
    from PIL import Image as PILImage, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

from character_window import CharacterWindow, CHAR_HEIGHT
from terminal_window import TerminalWindow
from agent_session import AgentSession, AgentProvider
from themes import THEMES

TICK_MS = 16


class _RECT(ctypes.Structure):
    _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long),
                ('right', ctypes.c_long), ('bottom', ctypes.c_long)]


def _get_workarea():
    rect = _RECT()
    try:
        ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
        return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
    except Exception:
        u = ctypes.windll.user32
        return 0, 0, u.GetSystemMetrics(0), u.GetSystemMetrics(1)


class LilAgentsApp:
    def __init__(self, root: tk.Tk):
        self.root             = root
        self.current_provider = AgentProvider.CLAUDE
        self.current_theme    = 'peach'
        self.characters: list[CharacterWindow] = []
        self._sessions:  dict[str, AgentSession]  = {}
        self._terminals: dict[str, TerminalWindow] = {}
        self._last_tick = time.time()

        self._workarea = _get_workarea()
        self._create_characters()
        self._setup_tray()
        self.root.after(TICK_MS, self._tick)

    def _dock_area(self):
        wx, wy, ww, wh = self._workarea
        margin = 40
        return wx + margin, ww - margin * 2, wy + wh

    def _create_characters(self):
        self.characters = [
            CharacterWindow(self.root, name='Bruce', x_start_frac=0.3,
                            walk_speed=75, on_clicked=self._on_character_clicked),
            CharacterWindow(self.root, name='Jazz',  x_start_frac=0.7,
                            walk_speed=85, on_clicked=self._on_character_clicked),
        ]

    def _on_character_clicked(self, character: CharacterWindow):
        try:
            name = character.name
            if name not in self._terminals:
                self._terminals[name] = TerminalWindow(
                    root=self.root, character_name=name,
                    provider_name=self.current_provider.display_name,
                    theme_name=self.current_theme,
                    on_send=lambda msg, n=name: self._on_user_send(n, msg),
                    on_close=lambda n=name: self._on_terminal_close(n),
                )
            self._terminals[name].show()
            if name not in self._sessions:
                self._start_session(name)
        except Exception as e:
            import traceback; traceback.print_exc()

    def _start_session(self, character_name: str):
        session  = AgentSession(self.current_provider)
        terminal = self._terminals.get(character_name)
        char     = self._char_by_name(character_name)

        def on_text(text):
            if terminal: terminal.append_text(text, 'assistant')

        def on_error(text):
            if terminal: terminal.append_text(f'Error: {text}\n', 'error')
            if char: self.root.after(0, lambda: char.set_busy(False))

        def on_tool_use(name, _i):
            if terminal: terminal.append_text(f'  [{name}]\n', 'system')

        def on_session_ready():
            if terminal:
                terminal.append_text(
                    f'{self.current_provider.display_name} ready. Say hi!\n', 'system')

        def on_turn_complete():
            if terminal:
                terminal.append_text('\n', 'assistant')
                terminal.set_input_sensitive(True)
            if char:
                self.root.after(0, lambda: char.set_busy(False))
                self.root.after(0, lambda: char.show_bubble('done!', 3.0))

        def on_process_exit():
            if terminal:
                terminal.append_text('\n[session ended]\n', 'error')
                terminal.set_input_sensitive(False)
            if char: self.root.after(0, lambda: char.set_busy(False))

        session.on_text          = lambda t:    self.root.after(0, lambda: on_text(t))
        session.on_error         = lambda t:    self.root.after(0, lambda: on_error(t))
        session.on_tool_use      = lambda n, i: self.root.after(0, lambda: on_tool_use(n, i))
        session.on_session_ready = lambda:      self.root.after(0, on_session_ready)
        session.on_turn_complete = lambda:      self.root.after(0, on_turn_complete)
        session.on_process_exit  = lambda:      self.root.after(0, on_process_exit)

        self._sessions[character_name] = session
        session.start()

    def _on_user_send(self, character_name: str, message: str):
        session  = self._sessions.get(character_name)
        terminal = self._terminals.get(character_name)
        char     = self._char_by_name(character_name)

        if not session or not session.is_running:
            if terminal: terminal.append_text('Starting session…\n', 'system')
            self._start_session(character_name)
            self.root.after(1500, lambda: self._retry_send(character_name, message))
            return

        if terminal: terminal.set_input_sensitive(False)
        if char: char.set_busy(True)
        session.send(message)

    def _retry_send(self, character_name: str, message: str):
        session = self._sessions.get(character_name)
        if session and session.is_running:
            self._on_user_send(character_name, message)

    def _on_terminal_close(self, character_name: str):
        session = self._sessions.pop(character_name, None)
        if session: session.terminate()

    def _setup_tray(self):
        if not HAS_TRAY:
            return

        img  = PILImage.new('RGBA', (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([8, 16, 56, 60], fill=(220, 100, 120, 255))
        draw.ellipse([20, 28, 30, 38], fill=(255, 240, 220, 255))
        draw.ellipse([34, 28, 44, 38], fill=(255, 240, 220, 255))

        def provider_item(p):
            return pystray.MenuItem(
                p.display_name,
                lambda icon, item, _p=p: self.root.after(0, lambda: self._on_provider_select(_p)),
                checked=lambda item, _p=p: self.current_provider == _p,
                radio=True,
            )

        def theme_item(key, data):
            return pystray.MenuItem(
                data['name'],
                lambda icon, item, _k=key: self.root.after(0, lambda: self._on_theme_select(_k)),
                checked=lambda item, _k=key: self.current_theme == _k,
                radio=True,
            )

        menu = pystray.Menu(
            pystray.MenuItem('lil agents', None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('AI Provider',
                pystray.Menu(*[provider_item(p) for p in AgentProvider])),
            pystray.MenuItem('Theme',
                pystray.Menu(*[theme_item(k, v) for k, v in THEMES.items()])),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Quit lil agents',
                lambda icon, item: self.root.after(0, self._quit)),
        )

        self._tray = pystray.Icon('lil-agents', img, 'lil agents', menu)
        threading.Thread(target=self._tray.run, daemon=True).start()

    def _on_provider_select(self, provider):
        self.current_provider = provider
        for s in self._sessions.values(): s.terminate()
        self._sessions.clear()
        for t in self._terminals.values():
            t.update_provider(provider.display_name, self.current_theme)

    def _on_theme_select(self, theme_key):
        self.current_theme = theme_key

    def _quit(self):
        for s in self._sessions.values(): s.terminate()
        if hasattr(self, '_tray'):
            try: self._tray.stop()
            except Exception: pass
        self.root.destroy()

    def _tick(self):
        now = time.time()
        dt  = now - self._last_tick
        self._last_tick = now
        dock_x, dock_width, dock_y = self._dock_area()
        for char in self.characters:
            char.update(dock_x, dock_width, dock_y, dt)
        self.root.after(TICK_MS, self._tick)

    def _char_by_name(self, name):
        return next((c for c in self.characters if c.name == name), None)


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    root.withdraw()
    LilAgentsApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
