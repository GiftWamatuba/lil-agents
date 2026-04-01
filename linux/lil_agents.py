#!/usr/bin/env python3
"""
lil agents — Linux version
Tiny AI companions that walk across your desktop.
"""

# Force X11 backend so window.move() works under Wayland (via XWayland).
# Must be set before any GDK/GTK import.
import os
os.environ.setdefault('GDK_BACKEND', 'x11')

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib

# Try to load a system tray indicator (AppIndicator3 or Ayatana fallback)
_AppIndicator = None
_IndicatorCategory = None
_IndicatorStatus = None

for _mod_name in ('AppIndicator3', 'AyatanaAppIndicator3'):
    try:
        gi.require_version(_mod_name, '0.1')
        from gi.repository import AppIndicator3 as _AppIndicator  # type: ignore
        _IndicatorCategory = _AppIndicator.IndicatorCategory
        _IndicatorStatus = _AppIndicator.IndicatorStatus
        break
    except (ValueError, ImportError):
        _AppIndicator = None

import sys
import os
import time
import random
import signal

from character_window import CharacterWindow, draw_bruce, draw_jazz, CHAR_HEIGHT
from terminal_window import TerminalWindow
from agent_session import AgentSession, AgentProvider
from themes import THEMES

TICK_MS = 16  # ~60 fps


