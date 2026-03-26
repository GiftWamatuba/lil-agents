"""Animated character windows — flat vector style matching the macOS originals."""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib

import cairo
import math
import random
import time
import os
import shutil
import subprocess
from collections import deque

CHAR_WIDTH  = 56
CHAR_HEIGHT = 98

_WALK_FRAMES = 8
_SPRITE_FPS = 30.0
_SPRITE_CACHE = {}


def _clear_black_bg(surface, threshold=12):
    """Flood-fill from edges to remove the black matte background.
    Only pixels with all channels <= threshold AND connected to the border are cleared.
    This preserves dark character pixels (hair, shoes) that are interior."""
    surface.flush()
    data = surface.get_data()
    stride = surface.get_stride()
    w = surface.get_width()
    h = surface.get_height()

    def is_dark(i):
        return (data[i + 3] > 0
                and data[i]     <= threshold  # B
                and data[i + 1] <= threshold  # G
                and data[i + 2] <= threshold) # R

    q = deque()
    seen = set()
    for x in range(w):
        q.append((x, 0));     q.append((x, h - 1))
    for y in range(h):
        q.append((0, y));     q.append((w - 1, y))

    while q:
        x, y = q.popleft()
        if (x, y) in seen:
            continue
        seen.add((x, y))
        i = y * stride + x * 4
        if not is_dark(i):
            continue
        data[i + 3] = 0
        if x > 0:   q.append((x - 1, y))
        if x < w-1: q.append((x + 1, y))
        if y > 0:   q.append((x, y - 1))
        if y < h-1: q.append((x, y + 1))

    surface.mark_dirty()


def _fit_surface(surface):
    """Return a surface resized to current display dimensions."""
    if surface.get_width() == CHAR_WIDTH and surface.get_height() == CHAR_HEIGHT:
        return surface
    target = cairo.ImageSurface(cairo.FORMAT_ARGB32, CHAR_WIDTH, CHAR_HEIGHT)
    ctx = cairo.Context(target)
    sx = CHAR_WIDTH / max(surface.get_width(), 1)
    sy = CHAR_HEIGHT / max(surface.get_height(), 1)
    ctx.scale(sx, sy)
    ctx.set_source_surface(surface, 0, 0)
    ctx.paint()
    return target


def _sprite_config(name):
    key = name.lower()
    if key == 'jazz':
        return {
            'idle_frame': 0,
            'walk_start': int(4.5 * _SPRITE_FPS),
            'walk_end': int(8.75 * _SPRITE_FPS),
            'y_offset': 1,
            'flip_x_offset': -3,
        }
    return {
        'idle_frame': 0,
        'walk_start': int(3.75 * _SPRITE_FPS),
        'walk_end': int(8.5 * _SPRITE_FPS),
        'y_offset': 3,
        'flip_x_offset': 0,
    }


def _remove_black_bg(png_path, tolerance=18, feather=18):
    """Replace black background pixels with transparency in-place."""
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        return
    img  = Image.open(png_path).convert('RGB')
    data = np.array(img, dtype=np.float32)
    # Distance from pure black
    dist  = np.sqrt((data ** 2).sum(axis=2))
    alpha = np.clip((dist - tolerance) / feather * 255, 0, 255).astype(np.uint8)
    rgba  = np.zeros((*data.shape[:2], 4), dtype=np.uint8)
    rgba[:, :, :3] = data.astype(np.uint8)
    rgba[:, :,  3] = alpha
    Image.fromarray(rgba, 'RGBA').save(png_path)


