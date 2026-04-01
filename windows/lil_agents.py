"""
lil agents — Windows version
Tiny AI companions that walk across your desktop.
"""

import sys
import os
import time
import random
import ctypes
import threading
import tkinter as tk

# Ensure the windows/ directory is on sys.path when run from another location.
sys.path.insert(0, os.path.dirname(__file__))

try:
    import pystray
    from PIL import Image as PILImage
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

from character_window import CharacterWindow, CHAR_HEIGHT
from terminal_window import TerminalWindow
from agent_session import AgentSession, AgentProvider
from themes import THEMES

TICK_MS = 16   # ~60 fps


# ── Windows work-area helpers ─────────────────────────────────────────────────

class _RECT(ctypes.Structure):
    _fields_ = [
        ('left',   ctypes.c_long),
        ('top',    ctypes.c_long),
        ('right',  ctypes.c_long),
        ('bottom', ctypes.c_long),
    ]


def _get_workarea():
    """Return (x, y, width, height) of the primary monitor's work area."""
    rect = _RECT()
    SPI_GETWORKAREA = 0x0030
    try:
        ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
        return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
    except Exception:
        # Fallback to full screen dimensions.
        user32 = ctypes.windll.user32
        return 0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


# ── Main application ──────────────────────────────────────────────────────────

