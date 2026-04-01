"""Animated character windows for Windows — tkinter + Pillow."""

import tkinter as tk
import math
import random
import time
import os
import shutil
import subprocess

try:
    from PIL import Image as PILImage, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

CHAR_WIDTH  = 56
CHAR_HEIGHT = 98
BUBBLE_AREA = 35          # pixels above character reserved for speech bubble
WIN_HEIGHT  = CHAR_HEIGHT + BUBBLE_AREA
_KEY_COLOR  = '#010101'   # chroma-key color for per-pixel transparency

_WALK_FRAMES = 8
_SPRITE_FPS  = 30.0
_SPRITE_CACHE: dict = {}

# Sprite timing config per character (same values as Linux version).
def _sprite_config(name):
    key = name.lower()
    if key == 'jazz':
        return {
            'idle_frame': 0,
            'walk_start': int(4.5 * _SPRITE_FPS),
            'walk_end':   int(8.75 * _SPRITE_FPS),
        }
    return {
        'idle_frame': 0,
        'walk_start': int(3.75 * _SPRITE_FPS),
        'walk_end':   int(8.5  * _SPRITE_FPS),
    }


def _remove_black_bg(png_path, tolerance=18, feather=18):
    """Replace near-black background pixels with transparency in-place."""
    if not HAS_PIL:
        return
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
    except ImportError:
        pass
    except Exception:
        pass


def _load_sprite_frames(name):
    """Load PNG frames as RGBA PIL Images, extracting via ffmpeg if needed."""
    if not HAS_PIL:
        _SPRITE_CACHE[name.lower()] = []
        return []

    key = name.lower()
    if key in _SPRITE_CACHE:
        return _SPRITE_CACHE[key]

    repo_root  = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    linux_cache  = os.path.join(repo_root, '.cache', 'linux-sprites', key)
    win_cache    = os.path.join(repo_root, '.cache', 'windows-sprites', key)
    sprites_dir  = os.path.join(os.path.dirname(__file__), 'sprites', key)

    frames_dir = None
    for candidate in (sprites_dir, win_cache, linux_cache):
        if os.path.isdir(candidate):
            files = sorted(
                f for f in os.listdir(candidate)
                if f.startswith('frame-') and f.endswith('.png')
            )
            if files:
                frames_dir = candidate
                break

    # Extract at runtime using ffmpeg if frames not yet cached.
    if frames_dir is None:
        mov_path   = os.path.join(repo_root, 'LilAgents', f'walk-{key}-01.mov')
        ffmpeg_bin = shutil.which('ffmpeg') or shutil.which('ffmpeg.exe')
        if os.path.exists(mov_path) and ffmpeg_bin:
            os.makedirs(win_cache, exist_ok=True)
            print(f'[lil agents] Extracting {key} sprites (one-time, ~30 s)…')
            subprocess.run(
                [
                    ffmpeg_bin, '-v', 'error', '-y',
                    '-i', mov_path,
                    '-vf', f'fps={int(_SPRITE_FPS)},scale={CHAR_WIDTH}:{CHAR_HEIGHT}:flags=lanczos',
                    '-pix_fmt', 'rgb24',
                    os.path.join(win_cache, 'frame-%04d.png'),
                ],
                check=False,
                creationflags=0x08000000,   # CREATE_NO_WINDOW
            )
            extracted = sorted(
                f for f in os.listdir(win_cache)
                if f.startswith('frame-') and f.endswith('.png')
            )
            print(f'[lil agents] Removing background from {len(extracted)} frames…')
            for fn in extracted:
                _remove_black_bg(os.path.join(win_cache, fn))
            if extracted:
                frames_dir = win_cache

    if frames_dir is None:
        _SPRITE_CACHE[key] = []
        return []

    all_files = sorted(
        f for f in os.listdir(frames_dir)
        if f.startswith('frame-') and f.endswith('.png')
    )
    frames = []
    for fn in all_files:
        try:
            img = PILImage.open(os.path.join(frames_dir, fn)).convert('RGBA')
            if img.size != (CHAR_WIDTH, CHAR_HEIGHT):
                img = img.resize((CHAR_WIDTH, CHAR_HEIGHT), PILImage.LANCZOS)
            frames.append(img)
        except Exception:
            pass

    _SPRITE_CACHE[key] = frames
    return frames


class _Bubble:
    def __init__(self, text, expiry):
        self.text   = text
        self.expiry = expiry


