#!/usr/bin/env python3
"""
extract_sprites.py
------------------
Extracts sprite frames from the macOS HEVC .mov files and removes the
background to create transparent PNGs for the Linux app.

Run once after installing ffmpeg and Pillow:
  sudo apt-get install -y ffmpeg
  pip3 install Pillow numpy
  python3 extract_sprites.py
"""

import os
import shutil
import subprocess
import sys

# ── Dependency check ─────────────────────────────────────────────────────────

try:
    from PIL import Image
    import numpy as np
except ImportError:
    print("Installing Pillow and numpy...")
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'Pillow', 'numpy'])
    from PIL import Image
    import numpy as np

# ── Config ───────────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT   = os.path.dirname(SCRIPT_DIR)
SPRITES_DIR = os.path.join(SCRIPT_DIR, 'sprites')

CHAR_WIDTH  = 112
CHAR_HEIGHT = 200
FPS         = 30

CHARACTERS = {
    'bruce': 'walk-bruce-01.mov',
    'jazz':  'walk-jazz-01.mov',
}


# ── Frame extraction ─────────────────────────────────────────────────────────

def extract_raw_frames(mov_path, raw_dir):
    os.makedirs(raw_dir, exist_ok=True)
    result = subprocess.run(
        [
            'ffmpeg', '-v', 'error', '-y',
            '-i', mov_path,
            '-vf', f'fps={FPS},scale={CHAR_WIDTH}:{CHAR_HEIGHT}:flags=lanczos',
            '-pix_fmt', 'rgb24',
            os.path.join(raw_dir, 'raw-%04d.png'),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  ffmpeg error:\n{result.stderr}")
        return False
    return True


# ── Background removal ───────────────────────────────────────────────────────

def detect_background(img_path):
    """Sample edge pixels to find the background colour."""
    img = Image.open(img_path).convert('RGB')
    arr = np.array(img, dtype=np.float32)
    h, w = arr.shape[:2]

    # Sample a thin border all around the frame
    border = np.concatenate([
        arr[0,   :].reshape(-1, 3),
        arr[h-1, :].reshape(-1, 3),
        arr[:,   0].reshape(-1, 3),
        arr[:, w-1].reshape(-1, 3),
    ])
    bg = np.median(border, axis=0)
    print(f"  Background colour detected: "
          f"R={bg[0]:.0f}  G={bg[1]:.0f}  B={bg[2]:.0f}")
    return bg


def remove_background(img_path, bg_color, tolerance=20, feather=20):
    """Remove background colour and return an RGBA Image."""
    img  = Image.open(img_path).convert('RGB')
    data = np.array(img, dtype=np.float32)

    # Euclidean distance to background in RGB space
    diff  = data - bg_color
    dist  = np.sqrt((diff ** 2).sum(axis=2))

    # Soft threshold: 0 → fully transparent, feather range → gradient
    alpha = np.clip((dist - tolerance) / feather * 255, 0, 255).astype(np.uint8)

    rgba = np.zeros((*data.shape[:2], 4), dtype=np.uint8)
    rgba[:, :, :3] = data.astype(np.uint8)
    rgba[:, :,  3] = alpha

    return Image.fromarray(rgba, 'RGBA')


# ── Per-character pipeline ───────────────────────────────────────────────────

def process(name, mov_filename):
    mov_path = os.path.join(REPO_ROOT, 'LilAgents', mov_filename)
    if not os.path.exists(mov_path):
        print(f"  Skipping — not found: {mov_path}")
        return

    out_dir = os.path.join(SPRITES_DIR, name)
    raw_dir = os.path.join(out_dir, '_raw')
    os.makedirs(out_dir, exist_ok=True)

    print(f"  Extracting frames from {mov_filename} …")
    if not extract_raw_frames(mov_path, raw_dir):
        return

    raw_files = sorted(f for f in os.listdir(raw_dir) if f.endswith('.png'))
    if not raw_files:
        print("  No frames extracted.")
        return
    print(f"  {len(raw_files)} frames extracted.")

    bg = detect_background(os.path.join(raw_dir, raw_files[0]))

    print(f"  Removing background and saving transparent PNGs …")
    for i, filename in enumerate(raw_files, start=1):
        out_path = os.path.join(out_dir, f'frame-{i:04d}.png')
        img = remove_background(os.path.join(raw_dir, filename), bg)
        img.save(out_path, compress_level=1)
        if i % 30 == 0:
            print(f"    {i}/{len(raw_files)}")

    shutil.rmtree(raw_dir)
    print(f"  Done → linux/sprites/{name}/  ({len(raw_files)} frames)")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    if not shutil.which('ffmpeg'):
        print("ffmpeg not found. Install it with:")
        print("  sudo apt-get install -y ffmpeg")
        sys.exit(1)

    for name, mov in CHARACTERS.items():
        existing = os.path.join(SPRITES_DIR, name)
        if os.path.isdir(existing):
            count = len([f for f in os.listdir(existing) if f.endswith('.png')])
            if count > 0:
                ans = input(f"\n{name}: {count} frames already exist. Re-extract? [y/N] ")
                if ans.strip().lower() != 'y':
                    print(f"  Skipping {name}.")
                    continue
            shutil.rmtree(existing)

        print(f"\n── {name.upper()} ──────────────────────────────────────")
        process(name, mov)

    print("\nAll done! Run the app:")
    print("  python3 lil_agents.py")


if __name__ == '__main__':
    main()