class LilAgentsApp:
    def __init__(self, root: tk.Tk):
        self.root             = root
        self.current_provider = AgentProvider.CLAUDE
        self.current_theme    = 'peach'
        self.characters: list[CharacterWindow] = []
        self._sessions:  dict[str, AgentSession]   = {}
        self._terminals: dict[str, TerminalWindow]  = {}
        self._last_tick  = time.time()

        self._workarea = _get_workarea()   # (x, y, w, h)
        self._create_characters()
        self._setup_tray()

        self.root.after(TICK_MS, self._tick)

    # ── Screen geometry ───────────────────────────────────────────────────────

    def _dock_area(self):
        """Return (x_start, width, baseline_y) for character positioning."""
        wx, wy, ww, wh = self._workarea
        margin = 40
        return wx + margin, ww - margin * 2, wy + wh

    # ── Characters ────────────────────────────────────────────────────────────

    def _create_characters(self):
        bruce = CharacterWindow(
            self.root, name='Bruce',
            x_start_frac=0.3, walk_speed=75,
            on_clicked=self._on_character_clicked,
        )
        jazz = CharacterWindow(
            self.root, name='Jazz',
            x_start_frac=0.7, walk_speed=85,
            on_clicked=self._on_character_clicked,
        )
        self.characters = [bruce, jazz]

    def _on_character_clicked(self, character: CharacterWindow):
        try:
            name = character.name
            if name not in self._terminals:
                self._terminals[name] = TerminalWindow(
                    root=self.root,
                    character_name=name,
                    provider_name=self.current_provider.display_name,
                    theme_name=self.current_theme,
                    on_send=lambda msg, n=name: self._on_user_send(n, msg),
                    on_close=lambda n=name: self._on_terminal_close(n),
                )
            self._terminals[name].show()
            if name not in self._sessions:
                self._start_session(name)
        except Exception as e:
            import traceback
            print(f'[lil agents] click error: {e}')
            traceback.print_exc()

    # ── Agent sessions ────────────────────────────────────────────────────────

    def _start_session(self, character_name: str):
        session  = AgentSession(self.current_provider)
        terminal = self._terminals.get(character_name)
        char     = self._char_by_name(character_name)

        def on_text(text):
            if terminal:
                terminal.append_text(text, 'assistant')

        def on_error(text):
            if terminal:
                terminal.append_text(f'Error: {text}\n', 'error')
            if char:
                self.root.after(0, lambda: char.set_busy(False))

        def on_tool_use(name, _input):
            if terminal:
                terminal.append_text(f'  [{name}]\n', 'system')

        def on_session_ready():
            if terminal:
                terminal.append_text(
                    f'{self.current_provider.display_name} ready. Say hi!\n',
                    'system',
                )

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
            if char:
                self.root.after(0, lambda: char.set_busy(False))

        # Bridge background threads → tkinter main thread.
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
            if terminal:
                terminal.append_text('Starting session…\n', 'system')
            self._start_session(character_name)
            self.root.after(
                1500,
                lambda: self._retry_send(character_name, message),
            )
            return

        if terminal:
            terminal.set_input_sensitive(False)
        if char:
            char.set_busy(True)
        session.send(message)

    def _retry_send(self, character_name: str, message: str):
        session = self._sessions.get(character_name)
        if session and session.is_running:
            self._on_user_send(character_name, message)

    def _on_terminal_close(self, character_name: str):
        session = self._sessions.pop(character_name, None)
        if session:
            session.terminate()

    # ── System tray ───────────────────────────────────────────────────────────

    def _setup_tray(self):
        if not HAS_TRAY:
            print('[lil agents] pystray not found — no system tray icon.')
            print('             Install with: pip install pystray pillow')
            return

        icon_img = self._make_tray_icon()

        def provider_item(p):
            return pystray.MenuItem(
                p.display_name,
                lambda icon, item, _p=p: self.root.after(
                    0, lambda: self._on_provider_select(_p)),
                checked=lambda item, _p=p: self.current_provider == _p,
                radio=True,
            )

        def theme_item(key, data):
            return pystray.MenuItem(
                data['name'],
                lambda icon, item, _k=key: self.root.after(
                    0, lambda: self._on_theme_select(_k)),
                checked=lambda item, _k=key: self.current_theme == _k,
                radio=True,
            )

        menu = pystray.Menu(
            pystray.MenuItem('lil agents', None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                'AI Provider',
                pystray.Menu(*[provider_item(p) for p in AgentProvider]),
            ),
            pystray.MenuItem(
                'Theme',
                pystray.Menu(*[theme_item(k, v) for k, v in THEMES.items()]),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                'Quit lil agents',
                lambda icon, item: self.root.after(0, self._quit),
            ),
        )

        self._tray = pystray.Icon('lil-agents', icon_img, 'lil agents', menu)
        threading.Thread(target=self._tray.run, daemon=True).start()

    def _make_tray_icon(self):
        """Generate a simple 64×64 icon for the system tray."""
        img = PILImage.new('RGBA', (64, 64), (0, 0, 0, 0))
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        # Peach circle body
        draw.ellipse([8, 16, 56, 60], fill=(220, 100, 120, 255))
        # Simple face
        draw.ellipse([22, 28, 30, 36], fill=(255, 240, 220, 255))  # left eye
        draw.ellipse([34, 28, 42, 36], fill=(255, 240, 220, 255))  # right eye
        return img

    # ── Tray callbacks ────────────────────────────────────────────────────────

    def _on_provider_select(self, provider: AgentProvider):
        self.current_provider = provider
        for session in self._sessions.values():
            session.terminate()
        self._sessions.clear()
        for terminal in self._terminals.values():
            terminal.update_provider(provider.display_name, self.current_theme)

    def _on_theme_select(self, theme_key: str):
        self.current_theme = theme_key

    def _quit(self):
        for session in self._sessions.values():
            session.terminate()
        if hasattr(self, '_tray'):
            try:
                self._tray.stop()
            except Exception:
                pass
        self.root.destroy()

    # ── Tick loop ─────────────────────────────────────────────────────────────

    def _tick(self):
        now = time.time()
        dt  = now - self._last_tick
        self._last_tick = now

        dock_x, dock_width, dock_y = self._dock_area()
        for char in self.characters:
            char.update(dock_x, dock_width, dock_y, dt)

        self.root.after(TICK_MS, self._tick)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _char_by_name(self, name: str):
        return next((c for c in self.characters if c.name == name), None)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    root.withdraw()   # hide the invisible root window

    # Set DPI awareness so window positions are in physical pixels.
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = LilAgentsApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