class LilAgentsApp:
    def __init__(self):
        self.current_provider = AgentProvider.CLAUDE
        self.current_theme = 'peach'
        self.characters: list[CharacterWindow] = []
        self._sessions: dict[str, AgentSession] = {}
        self._terminals: dict[str, TerminalWindow] = {}
        self._last_tick = time.time()

        self._workarea = self._get_workarea()
        self._create_characters()
        self._setup_tray()

        GLib.timeout_add(TICK_MS, self._tick)

    # ------------------------------------------------------------------
    # Screen geometry
    # ------------------------------------------------------------------

    def _get_workarea(self) -> Gdk.Rectangle:
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor()
        if monitor:
            return monitor.get_workarea()
        screen = Gdk.Screen.get_default()
        r = Gdk.Rectangle()
        r.x, r.y, r.width, r.height = 0, 0, screen.get_width(), screen.get_height()
        return r

    def _get_geometry(self) -> Gdk.Rectangle:
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor()
        if monitor:
            return monitor.get_geometry()
        return self._workarea

    def _dock_area(self):
        """Return (x, width, baseline_y) placing characters above the taskbar."""
        wa = self._workarea
        margin = 40
        return (
            wa.x + margin,
            wa.width - margin * 2,
            wa.y + wa.height,
        )

    # ------------------------------------------------------------------
    # Characters
    # ------------------------------------------------------------------

    def _create_characters(self):
        bruce = CharacterWindow(
            name='Bruce',
            draw_func=draw_bruce,
            x_start_frac=0.3,
            walk_speed=75,
            on_clicked=self._on_character_clicked,
        )
        jazz = CharacterWindow(
            name='Jazz',
            draw_func=draw_jazz,
            x_start_frac=0.7,
            walk_speed=85,
            on_clicked=self._on_character_clicked,
        )
        self.characters = [bruce, jazz]

    def _on_character_clicked(self, character: CharacterWindow):
        try:
            name = character.name

            if name not in self._terminals:
                self._terminals[name] = TerminalWindow(
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

    # ------------------------------------------------------------------
    # Agent sessions
    # ------------------------------------------------------------------

    def _start_session(self, character_name: str):
        session = AgentSession(self.current_provider)
        terminal = self._terminals.get(character_name)
        char = self._char_by_name(character_name)

        def on_text(text):
            if terminal:
                terminal.append_text(text, 'assistant')

        def on_error(text):
            if terminal:
                terminal.append_text(f'Error: {text}\n', 'error')
            if char:
                GLib.idle_add(char.set_busy, False)

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
                GLib.idle_add(char.set_busy, False)
                GLib.idle_add(char.show_bubble, 'done!', 3.0)

        def on_process_exit():
            if terminal:
                terminal.append_text('\n[session ended]\n', 'error')
                terminal.set_input_sensitive(False)
            if char:
                GLib.idle_add(char.set_busy, False)

        session.on_text = lambda t: GLib.idle_add(on_text, t)
        session.on_error = lambda t: GLib.idle_add(on_error, t)
        session.on_tool_use = lambda n, i: GLib.idle_add(on_tool_use, n, i)
        session.on_session_ready = lambda: GLib.idle_add(on_session_ready)
        session.on_turn_complete = lambda: GLib.idle_add(on_turn_complete)
        session.on_process_exit = lambda: GLib.idle_add(on_process_exit)

        self._sessions[character_name] = session
        session.start()

    def _on_user_send(self, character_name: str, message: str):
        session = self._sessions.get(character_name)
        terminal = self._terminals.get(character_name)
        char = self._char_by_name(character_name)

        if not session or not session.is_running:
            if terminal:
                terminal.append_text('Starting session…\n', 'system')
            self._start_session(character_name)
            GLib.timeout_add(
                1500,
                lambda: self._retry_send(character_name, message),
            )
            return

        if terminal:
            terminal.set_input_sensitive(False)
        if char:
            char.set_busy(True)
        session.send(message)

    def _retry_send(self, character_name: str, message: str) -> bool:
        session = self._sessions.get(character_name)
        if session and session.is_running:
            self._on_user_send(character_name, message)
        return False  # do not repeat

    def _on_terminal_close(self, character_name: str):
        session = self._sessions.pop(character_name, None)
        if session:
            session.terminate()

    # ------------------------------------------------------------------
    # System tray
    # ------------------------------------------------------------------

    def _setup_tray(self):
        if _AppIndicator:
            ind = _AppIndicator.Indicator.new(
                'lil-agents',
                'application-x-executable',
                _IndicatorCategory.APPLICATION_STATUS,
            )
            ind.set_status(_IndicatorStatus.ACTIVE)
            ind.set_menu(self._build_menu())
            self._indicator = ind
        else:
            icon = Gtk.StatusIcon()
            icon.set_from_icon_name('application-x-executable')
            icon.set_tooltip_text('lil agents')
            icon.connect('popup-menu', self._on_status_popup)
            icon.set_visible(True)
            self._status_icon = icon

    def _on_status_popup(self, icon, button, activate_time):
        menu = self._build_menu()
        menu.show_all()
        menu.popup(None, None, None, None, button, activate_time)

    def _build_menu(self) -> Gtk.Menu:
        menu = Gtk.Menu()

        title = Gtk.MenuItem(label='lil agents')
        title.set_sensitive(False)
        menu.append(title)
        menu.append(Gtk.SeparatorMenuItem())

        # Provider submenu
        provider_item = Gtk.MenuItem(label='AI Provider')
        sub_p = Gtk.Menu()
        for p in AgentProvider:
            item = Gtk.CheckMenuItem(label=p.display_name)
            item.set_active(p == self.current_provider)
            item.connect('activate', self._on_provider_select, p)
            sub_p.append(item)
        provider_item.set_submenu(sub_p)
        menu.append(provider_item)

        # Theme submenu
        theme_item = Gtk.MenuItem(label='Theme')
        sub_t = Gtk.Menu()
        for key, data in THEMES.items():
            item = Gtk.CheckMenuItem(label=data['name'])
            item.set_active(key == self.current_theme)
            item.connect('activate', self._on_theme_select, key)
            sub_t.append(item)
        theme_item.set_submenu(sub_t)
        menu.append(theme_item)

        menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label='Quit lil agents')
        quit_item.connect('activate', self._on_quit)
        menu.append(quit_item)

        menu.show_all()
        return menu

    def _on_provider_select(self, item, provider: AgentProvider):
        if not item.get_active():
            return
        self.current_provider = provider
        for session in list(self._sessions.values()):
            session.terminate()
        self._sessions.clear()
        for terminal in self._terminals.values():
            terminal.update_provider(provider.display_name, self.current_theme)

    def _on_theme_select(self, item, theme_key: str):
        if item.get_active():
            self.current_theme = theme_key

    def _on_quit(self, _widget):
        for session in list(self._sessions.values()):
            session.terminate()
        Gtk.main_quit()

    # ------------------------------------------------------------------
    # Tick loop
    # ------------------------------------------------------------------

    def _tick(self) -> bool:
        now = time.time()
        dt = now - self._last_tick
        self._last_tick = now

        dock_x, dock_width, dock_y = self._dock_area()
        for char in self.characters:
            char.update(dock_x, dock_width, dock_y, dt)

        return True  # keep going

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _char_by_name(self, name: str):
        return next((c for c in self.characters if c.name == name), None)


def main():
    # Keep app alive if the launching terminal is closed.
    try:
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
    except Exception:
        pass
    app = LilAgentsApp()
    Gtk.main()


if __name__ == '__main__':
    main()