def _load_sprite_frames(name):
    """Load PNG frames from linux/sprites/<name>/ or extract them at runtime."""
    key = name.lower()
    if key in _SPRITE_CACHE:
        return _SPRITE_CACHE[key]

    sprites_dir = os.path.join(os.path.dirname(__file__), 'sprites', key)
    repo_root   = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    cache_dir   = os.path.join(repo_root, '.cache', 'linux-sprites', key)

    frames_dir = None
    for candidate in (sprites_dir, cache_dir):
        if os.path.isdir(candidate):
            files = sorted(f for f in os.listdir(candidate)
                           if f.startswith('frame-') and f.endswith('.png'))
            if files:
                frames_dir = candidate
                break

    # Extract at runtime with ffmpeg if frames not found
    if frames_dir is None:
        mov_path = os.path.join(repo_root, 'LilAgents', f'walk-{key}-01.mov')
        ffmpeg_bin = shutil.which('ffmpeg')
        if os.path.exists(mov_path) and ffmpeg_bin:
            os.makedirs(cache_dir, exist_ok=True)
            print(f'[lil agents] Extracting {key} sprites (one-time, ~30s)…')
            subprocess.run(
                [
                    ffmpeg_bin, '-v', 'error', '-y',
                    '-i', mov_path,
                    '-vf', f'fps={int(_SPRITE_FPS)},scale={CHAR_WIDTH}:{CHAR_HEIGHT}:flags=lanczos',
                    '-pix_fmt', 'rgb24',
                    os.path.join(cache_dir, 'frame-%04d.png'),
                ],
                check=False,
            )
            # Remove black background from every extracted frame
            extracted = sorted(f for f in os.listdir(cache_dir)
                               if f.startswith('frame-') and f.endswith('.png'))
            print(f'[lil agents] Removing background from {len(extracted)} frames…')
            for fn in extracted:
                _remove_black_bg(os.path.join(cache_dir, fn))
            if extracted:
                frames_dir = cache_dir

    if frames_dir is None:
        _SPRITE_CACHE[key] = []
        return []

    all_files = sorted(f for f in os.listdir(frames_dir)
                       if f.startswith('frame-') and f.endswith('.png'))

    # One-time upgrade: if PNGs have no alpha channel (old cache built without numpy),
    # re-run background removal now that numpy is available.
    if all_files:
        probe = cairo.ImageSurface.create_from_png(
            os.path.join(frames_dir, all_files[0]))
        if probe.get_format() != cairo.FORMAT_ARGB32:
            print(f'[lil agents] Upgrading {key} sprites with alpha (one-time)…')
            for fn in all_files:
                _remove_black_bg(os.path.join(frames_dir, fn))

    surfaces = []
    for filename in all_files:
        try:
            surf = cairo.ImageSurface.create_from_png(
                os.path.join(frames_dir, filename))
            _clear_black_bg(surf)
            fitted = _fit_surface(surf)
            _clear_black_bg(fitted, threshold=26)
            surfaces.append(fitted)
        except Exception:
            pass

    _SPRITE_CACHE[key] = surfaces
    return surfaces

# (body_bob, left_leg_deg, right_leg_deg, left_arm_deg, right_arm_deg)
_WALK = [
    (0.0, -28,  28, -22,  22),
    (1.2, -38,  14, -30,  12),
    (2.4, -20,  20, -16,  16),
    (1.2, -14,  38, -12,  30),
    (0.0,  28, -28,  22, -22),
    (1.2,  14, -38,  12, -30),
    (2.4,  20, -20,  16, -16),
    (1.2,  38, -14,  30, -12),
]

# ── Colour palettes ──────────────────────────────────────────────────────────

BRUCE = dict(
    skin   = (0.95, 0.80, 0.65, 1),
    hair   = (0.17, 0.13, 0.10, 1),
    jacket = (0.43, 0.73, 0.43, 1),
    jacket_shadow = (0.32, 0.58, 0.32, 1),
    pants  = (0.93, 0.93, 0.91, 1),
    shoe   = (0.16, 0.15, 0.17, 1),
    eye    = (0.16, 0.12, 0.08, 1),
)

JAZZ = dict(
    skin   = (0.95, 0.80, 0.65, 1),
    hair   = (0.17, 0.13, 0.10, 1),
    top    = (0.32, 0.52, 0.78, 1),
    scarf  = (0.22, 0.40, 0.68, 1),
    pants  = (0.97, 0.50, 0.10, 1),
    shoe   = (0.16, 0.15, 0.17, 1),
    bag    = (0.22, 0.20, 0.25, 1),
    glass_frame = (0.18, 0.16, 0.20, 1),
    glass_lens  = (0.55, 0.72, 0.90, 0.45),
    eye    = (0.16, 0.12, 0.08, 1),
)


# ── Cairo helpers ────────────────────────────────────────────────────────────

