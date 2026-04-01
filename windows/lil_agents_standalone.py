"""
lil agents — standalone Windows version
Just the walking characters, no AI required.

Dependencies: pip install pillow pystray
"""

import sys
import os
import time
import random
import ctypes
import threading
import tkinter as tk
import shutil
import subprocess

sys.path.insert(0, os.path.dirname(__file__))

try:
    from PIL import Image as PILImage, ImageTk, ImageDraw
    HAS_PIL = True
except ImportError:
    print('ERROR: Pillow not installed. Run: pip install pillow')
    sys.exit(1)

try:
    import pystray
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False


def _resource_dir():
    if hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


# ── Constants ─────────────────────────────────────────────────────────────────

CHAR_WIDTH  = 56
CHAR_HEIGHT = 98
WIN_HEIGHT  = CHAR_HEIGHT
_KEY_COLOR  = '#010101'
_SPRITE_FPS = 30.0
_SPRITE_CACHE: dict = {}
TICK_MS = 16


# ── Windows work area ─────────────────────────────────────────────────────────

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


# ── Sprite loading ────────────────────────────────────────────────────────────

def _sprite_config(name):
    if name.lower() == 'jazz':
        return {'idle_frame': 0,
                'walk_start': int(4.5  * _SPRITE_FPS),
                'walk_end':   int(8.75 * _SPRITE_FPS),
                'y_offset': 1, 'flip_x_offset': -3}
    return     {'idle_frame': 0,
                'walk_start': int(3.75 * _SPRITE_FPS),
                'walk_end':   int(8.5  * _SPRITE_FPS),
                'y_offset': 3, 'flip_x_offset': 0}


def _remove_black_bg(png_path, tolerance=18, feather=18):
    try:
        import numpy as np
        img  = PILImage.open(png_path).convert('RGB')
        data = np.array(img, dtype=np.float32)
        dist  = np.sqrt((data ** 2).sum(axis=2))
        alpha = np.clip((dist - tolerance) / max(feather, 1) * 255, 0, 255).astype(np.uint8)
        rgba  = np.zeros((*data.shape[:2], 4), dtype=np.uint8)
        rgba[:, :, :3] = data.astype(np.uint8)
        rgba[:, :,  3] = alpha
        PILImage.fromarray(rgba, 'RGBA').save(png_path)
    except Exception:
        pass


def _load_sprites(name):
    key = name.lower()
    if key in _SPRITE_CACHE:
        return _SPRITE_CACHE[key]

    base      = _resource_dir()
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    candidates = [
        os.path.join(base, 'sprites', key),
        os.path.join(os.path.dirname(__file__), 'sprites', key),
        os.path.join(repo_root, '.cache', 'windows-sprites', key),
        os.path.join(repo_root, '.cache', 'linux-sprites', key),
    ]
    frames_dir = None
    for c in candidates:
        if os.path.isdir(c):
            files = sorted(f for f in os.listdir(c)
                           if f.startswith('frame-') and f.endswith('.png'))
            if files:
                frames_dir = c
                break

    if frames_dir is None:
        mov = os.path.join(repo_root, 'LilAgents', f'walk-{key}-01.mov')
        ff  = shutil.which('ffmpeg') or shutil.which('ffmpeg.exe')
        dst = os.path.join(repo_root, '.cache', 'windows-sprites', key)
        if os.path.exists(mov) and ff:
            os.makedirs(dst, exist_ok=True)
            print(f'[lil agents] Extracting {key} sprites (one-time, ~30 s)…')
            subprocess.run(
                [ff, '-v', 'error', '-y', '-i', mov,
                 '-vf', f'fps={int(_SPRITE_FPS)},scale={CHAR_WIDTH}:{CHAR_HEIGHT}:flags=lanczos',
                 '-pix_fmt', 'rgb24',
                 os.path.join(dst, 'frame-%04d.png')],
                check=False, creationflags=0x08000000)
            extracted = sorted(f for f in os.listdir(dst)
                               if f.startswith('frame-') and f.endswith('.png'))
            print(f'[lil agents] Removing background from {len(extracted)} frames…')
            for fn in extracted:
                _remove_black_bg(os.path.join(dst, fn))
            if extracted:
                frames_dir = dst

    if frames_dir is None:
        _SPRITE_CACHE[key] = []
        return []

    frames = []
    for fn in sorted(f for f in os.listdir(frames_dir)
                     if f.startswith('frame-') and f.endswith('.png')):
        try:
            img = PILImage.open(os.path.join(frames_dir, fn)).convert('RGBA')
            if img.size != (CHAR_WIDTH, CHAR_HEIGHT):
                img = img.resize((CHAR_WIDTH, CHAR_HEIGHT), PILImage.LANCZOS)
            frames.append(img)
        except Exception:
            pass

    _SPRITE_CACHE[key] = frames
    return frames


# ── Character window ──────────────────────────────────────────────────────────

