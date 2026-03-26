#!/usr/bin/env bash
# setup.sh — install lil agents Linux dependencies
set -euo pipefail

echo "lil agents — Linux setup"
echo "========================"
echo ""

install_apt() {
    echo "Detected apt (Debian/Ubuntu/Mint)…"
    sudo apt-get update -q
    sudo apt-get install -y \
        python3 \
        python3-gi \
        python3-gi-cairo \
        gir1.2-gtk-3.0 \
        gir1.2-gdk-3.0 \
        libgirepository1.0-dev \
        libcairo2-dev \
        ffmpeg

    # AppIndicator — try Ubuntu/standard first, then Ayatana
    sudo apt-get install -y gir1.2-appindicator3-0.1 2>/dev/null \
        || sudo apt-get install -y gir1.2-ayatanaappindicator3-0.1 2>/dev/null \
        || echo "  Note: AppIndicator not found — GtkStatusIcon fallback will be used."
}

install_dnf() {
    echo "Detected dnf (Fedora/RHEL)…"
    sudo dnf install -y \
        python3 \
        python3-gobject \
        python3-cairo \
        gtk3 \
        libappindicator-gtk3 \
        ffmpeg
}

install_pacman() {
    echo "Detected pacman (Arch/Manjaro)…"
    sudo pacman -S --noconfirm \
        python \
        python-gobject \
        python-cairo \
        gtk3 \
        libappindicator-gtk3 \
        ffmpeg
}

install_zypper() {
    echo "Detected zypper (openSUSE)…"
    sudo zypper install -y \
        python3 \
        python3-gobject \
        python3-cairo \
        typelib-1_0-Gtk-3_0 \
        libappindicator3-1 \
        ffmpeg
}

if command -v apt-get &>/dev/null; then
    install_apt
elif command -v dnf &>/dev/null; then
    install_dnf
elif command -v pacman &>/dev/null; then
    install_pacman
elif command -v zypper &>/dev/null; then
    install_zypper
else
    echo "Unrecognised package manager."
    echo "Please install the following manually:"
    echo "  python3, python3-gi, python3-gi-cairo, gir1.2-gtk-3.0, ffmpeg"
    echo "  (Optional) gir1.2-appindicator3-0.1 or gir1.2-ayatanaappindicator3-0.1"
    exit 1
fi

echo ""
echo "All done! To run lil agents:"
echo "  python3 lil_agents.py"
echo ""
echo "Tip: a compositor (e.g. picom, kwin, mutter) is needed"
echo "     for transparent character windows."