def _set(ctx, color):
    ctx.set_source_rgba(*color)

def _rrect(ctx, x, y, w, h, r):
    """Fill a rounded rectangle."""
    r = min(r, w / 2, h / 2)
    ctx.new_path()
    ctx.move_to(x + r, y)
    ctx.line_to(x + w - r, y)
    ctx.arc(x + w - r, y + r, r, -math.pi/2, 0)
    ctx.line_to(x + w, y + h - r)
    ctx.arc(x + w - r, y + h - r, r, 0, math.pi/2)
    ctx.line_to(x + r, y + h)
    ctx.arc(x + r, y + h - r, r, math.pi/2, math.pi)
    ctx.line_to(x, y + r)
    ctx.arc(x + r, y + r, r, math.pi, 3*math.pi/2)
    ctx.close_path()

def _pill(ctx, cx, y_top, w, h, r=None):
    """Rounded pill centred at cx."""
    if r is None:
        r = w / 2
    _rrect(ctx, cx - w/2, y_top, w, h, r)

def _leg(ctx, cx, y_top, w, h, angle_deg, color_top, color_shoe, shoe_h=9):
    """Draw a leg with a shoe block, pivoting from the top."""
    a = math.radians(angle_deg)
    tx = cx + math.sin(a) * h
    ty = y_top + math.cos(a) * h
    # Leg segment
    ctx.set_line_width(w)
    ctx.set_line_cap(cairo.LineCap.ROUND)
    _set(ctx, color_top)
    ctx.move_to(cx, y_top)
    ctx.line_to(tx, ty)
    ctx.stroke()
    # Shoe
    _set(ctx, color_shoe)
    ctx.arc(tx, ty, w * 0.55, 0, 2*math.pi)
    ctx.fill()
    ctx.rectangle(tx - w * 0.6, ty - 1, w * 1.4, shoe_h)
    ctx.fill()

def _arm(ctx, cx, y_top, length, angle_deg, width, color):
    a = math.radians(angle_deg)
    ex = cx + math.sin(a) * length
    ey = y_top + math.cos(a) * length
    ctx.set_line_width(width)
    ctx.set_line_cap(cairo.LineCap.ROUND)
    _set(ctx, color)
    ctx.move_to(cx, y_top)
    ctx.line_to(ex, ey)
    ctx.stroke()
    # Hand nub
    ctx.arc(ex, ey, width * 0.6, 0, 2*math.pi)
    ctx.fill()


# ── Bruce ────────────────────────────────────────────────────────────────────

def draw_bruce(ctx, frame, direction, _color=None):
    c = BRUCE
    bob, ll, rl, la, ra = _WALK[frame % _WALK_FRAMES]

    ctx.save()
    if direction < 0:
        ctx.translate(CHAR_WIDTH, 0)
        ctx.scale(-1, 1)

    cx   = CHAR_WIDTH / 2
    floor = CHAR_HEIGHT - 6
    leg_h = 26
    body_h = 38
    body_w = 30
    shoulder_y = floor - leg_h - body_h
    head_r = 13.5
    head_cy = shoulder_y - head_r + 1

    # ── legs ──────────────────────────────────────────────────────
    _leg(ctx, cx - 7, floor - leg_h, 9, leg_h, ll, c['pants'], c['shoe'])
    _leg(ctx, cx + 7, floor - leg_h, 9, leg_h, rl, c['pants'], c['shoe'])

    # ── arms (behind body) ───────────────────────────────────────
    _arm(ctx, cx - 13, shoulder_y + 10, 24, la - 168, 8, c['jacket'])
    _arm(ctx, cx + 13, shoulder_y + 10, 24, ra - 10,  8, c['jacket'])

    # ── jacket body ──────────────────────────────────────────────
    _set(ctx, c['jacket'])
    _pill(ctx, cx, shoulder_y, body_w, body_h, 8)
    ctx.fill()

    # Jacket lapel shadow (centre stripe)
    _set(ctx, c['jacket_shadow'])
    _rrect(ctx, cx - 3.5, shoulder_y + 2, 7, body_h - 6, 2)
    ctx.fill()

    # Jacket collar fold (V shape)
    _set(ctx, c['jacket_shadow'])
    ctx.set_line_width(2.5)
    ctx.set_line_cap(cairo.LineCap.ROUND)
    ctx.move_to(cx - 5, shoulder_y + 2)
    ctx.line_to(cx,     shoulder_y + 12)
    ctx.line_to(cx + 5, shoulder_y + 2)
    ctx.stroke()

    # ── head ─────────────────────────────────────────────────────
    _set(ctx, c['skin'])
    ctx.arc(cx, head_cy, head_r, 0, 2*math.pi)
    ctx.fill()

    # Hair (flat top)
    _set(ctx, c['hair'])
    ctx.arc(cx, head_cy, head_r, math.pi, 0)
    ctx.fill()
    ctx.rectangle(cx - head_r, head_cy - head_r, head_r * 2, head_r * 0.55)
    ctx.fill()

    # Eyes
    _set(ctx, c['eye'])
    for ex in (cx - 4.5, cx + 4.5):
        ctx.arc(ex, head_cy + 2, 2.2, 0, 2*math.pi)
        ctx.fill()

    # Smile
    ctx.set_line_width(1.8)
    ctx.set_line_cap(cairo.LineCap.ROUND)
    ctx.arc(cx, head_cy + 5, 5, math.radians(15), math.radians(165))
    ctx.stroke()

    ctx.restore()