class CharacterWindow:
    THINKING_PHRASES = [
        "hmm...", "thinking...", "on it!", "let me see...",
        "processing...", "almost...", "working...", "hold on...",
    ]

    def __init__(self, root, name, x_start_frac=0.3,
                 walk_speed=75, on_clicked=None):
        self.root              = root
        self.name              = name
        self.position_progress = x_start_frac
        self.direction         = 1
        self._walk_speed       = walk_speed + random.uniform(-8, 8)
        self._bubble           = None
        self.on_clicked        = on_clicked

        self._sprite_cfg    = _sprite_config(name)
        self._sprite_frames = _load_sprite_frames(name)
        self._sprite_index  = self._sprite_cfg['idle_frame']
        self._sprite_timer  = 0.0
        self._pause_until   = time.time() + random.uniform(0.5, 3.0)
        self._target        = random.uniform(0.4, 0.85)

        self._win    = None
        self._canvas = None
        self._photo  = None   # keep ImageTk ref alive
        self._build()

    def _build(self):
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes('-topmost', True)
        win.attributes('-transparentcolor', _KEY_COLOR)
        win.configure(bg=_KEY_COLOR)
        win.resizable(False, False)

        canvas = tk.Canvas(
            win,
            width=CHAR_WIDTH,
            height=WIN_HEIGHT,
            bg=_KEY_COLOR,
            highlightthickness=0,
            cursor='hand2',
        )
        canvas.pack()
        canvas.bind('<Button-1>', self._on_click)

        win.geometry(f'{CHAR_WIDTH}x{WIN_HEIGHT}+0+0')
        self._win    = win
        self._canvas = canvas

    # ── Rendering ────────────────────────────────────────────────────────────

    def _render(self):
        c = self._canvas
        c.delete('all')

        if self._sprite_frames and HAS_PIL:
            idx      = self._sprite_index % len(self._sprite_frames)
            frame    = self._sprite_frames[idx].copy()

            if self.direction < 0:
                frame = frame.transpose(PILImage.FLIP_LEFT_RIGHT)

            # Composite character onto the chroma-key background.
            out = PILImage.new('RGB', (CHAR_WIDTH, WIN_HEIGHT), (1, 1, 1))
            r, g, b, a = frame.split()
            out.paste(frame.convert('RGB'), (0, BUBBLE_AREA), mask=a)

            photo        = ImageTk.PhotoImage(out)
            self._photo  = photo          # prevent GC
            c.create_image(0, 0, anchor='nw', image=photo)

        # Draw speech bubble if active.
        if self._bubble and time.time() < self._bubble.expiry:
            self._draw_bubble(self._bubble.text)

    def _draw_bubble(self, text):
        c    = self._canvas
        font = ('Helvetica', 8, 'bold')
        pad  = 5

        # Estimate text dimensions.
        tmp = tk.Label(self.root, text=text, font=font)
        tmp.update_idletasks()
        tw = tmp.winfo_reqwidth()
        th = tmp.winfo_reqheight()
        tmp.destroy()

        bw = tw + pad * 2 + 4
        bh = th + pad * 2
        bx = max(0, CHAR_WIDTH // 2 - bw // 2)
        by = 2

        # Shadow
        c.create_rectangle(
            bx + 1, by + 2, bx + bw + 1, by + bh + 2,
            fill='#00000022', outline='', )
        # Bubble body
        c.create_rectangle(
            bx, by, bx + bw, by + bh,
            fill='#fff5eb', outline='#e08a8a', width=1,
        )
        # Arrow pointing down to character
        mx = CHAR_WIDTH // 2
        c.create_polygon(
            mx - 4, by + bh,
            mx,     by + bh + 5,
            mx + 4, by + bh,
            fill='#fff5eb', outline='',
        )
        # Text
        c.create_text(
            bx + pad + 2, by + pad,
            anchor='nw', text=text,
            fill='#887080', font=font,
        )

    # ── Events ───────────────────────────────────────────────────────────────

    def _on_click(self, _event):
        if self.on_clicked:
            self.on_clicked(self)

    # ── Public API ───────────────────────────────────────────────────────────

    def show_bubble(self, text, duration=4.0):
        self._bubble = _Bubble(text, time.time() + duration)

    def set_busy(self, busy):
        if busy:
            self.show_bubble(random.choice(self.THINKING_PHRASES), duration=9999)
        else:
            self._bubble = None

    def update(self, dock_x, dock_width, dock_y, dt):
        now = time.time()

        if now >= self._pause_until:
            speed_frac = self._walk_speed / max(dock_width, 1)
            self.position_progress += self.direction * speed_frac * dt

            if self.direction > 0 and self.position_progress >= self._target:
                self.direction         = -1
                self.position_progress = self._target
                self._pause_until      = now + random.uniform(2.0, 7.0)
                self._target = random.uniform(
                    0.05, max(0.06, self.position_progress - 0.1))
            elif self.direction < 0 and self.position_progress <= self._target:
                self.direction         = 1
                self.position_progress = self._target
                self._pause_until      = now + random.uniform(2.0, 7.0)
                self._target = random.uniform(
                    min(0.94, self.position_progress + 0.1), 0.94)

            self.position_progress = max(0.0, min(1.0, self.position_progress))

            # Advance sprite frame while walking.
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
            # Idle frame while paused.
            if self._sprite_frames:
                self._sprite_index = min(
                    self._sprite_cfg['idle_frame'],
                    len(self._sprite_frames) - 1,
                )

        # Position window: character bottom sits at dock_y.
        px = int(dock_x + self.position_progress * dock_width - CHAR_WIDTH / 2)
        py = int(dock_y - CHAR_HEIGHT - BUBBLE_AREA)
        self._win.geometry(f'{CHAR_WIDTH}x{WIN_HEIGHT}+{px}+{py}')
        self._render()
