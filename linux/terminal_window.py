"""Chat/terminal popup window."""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Pango

from themes import THEMES


class TerminalWindow:
    def __init__(self, character_name, provider_name, theme_name='peach',
                 on_send=None, on_close=None):
        self.character_name = character_name
        self.provider_name = provider_name
        self.theme = THEMES.get(theme_name, THEMES['peach'])
        self.on_send = on_send
        self.on_close = on_close

        self._window = None
        self._shell = None
        self._text_view = None
        self._text_buffer = None
        self._input_view = None
        self._input_buffer = None
        self._send_btn = None
        self._close_btn = None
        self._assistant_partial = ""
        self._build()

    def _build(self):
        win = Gtk.Window()
        win.set_title(f'lil agents — {self.character_name}')
        win.set_default_size(390, 500)
        win.set_resizable(False)
        win.set_decorated(False)
        win.set_app_paintable(False)
        screen = win.get_screen()
        if screen is not None:
            visual = screen.get_system_visual()
            if visual is not None:
                win.set_visual(visual)
        win.connect('delete-event', self._on_delete)
        win.connect('key-press-event', self._on_key_press)
        win.set_name('chat-window')
        self._window = win

        self._apply_theme()

        shell = Gtk.EventBox()
        shell.set_name('chat-shell')
        win.add(shell)
        self._shell = shell

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        shell.add(vbox)
        self._root = vbox

        # Header
        header = Gtk.Label()
        theme_fmt = self.theme.get('title_format', 'uppercase')
        label_text = self._format_provider(self.provider_name, theme_fmt)
        accent = self.theme.get('accent', (0.85, 0.35, 0.45, 1.0))
        accent_hex = '#{:02x}{:02x}{:02x}'.format(
            int(accent[0] * 255),
            int(accent[1] * 255),
            int(accent[2] * 255),
        )
        header.set_markup(f'<span foreground="{accent_hex}"><b>{label_text}</b></span>')
        header.override_font(Pango.FontDescription('Sans Bold 11'))
        header.set_margin_top(4)
        header.set_margin_bottom(4)
        self._header = header
        header_wrap = Gtk.EventBox()
        header_wrap.set_name('chat-header')
        header_wrap.set_size_request(-1, 26)
        header_wrap.connect('button-press-event', self._on_header_drag)
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        header_wrap.add(inner)
        inner.pack_start(header, False, False, 12)
        inner.pack_start(Gtk.Box(), True, True, 0)
        close_btn = Gtk.Button(label='×')
        close_btn.set_name('chat-close')
        close_btn.set_relief(Gtk.ReliefStyle.NONE)
        close_btn.connect('clicked', self._on_close_clicked)
        close_btn.set_tooltip_text('Close chat (Esc)')
        close_btn.set_can_focus(True)
        inner.pack_start(close_btn, False, False, 8)
        self._close_btn = close_btn
        vbox.pack_start(header_wrap, False, False, 0)

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        vbox.pack_start(sep, False, False, 0)

        # Scrolled message area
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_name('chat-scroll')
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_margin_start(10)
        scrolled.set_margin_end(10)
        scrolled.set_margin_top(6)

        tv = Gtk.TextView()
        tv.set_name('chat-body')
        tv.set_editable(False)
        tv.set_cursor_visible(False)
        tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        tv.set_left_margin(4)
        tv.set_right_margin(4)
        tv.set_top_margin(3)
        tv.set_bottom_margin(3)
        tv.set_pixels_above_lines(0)
        tv.set_pixels_below_lines(2)
        tv.override_font(Pango.FontDescription('Sans 12'))
        self._text_view = tv
        light_bg = Gdk.RGBA(0.965, 0.949, 0.925, 1.0)
        tv.override_background_color(Gtk.StateFlags.NORMAL, light_bg)
        scrolled.override_background_color(Gtk.StateFlags.NORMAL, light_bg)

        buf = tv.get_buffer()
        self._text_buffer = buf

        # Message tags
        text_fg = self.theme['text']
        fg_hex = '#{:02x}{:02x}{:02x}'.format(
            int(text_fg[0] * 255),
            int(text_fg[1] * 255),
            int(text_fg[2] * 255),
        )
        buf.create_tag('user', weight=Pango.Weight.BOLD, foreground=fg_hex)
        buf.create_tag('assistant', foreground=fg_hex)
        buf.create_tag('error', foreground='#cc4444')
        buf.create_tag('system', foreground='#888888', style=Pango.Style.ITALIC)
        buf.create_tag('accent', weight=Pango.Weight.BOLD, foreground='#d95a72')

        scrolled.add(tv)
        vbox.pack_start(scrolled, True, True, 0)
        self._scrolled = scrolled

        sep2 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        vbox.pack_start(sep2, False, False, 0)

        # Input bar
        input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        input_box.set_name('chat-input-wrap')
        input_box.set_margin_start(10)
        input_box.set_margin_end(10)
        input_box.set_margin_top(4)
        input_box.set_margin_bottom(10)

        input_scrolled = Gtk.ScrolledWindow()
        input_scrolled.set_name('chat-input-scroll')
        input_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        input_scrolled.set_min_content_height(30)
        input_scrolled.set_max_content_height(84)

        input_view = Gtk.TextView()
        input_view.set_name('chat-input')
        input_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        input_view.set_left_margin(6)
        input_view.set_right_margin(6)
        input_view.set_top_margin(5)
        input_view.set_bottom_margin(5)
        input_view.override_font(Pango.FontDescription('Sans 11'))
        input_view.connect('key-press-event', self._on_input_key_press)
        self._input_view = input_view
        self._input_buffer = input_view.get_buffer()
        input_view.set_tooltip_text(f'Ask {self.provider_name}...')
        input_view.grab_focus()

        input_scrolled.add(input_view)
        input_box.pack_start(input_scrolled, True, True, 0)

        send_btn = Gtk.Button()
        send_btn.set_name('chat-send')
        send_btn.set_relief(Gtk.ReliefStyle.NONE)
        send_btn.set_tooltip_text('Send message')
        send_btn.set_can_focus(True)
        icon = Gtk.Image.new_from_icon_name('mail-send-symbolic', Gtk.IconSize.MENU)
        if icon:
            send_btn.set_image(icon)
            send_btn.set_always_show_image(True)
        else:
            send_btn.set_label('>')
        send_btn.connect('clicked', self._on_send_clicked)
        input_box.pack_start(send_btn, False, False, 6)
        self._send_btn = send_btn

        vbox.pack_start(input_box, False, False, 0)

    def _format_provider(self, name, fmt):
        if fmt == 'uppercase':
            return name.upper()
        elif fmt == 'lowercase_tilde':
            return f'{name.lower()} ~'
        return name

    def _apply_theme(self):
        bg = self.theme['bg']
        text = self.theme['text']
        border = self.theme.get('border', (0.95, 0.55, 0.65, 1.0))
        input_bg = self.theme.get('input_bg', (1.0, 0.98, 0.95, 1.0))
        radius = 0
        border_px = float(self.theme.get('window_border_width', 2.0))
        css = (
            f'#chat-window {{'
            f'  background-color: rgba(246,242,236,1.0);'
            f'  border-radius: 0px;'
            f'  border: 0px;'
            f'}}'
            f'#chat-shell {{'
            f'  background-color: rgba(246,242,236,1.0);'
            f'  border-radius: {radius}px;'
            f'  border: {border_px}px solid rgba(224,124,82,1.0);'
            f'}}'
            f'#chat-header {{'
            f'  background-color: rgba(245,221,199,1.0);'
            f'  border-top-left-radius: {radius}px;'
            f'  border-top-right-radius: {radius}px;'
            f'}}'
            f'#chat-header label {{'
            f'  color: rgba({int(text[0]*255)},{int(text[1]*255)},'
            f'{int(text[2]*255)},{text[3]:.2f});'
            f'}}'
            f'#chat-body {{'
            f'  background-color: rgba(246,242,236,1.0);'
            f'}}'
            f'#chat-scroll, #chat-scroll viewport {{'
            f'  background-color: rgba(246,242,236,1.0);'
            f'}}'
            f'#chat-input {{'
            f'  background-color: transparent;'
            f'  border-radius: 0px;'
            f'  border: 0px;'
            f'  padding: 4px 0px;'
            f'  min-height: 26px;'
            f'  color: rgba(58,52,55,1.0);'
            f'}}'
            f'#chat-input-scroll {{'
            f'  background-color: rgba(248,240,231,1.0);'
            f'  border: 1px solid rgba(224,124,82,0.22);'
            f'  border-radius: 6px;'
            f'}}'
            f'#chat-input-wrap {{'
            f'  background-color: transparent;'
            f'}}'
            f'#chat-send {{'
            f'  min-width: 28px;'
            f'  min-height: 26px;'
            f'  padding: 2px;'
            f'  border-radius: 6px;'
            f'  background-color: rgba(224,124,82,0.16);'
            f'}}'
            f'#chat-send:hover {{'
            f'  background-color: rgba(224,124,82,0.30);'
            f'}}'
            f'#chat-close {{'
            f'  min-width: 26px;'
            f'  min-height: 26px;'
            f'  padding: 0px;'
            f'  border-radius: 6px;'
            f'  background-color: rgba(224,124,82,0.14);'
            f'  color: rgba(130,76,58,1.0);'
            f'  font-weight: 700;'
            f'}}'
            f'#chat-close:hover {{'
            f'  background-color: rgba(224,124,82,0.28);'
            f'  color: rgba(120,62,44,1.0);'
            f'}}'
            f'#chat-window separator {{'
            f'  color: rgba(224,124,82,0.30);'
            f'}}'
        )
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _on_send_clicked(self, widget):
        if not self._input_buffer:
            return
        start = self._input_buffer.get_start_iter()
        end = self._input_buffer.get_end_iter()
        text = self._input_buffer.get_text(start, end, True).strip()
        if not text:
            return
        self._input_buffer.set_text('')
        self.append_text(f'> {text}\n', 'user')
        if self.on_send:
            self.on_send(text)

    def _on_close_clicked(self, _widget):
        self._window.hide()
        if self.on_close:
            self.on_close()

    def _on_key_press(self, _widget, event):
        # Escape is a common and accessible close pattern.
        if event.keyval == Gdk.KEY_Escape:
            self._on_close_clicked(None)
            return True
        return False

    def _on_input_key_press(self, _widget, event):
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if event.state & Gdk.ModifierType.SHIFT_MASK:
                return False  # allow newline insertion
            self._on_send_clicked(_widget)
            return True
        return False

    def _on_header_drag(self, widget, event):
        if event.button == 1:
            self._window.begin_move_drag(
                event.button, int(event.x_root), int(event.y_root), event.time)

    def _on_delete(self, widget, event):
        self._window.hide()
        if self.on_close:
            self.on_close()
        return True  # prevent destroy

    def append_text(self, text, tag='assistant'):
        def _do():
            should_stick = self._should_autoscroll()
            end = self._text_buffer.get_end_iter()
            if tag == 'assistant':
                self._append_assistant_markdown(text)
            else:
                self._text_buffer.insert_with_tags_by_name(end, text, tag)
            if should_stick:
                self._scroll_to_bottom()
        GLib.idle_add(_do)

    def _should_autoscroll(self):
        adj = self._scrolled.get_vadjustment()
        if not adj:
            return True
        return (adj.get_upper() - (adj.get_value() + adj.get_page_size())) <= 24.0

    def _scroll_to_bottom(self):
        adj = self._scrolled.get_vadjustment()
        if adj:
            adj.set_value(adj.get_upper() - adj.get_page_size())

    def _append_assistant_markdown(self, text):
        self._assistant_partial += text
        while '\n' in self._assistant_partial:
            line, self._assistant_partial = self._assistant_partial.split('\n', 1)
            self._append_assistant_line(line + '\n')

    def _append_assistant_line(self, line):
        stripped = line.strip()
        end = self._text_buffer.get_end_iter()
        if stripped.startswith(('- ', '* ')):
            self._text_buffer.insert_with_tags_by_name(end, '  • ', 'accent')
            self._insert_inline_markup(line[2:], 'assistant')
            return
        self._insert_inline_markup(line, 'assistant')

    def _insert_inline_markup(self, text, default_tag):
        pos = 0
        while True:
            start = text.find('**', pos)
            if start == -1:
                end_iter = self._text_buffer.get_end_iter()
                self._text_buffer.insert_with_tags_by_name(end_iter, text[pos:], default_tag)
                break
            close = text.find('**', start + 2)
            if close == -1:
                end_iter = self._text_buffer.get_end_iter()
                self._text_buffer.insert_with_tags_by_name(end_iter, text[pos:], default_tag)
                break
            if start > pos:
                end_iter = self._text_buffer.get_end_iter()
                self._text_buffer.insert_with_tags_by_name(end_iter, text[pos:start], default_tag)
            bold_text = text[start + 2:close]
            end_iter = self._text_buffer.get_end_iter()
            self._text_buffer.insert_with_tags_by_name(end_iter, bold_text, 'user')
            pos = close + 2

    def set_input_sensitive(self, sensitive):
        if self._input_view:
            GLib.idle_add(self._input_view.set_sensitive, sensitive)
        if self._send_btn:
            GLib.idle_add(self._send_btn.set_sensitive, sensitive)

    def update_provider(self, provider_name, theme_name=None):
        self.provider_name = provider_name
        if theme_name:
            self.theme = THEMES.get(theme_name, self.theme)
        if self._input_view:
            GLib.idle_add(self._input_view.set_tooltip_text, f'Ask {provider_name}...')
        if self._header:
            fmt = self.theme.get('title_format', 'uppercase')
            label_text = self._format_provider(provider_name, fmt)
            accent = self.theme.get('accent', (0.85, 0.35, 0.45, 1.0))
            accent_hex = '#{:02x}{:02x}{:02x}'.format(
                int(accent[0] * 255),
                int(accent[1] * 255),
                int(accent[2] * 255),
            )
            GLib.idle_add(
                self._header.set_markup,
                f'<span foreground="{accent_hex}"><b>{label_text}</b></span>'
            )

    def show(self):
        if not self._window.get_visible():
            self._window.set_position(Gtk.WindowPosition.MOUSE)
        self._window.show_all()
        self._window.present()

    def hide(self):
        self._window.hide()