# ── Jazz ─────────────────────────────────────────────────────────────────────

def draw_jazz(ctx, frame, direction, _color=None):
    c = JAZZ
    bob, ll, rl, la, ra = _WALK[frame % _WALK_FRAMES]

    ctx.save()
    if direction < 0:
        ctx.translate(CHAR_WIDTH, 0)
        ctx.scale(-1, 1)

    cx    = CHAR_WIDTH / 2
    floor = CHAR_HEIGHT - 6
    leg_h = 22
    body_h = 32
    body_w = 28
    shoulder_y = floor - leg_h - body_h
    head_r = 13
    head_cy = shoulder_y - head_r + 2

    # ── legs ──────────────────────────────────────────────────────
    _leg(ctx, cx - 7, floor - leg_h, 9, leg_h, ll, c['pants'], c['shoe'])
    _leg(ctx, cx + 7, floor - leg_h, 9, leg_h, rl, c['pants'], c['shoe'])

    # ── bag (right side) ─────────────────────────────────────────
    bag_x = cx + body_w / 2 - 2
    bag_y = shoulder_y + body_h * 0.35
    _set(ctx, c['bag'])
    _rrect(ctx, bag_x, bag_y, 12, 16, 3)
    ctx.fill()
    # bag strap
    ctx.set_line_width(2)
    ctx.set_source_rgba(*c['bag'])
    ctx.move_to(cx + 10, shoulder_y + 6)
    ctx.line_to(bag_x + 4, bag_y)
    ctx.stroke()

    # ── arms ──────────────────────────────────────────────────────
    _arm(ctx, cx - 13, shoulder_y + 8, 22, la - 168, 8, c['top'])
    _arm(ctx, cx + 13, shoulder_y + 8, 22, ra - 10,  8, c['top'])

    # ── body (top/jacket) ────────────────────────────────────────
    _set(ctx, c['top'])
    _pill(ctx, cx, shoulder_y, body_w, body_h, 9)
    ctx.fill()

    # Scarf
    _set(ctx, c['scarf'])
    _rrect(ctx, cx - body_w/2 + 3, shoulder_y - 1, body_w - 6, 12, 5)
    ctx.fill()

    # ── head ─────────────────────────────────────────────────────
    _set(ctx, c['skin'])
    ctx.arc(cx, head_cy, head_r, 0, 2*math.pi)
    ctx.fill()

    # Hair
    _set(ctx, c['hair'])
    ctx.arc(cx, head_cy, head_r, math.pi, 0)
    ctx.fill()
    ctx.rectangle(cx - head_r, head_cy - head_r, head_r * 2, head_r * 0.5)
    ctx.fill()

    # Glasses frames
    g_y  = head_cy + 1
    g_r  = 5.5
    g_cx = [cx - 6.5, cx + 6.5]
    for gx in g_cx:
        _set(ctx, c['glass_lens'])
        ctx.arc(gx, g_y, g_r, 0, 2*math.pi)
        ctx.fill()
        _set(ctx, c['glass_frame'])
        ctx.set_line_width(1.8)
        ctx.arc(gx, g_y, g_r, 0, 2*math.pi)
        ctx.stroke()
    # Bridge
    _set(ctx, c['glass_frame'])
    ctx.set_line_width(1.6)
    ctx.move_to(g_cx[0] + g_r, g_y)
    ctx.line_to(g_cx[1] - g_r, g_y)
    ctx.stroke()
    # Side arms
    ctx.move_to(g_cx[0] - g_r, g_y)
    ctx.line_to(g_cx[0] - g_r - 5, g_y - 1)
    ctx.stroke()
    ctx.move_to(g_cx[1] + g_r, g_y)
    ctx.line_to(g_cx[1] + g_r + 5, g_y - 1)
    ctx.stroke()

    # Eyes behind glasses
    _set(ctx, c['eye'])
    for gx in g_cx:
        ctx.arc(gx, g_y + 0.5, 1.8, 0, 2*math.pi)
        ctx.fill()

    ctx.restore()


