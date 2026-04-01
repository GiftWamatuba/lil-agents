"""Chat popup window — tkinter."""

import tkinter as tk
import tkinter.font as tkFont

from themes import THEMES


def _to_hex(rgba):
    return '#{:02x}{:02x}{:02x}'.format(
        int(rgba[0] * 255), int(rgba[1] * 255), int(rgba[2] * 255))


class TerminalWindow:
    WIN_W = 390
    WIN_H = 500

    def __init__(self, root, character_name, provider_name,
                 theme_name='peach', on_send=None, on_close=None):
        self.root           = root
        self.character_name = character_name
        self.provider_name  = provider_name
        self.theme          = THEMES.get(theme_name, THEMES['peach'])
        self.on_send        = on_send
        self.on_close       = on_close

        self._win          = None
        self._text         = None
        self._input        = None
        self._send_btn     = None
        self._header_label = None
        self._assistant_partial = ''
        self._drag_x = 0
        self._drag_y = 0

        self._build()

    def _build(self):
        theme    = self.theme
        bg       = _to_hex(theme['bg'])
        text_col = _to_hex(theme['text'])
        accent   = _to_hex(theme['accent'])
        border   = _to_hex(theme['border'])
        input_bg = _to_hex(theme['input_bg'])

        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.resizable(False, False)
        win.configure(bg=border)
        win.attributes('-topmost', True)
        win.geometry(f'{self.WIN_W}x{self.WIN_H}')
        win.bind('<Escape>', lambda e: self._close())
        self._win = win

        outer = tk.Frame(win, bg=border, padx=2, pady=2)
        outer.pack(fill='both', expand=True)

        inner = tk.Frame(outer, bg=bg)
        inner.pack(fill='both', expand=True)

        # Header
        header_bg = _to_hex((theme['bg'][0] * 0.94,
                              theme['bg'][1] * 0.94,
                              theme['bg'][2] * 0.94))
        header = tk.Frame(inner, bg=header_bg, height=28)
        header.pack(fill='x', side='top')
        header.pack_propagate(False)
        header.bind('<ButtonPress-1>', self._drag_start)
        header.bind('<B1-Motion>',     self._drag_move)

        label_text = self._format_provider(
            self.provider_name, theme.get('title_format', 'uppercase'))
        hfont = tkFont.Font(family='Helvetica', size=10, weight='bold')
        lbl = tk.Label(header, text=label_text, bg=header_bg,
                       fg=accent, font=hfont, anchor='w', padx=10)
        lbl.pack(side='left')
        lbl.bind('<ButtonPress-1>', self._drag_start)
        lbl.bind('<B1-Motion>',     self._drag_move)
        self._header_label = lbl

        close_btn = tk.Button(header, text='×', bg=header_bg, fg=text_col,
                              font=tkFont.Font(family='Helvetica', size=12, weight='bold'),
                              relief='flat', bd=0, activebackground=border,
                              cursor='hand2', command=self._close)
        close_btn.pack(side='right', padx=6)

        tk.Frame(inner, bg=border, height=1).pack(fill='x')

        # Message area
        msg_frame = tk.Frame(inner, bg=bg)
        msg_frame.pack(fill='both', expand=True, padx=8, pady=(6, 0))

        msg_font  = tkFont.Font(family='Helvetica', size=11)
        bold_font = tkFont.Font(family='Helvetica', size=11, weight='bold')

        text = tk.Text(msg_frame, bg=bg, fg=text_col, font=msg_font,
                       wrap='word', relief='flat', bd=0, padx=4, pady=3,
                       state='disabled', cursor='arrow')
        text.pack(side='left', fill='both', expand=True)

        vsb = tk.Scrollbar(msg_frame, orient='vertical', command=text.yview)
        vsb.pack(side='right', fill='y')
        text.configure(yscrollcommand=vsb.set)

        text.tag_configure('user',      font=bold_font, foreground=text_col)
        text.tag_configure('assistant', font=msg_font,  foreground=text_col)
        text.tag_configure('error',     font=msg_font,  foreground='#cc4444')
        text.tag_configure('system',    foreground='#888888',
                           font=tkFont.Font(family='Helvetica', size=11, slant='italic'))
        text.tag_configure('accent',    font=bold_font, foreground=accent)

        self._text = text
        self._vsb  = vsb

        tk.Frame(inner, bg=border, height=1).pack(fill='x')

        # Input bar
        input_frame = tk.Frame(inner, bg=bg, pady=6, padx=8)
        input_frame.pack(fill='x', side='bottom')

        inp = tk.Text(input_frame, bg=input_bg, fg=text_col,
                      font=tkFont.Font(family='Helvetica', size=11),
                      wrap='word', relief='flat', bd=1,
                      highlightthickness=1, highlightbackground=border,
                      highlightcolor=accent, padx=6, pady=4, height=3)
        inp.pack(side='left', fill='x', expand=True)
        inp.bind('<Return>',   self._on_return)
        inp.bind('<KP_Enter>', self._on_return)
        self._input = inp
        inp.focus_set()

        send_btn = tk.Button(input_frame, text='▶',
                             bg=_to_hex(theme['accent']), fg='white',
                             font=tkFont.Font(family='Helvetica', size=11, weight='bold'),
                             relief='flat', bd=0, padx=8, pady=4,
                             cursor='hand2', command=self._send)
        send_btn.pack(side='right', padx=(6, 0))
        self._send_btn = send_btn

    def _format_provider(self, name, fmt):
        if fmt == 'uppercase':
            return name.upper()
        elif fmt == 'lowercase_tilde':
            return f'{name.lower()} ~'
        return name

    def _drag_start(self, event):
        self._drag_x = event.x_root - self._win.winfo_x()
        self._drag_y = event.y_root - self._win.winfo_y()

    def _drag_move(self, event):
        self._win.geometry(f'+{event.x_root - self._drag_x}+{event.y_root - self._drag_y}')

    def _on_return(self, event):
        if event.state & 0x0001:
            return None
        self._send()
        return 'break'

    def _send(self):
        text = self._input.get('1.0', 'end').strip()
        if not text:
            return
        self._input.delete('1.0', 'end')
        self.append_text(f'> {text}\n', 'user')
        if self.on_send:
            self.on_send(text)

    def _close(self):
        self._win.withdraw()
        if self.on_close:
            self.on_close()

    def show(self):
        if not self._win.winfo_viewable():
            mx = self._win.winfo_pointerx()
            my = self._win.winfo_pointery()
            sw = self._win.winfo_screenwidth()
            sh = self._win.winfo_screenheight()
            x  = max(0, min(mx - self.WIN_W // 2, sw - self.WIN_W))
            y  = max(0, min(my - self.WIN_H - 20, sh - self.WIN_H))
            self._win.geometry(f'{self.WIN_W}x{self.WIN_H}+{x}+{y}')
        self._win.deiconify()
        self._win.lift()
        if self._input:
            self._input.focus_set()

    def hide(self):
        self._win.withdraw()

    def append_text(self, text, tag='assistant'):
        def _do():
            try:
                if not self._text or not self._text.winfo_exists():
                    return
                at_bottom = self._is_at_bottom()
                t = self._text
                t.configure(state='normal')
                if tag == 'assistant':
                    self._append_assistant_markdown(text)
                else:
                    t.insert('end', text, tag)
                t.configure(state='disabled')
                if at_bottom:
                    t.see('end')
            except Exception:
                pass
        try:
            if self.root.winfo_exists():
                self.root.after(0, _do)
        except Exception:
            pass

    def _is_at_bottom(self):
        try:
            return float(self._vsb.get()[1]) >= 0.99
        except Exception:
            return True

    def _append_assistant_markdown(self, text):
        self._assistant_partial += text
        while '\n' in self._assistant_partial:
            line, self._assistant_partial = self._assistant_partial.split('\n', 1)
            self._append_assistant_line(line + '\n')

    def _append_assistant_line(self, line):
        if line.strip().startswith(('- ', '* ')):
            self._text.insert('end', '  • ', 'accent')
            self._insert_inline_markup(line[2:], 'assistant')
            return
        self._insert_inline_markup(line, 'assistant')

    def _insert_inline_markup(self, text, default_tag):
        pos = 0
        while True:
            start = text.find('**', pos)
            if start == -1:
                self._text.insert('end', text[pos:], default_tag)
                break
            close = text.find('**', start + 2)
            if close == -1:
                self._text.insert('end', text[pos:], default_tag)
                break
            if start > pos:
                self._text.insert('end', text[pos:start], default_tag)
            self._text.insert('end', text[start + 2:close], 'user')
            pos = close + 2

    def set_input_sensitive(self, sensitive):
        state = 'normal' if sensitive else 'disabled'
        def _do():
            try:
                if self._input and self._input.winfo_exists():
                    self._input.configure(state=state)
                if self._send_btn and self._send_btn.winfo_exists():
                    self._send_btn.configure(state=state)
            except Exception:
                pass
        try:
            if self.root.winfo_exists():
                self.root.after(0, _do)
        except Exception:
            pass

    def update_provider(self, provider_name, theme_name=None):
        self.provider_name = provider_name
        if theme_name:
            self.theme = THEMES.get(theme_name, self.theme)
        if self._header_label:
            fmt  = self.theme.get('title_format', 'uppercase')
            text = self._format_provider(provider_name, fmt)
            try:
                if self.root.winfo_exists():
                    self.root.after(0, lambda: self._header_label.configure(text=text))
            except Exception:
                pass
