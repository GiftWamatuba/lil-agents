"""Shell environment resolution for Windows."""

import os
import shutil


def _to_hex(rgba):
    return '#{:02x}{:02x}{:02x}'.format(
        int(rgba[0] * 255), int(rgba[1] * 255), int(rgba[2] * 255))


class ShellEnvironment:
    _cached_env = None

    @classmethod
    def resolve(cls):
        """Return the current process environment (cached)."""
        if cls._cached_env is not None:
            return cls._cached_env
        cls._cached_env = dict(os.environ)
        return cls._cached_env

    @classmethod
    def find_binary(cls, name, fallback_paths=None):
        """Find a CLI binary by name, checking PATH and common Windows locations."""
        # Check for the plain name and common Windows extensions.
        for ext in ('', '.cmd', '.exe', '.bat'):
            found = shutil.which(name + ext)
            if found:
                return found

        # Explicit fallbacks supplied by the caller.
        for path in (fallback_paths or []):
            if os.path.isfile(path):
                return path

        return None

    @classmethod
    def process_environment(cls, extra_paths=None):
        """Build a process environment with essential PATH entries prepended."""
        env = dict(cls.resolve())
        appdata = os.environ.get('APPDATA', '')
        localappdata = os.environ.get('LOCALAPPDATA', '')
        home = os.path.expanduser('~')

        essential = [
            os.path.join(appdata, 'npm'),                          # npm global bins
            os.path.join(localappdata, 'Programs', 'Claude'),      # possible future location
            os.path.join(localappdata, 'AnthropicClaude'),
            os.path.join(home, '.claude', 'local', 'bin'),
            r'C:\Program Files\nodejs',
            r'C:\Program Files (x86)\nodejs',
        ] + (extra_paths or [])

        current = env.get('PATH', '')
        sep = os.pathsep
        missing = [p for p in essential if p and p not in current]
        if missing:
            env['PATH'] = sep.join(missing + [current])

        return env