class CharacterWindow:
    def __init__(self, root, name, x_start_frac=0.3, walk_speed=75):
        self.root              = root
        self.name              = name
        self.position_progress = x_start_frac
        self.direction         = 1
        self._walk_speed       = walk_speed + random.uniform(-8, 8)

        self._sprite_cfg    = _sprite_config(name)
        self._sprite_frames = _load_sprites(name)
        self._sprite_index  = self._sprite_cfg['idle_frame']
        self._sprite_timer  = 0.0
        self._pause_until   = time.time() + random.uniform(0.5, 3.0)
        self._target        = random.uniform(0.4, 0.85)
        self._photo         = None
        self._build()

    def _build(self):
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes('-topmost', True)
        win.attributes('-transparentcolor', _KEY_COLOR)
        win.configure(bg=_KEY_COLOR)
        win.resizable(False, False)

        canvas = tk.Canvas(win, width=CHAR_WIDTH, height=WIN_HEIGHT,
                           bg=_KEY_COLOR, highlightthickness=0, cursor='hand2')
        canvas.pack()
        win.geometry(f'{CHAR_WIDTH}x{WIN_HEIGHT}+0+0')

        self._win    = win
        self._canvas = canvas

    def _render(self):
        c = self._canvas
        c.delete('all')
        if not self._sprite_frames:
            return

        idx   = self._sprite_index % len(self._sprite_frames)
        frame = self._sprite_frames[idx].copy()
        flip_x = 0
        if self.direction < 0:
            frame  = frame.transpose(PILImage.FLIP_LEFT_RIGHT)
            flip_x = self._sprite_cfg.get('flip_x_offset', 0)

        out = PILImage.new('RGB', (CHAR_WIDTH, WIN_HEIGHT), (1, 1, 1))
        r, g, b, a = frame.split()
        out.paste(frame.convert('RGB'), (flip_x, 0), mask=a)

        photo       = ImageTk.PhotoImage(out)
        self._photo = photo
        c.create_image(0, 0, anchor='nw', image=photo)

    def update(self, dock_x, dock_width, dock_y, dt):
        now = time.time()
        if now >= self._pause_until:
            speed_frac = self._walk_speed / max(dock_width, 1)
            self.position_progress += self.direction * speed_frac * dt

            if self.direction > 0 and self.position_progress >= self._target:
                self.direction         = -1
                self.position_progress = self._target
                self._pause_until      = now + random.uniform(2.0, 7.0)
                self._target = random.uniform(0.05, max(0.06, self.position_progress - 0.1))
            elif self.direction < 0 and self.position_progress <= self._target:
                self.direction         = 1
                self.position_progress = self._target
                self._pause_until      = now + random.uniform(2.0, 7.0)
                self._target = random.uniform(min(0.94, self.position_progress + 0.1), 0.94)

            self.position_progress = max(0.0, min(1.0, self.position_progress))

            self._sprite_timer += dt
            if self._sprite_frames and self._sprite_timer >= (1.0 / _SPRITE_FPS):
                cfg   = self._sprite_cfg
                start = max(0, min(cfg['walk_start'], len(self._sprite_frames) - 1))
                end   = max(start, min(cfg['walk_end'],   len(self._sprite_frames) - 1))
                if self._sprite_index < start or self._sprite_index > end:
                    self._sprite_index = start
                else:
                    self._sprite_index += 1
                    if self._sprite_index > end:
                        self._sprite_index = start
                self._sprite_timer = 0.0
        else:
            if self._sprite_frames:
                self._sprite_index = min(self._sprite_cfg['idle_frame'],
                                         len(self._sprite_frames) - 1)

        y_offset = self._sprite_cfg.get('y_offset', 0)
        px = int(dock_x + self.position_progress * dock_width - CHAR_WIDTH / 2)
        py = int(dock_y - CHAR_HEIGHT + y_offset)
        self._win.geometry(f'{CHAR_WIDTH}x{WIN_HEIGHT}+{px}+{py}')
        self._render()


# ── App ───────────────────────────────────────────────────────────────────────

class LilAgentsApp:
    def __init__(self, root: tk.Tk):
        self.root       = root
        self._workarea  = _get_workarea()
        self._last_tick = time.time()

        self.characters = [
            CharacterWindow(root, 'Bruce', x_start_frac=0.3, walk_speed=75),
            CharacterWindow(root, 'Jazz',  x_start_frac=0.7, walk_speed=85),
        ]

        self._setup_tray()
        self.root.after(TICK_MS, self._tick)

    def _dock_area(self):
        wx, wy, ww, wh = self._workarea
        return wx + 40, ww - 80, wy + wh

    def _tick(self):
        now = time.time()
        dt  = now - self._last_tick
        self._last_tick = now
        dock_x, dock_width, dock_y = self._dock_area()
        for char in self.characters:
            char.update(dock_x, dock_width, dock_y, dt)
        self.root.after(TICK_MS, self._tick)

    def _setup_tray(self):
        if not HAS_TRAY:
            print('[lil agents] No system tray (pip install pystray to add it).')
            print('             Close the console window to quit.')
            return

        img  = PILImage.new('RGBA', (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([8, 16, 56, 60], fill=(220, 100, 120, 255))
        draw.ellipse([20, 28, 30, 38], fill=(255, 240, 220, 255))
        draw.ellipse([34, 28, 44, 38], fill=(255, 240, 220, 255))

        menu = pystray.Menu(
            pystray.MenuItem('lil agents', None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Quit', lambda icon, item: self.root.after(0, self._quit)),
        )
        self._tray = pystray.Icon('lil-agents', img, 'lil agents', menu)
        threading.Thread(target=self._tray.run, daemon=True).start()

    def _quit(self):
        if hasattr(self, '_tray'):
            try: self._tray.stop()
            except Exception: pass
        self.root.destroy()


# ── Entry point ───────────────────────────────────────────────────────────────

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