# ── Bubble ───────────────────────────────────────────────────────────────────

class _Bubble:
    def __init__(self, text, expiry):
        self.text  = text
        self.expiry = expiry


# ── CharacterWindow ──────────────────────────────────────────────────────────

class CharacterWindow:
    THINKING_PHRASES = [
        "hmm...", "thinking...", "on it!", "let me see...",
        "processing...", "almost...", "working...", "hold on...",
    ]

    def __init__(self, name, draw_func, color=None,
                 x_start_frac=0.3, walk_speed=75, on_clicked=None):
        self.name          = name
        self._draw_func    = draw_func
        self.position_progress = x_start_frac
        self.direction     = 1
        self._walk_speed   = walk_speed + random.uniform(-8, 8)
        self._bubble       = None
        self.on_clicked    = on_clicked

        self._frame        = 0
        self._frame_timer  = 0.0
        self._sprite_cfg = _sprite_config(name)
        self._sprite_frames = _load_sprite_frames(name)
        self._sprite_index = self._sprite_cfg['idle_frame']
        self._sprite_timer = 0.0
        self._pause_until  = time.time() + random.uniform(0.5, 3.0)
        self._target       = random.uniform(0.4, 0.85)

        self._window = None
        self._area   = None
        self._build()

    def _build(self):
        win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        win.set_app_paintable(True)
        win.set_decorated(False)
        win.set_skip_taskbar_hint(True)
        win.set_skip_pager_hint(True)
        win.set_keep_above(True)
        win.set_accept_focus(False)
        win.set_type_hint(Gdk.WindowTypeHint.UTILITY)

        screen = win.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            win.set_visual(visual)

        # Force transparent window background via CSS so GTK doesn't paint black.
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b'window { background-color: transparent; }')
        win.get_style_context().add_provider(
            css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        area = Gtk.DrawingArea()
        area.set_size_request(CHAR_WIDTH, CHAR_HEIGHT)
        area.connect('draw', self._on_draw)
        area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        area.connect('button-press-event', self._on_click)

        win.add(area)
        win.set_size_request(CHAR_WIDTH, CHAR_HEIGHT)
        win.show_all()

        self._window = win
        self._area   = area

    # ── Drawing ─────────────────────────────────────────────────────────────

    def _on_draw(self, widget, ctx):
        ctx.set_operator(cairo.Operator.CLEAR)
        ctx.paint()
        ctx.set_operator(cairo.Operator.OVER)
        if self._sprite_frames:
            frame = self._sprite_frames[self._sprite_index % len(self._sprite_frames)]
            if self.direction < 0:
                ctx.save()
                ctx.translate(CHAR_WIDTH + self._sprite_cfg['flip_x_offset'], 0)
                ctx.scale(-1, 1)
                ctx.set_source_surface(frame, 0, 0)
                ctx.paint()
                ctx.restore()
            else:
                ctx.set_source_surface(frame, 0, 0)
                ctx.paint()
        else:
            # Keep transparent if sprite extraction failed; avoid mismatched fallback art.
            pass
        if self._bubble and time.time() < self._bubble.expiry:
            self._draw_bubble(ctx, self._bubble.text)

    def _draw_bubble(self, ctx, text):
        ctx.select_font_face('Sans', cairo.FontSlant.NORMAL, cairo.FontWeight.BOLD)
        ctx.set_font_size(11)
        te  = ctx.text_extents(text)
        pad = 6
        bw  = te.width + pad * 2
        bh  = te.height + pad * 2
        bx  = CHAR_WIDTH / 2 - bw / 2
        by  = 2

        ctx.set_source_rgba(0, 0, 0, 0.10)
        _rrect(ctx, bx + 1, by + 2, bw, bh, 14)
        ctx.fill()

        ctx.set_source_rgba(1.0, 0.95, 0.90, 0.95)
        _rrect(ctx, bx, by, bw, bh, 14)
        ctx.fill_preserve()
        ctx.set_source_rgba(0.95, 0.55, 0.65, 0.60)
        ctx.set_line_width(1.5)
        ctx.stroke()

        ctx.set_source_rgba(0.55, 0.50, 0.52, 1.0)
        ctx.move_to(bx + pad - te.x_bearing, by + pad - te.y_bearing)
        ctx.show_text(text)

        tx = CHAR_WIDTH / 2
        ty = by + bh
        ctx.set_source_rgba(1.0, 0.95, 0.90, 0.95)
        ctx.move_to(tx - 4, ty)
        ctx.line_to(tx, ty + 5)
        ctx.line_to(tx + 4, ty)
        ctx.close_path()
        ctx.fill()

    # ── Events ──────────────────────────────────────────────────────────────

    def _on_click(self, widget, event):
        if self.on_clicked:
            self.on_clicked(self)

    # ── Public API ──────────────────────────────────────────────────────────

    def show_bubble(self, text, duration=4.0):
        self._bubble = _Bubble(text, time.time() + duration)
        if self._area:
            self._area.queue_draw()

    def set_busy(self, busy):
        if busy:
            self.show_bubble(random.choice(self.THINKING_PHRASES), duration=9999)
        else:
            self._bubble = None
            if self._area:
                self._area.queue_draw()

    def update(self, dock_x, dock_width, dock_y, dt):
        now = time.time()
        if now >= self._pause_until:
            speed_frac = self._walk_speed / max(dock_width, 1)
            self.position_progress += self.direction * speed_frac * dt

            if self.direction > 0 and self.position_progress >= self._target:
                self.direction = -1
                self.position_progress = self._target
                self._pause_until = now + random.uniform(2.0, 7.0)
                self._target = random.uniform(0.05, max(0.06, self.position_progress - 0.1))
            elif self.direction < 0 and self.position_progress <= self._target:
                self.direction = 1
                self.position_progress = self._target
                self._pause_until = now + random.uniform(2.0, 7.0)
                self._target = random.uniform(min(0.94, self.position_progress + 0.1), 0.94)

            self.position_progress = max(0.0, min(1.0, self.position_progress))

            self._frame_timer += dt
            if self._frame_timer >= 0.09:
                self._frame = (self._frame + 1) % _WALK_FRAMES
                self._frame_timer = 0.0
            self._sprite_timer += dt
            if self._sprite_frames and self._sprite_timer >= (1.0 / _SPRITE_FPS):
                start = max(0, min(self._sprite_cfg['walk_start'], len(self._sprite_frames) - 1))
                end = max(start, min(self._sprite_cfg['walk_end'], len(self._sprite_frames) - 1))
                if self._sprite_index < start or self._sprite_index > end:
                    self._sprite_index = start
                else:
                    self._sprite_index += 1
                    if self._sprite_index > end:
                        self._sprite_index = start
                self._sprite_timer = 0.0
        elif self._sprite_frames:
            self._sprite_index = min(self._sprite_cfg['idle_frame'], len(self._sprite_frames) - 1)

        px = int(dock_x + self.position_progress * dock_width - CHAR_WIDTH / 2)
        py = int(dock_y - CHAR_HEIGHT + self._sprite_cfg['y_offset'])
        self._window.move(px, py)
        if self._area:
            self._area.queue_draw()

    @property
    def window(self):
        return self._window
