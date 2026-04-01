"""Shell environment resolution for Windows."""

import os
import shutil


class ShellEnvironment:
    _cached_env = None

    @classmethod
    def resolve(cls):
        if cls._cached_env is not None:
            return cls._cached_env
        cls._cached_env = dict(os.environ)
        return cls._cached_env

    @classmethod
    def find_binary(cls, name, fallback_paths=None):
        for ext in ('', '.cmd', '.exe', '.bat'):
            found = shutil.which(name + ext)
            if found:
                return found
        for path in (fallback_paths or []):
            if os.path.isfile(path):
                return path
        return None

    @classmethod
    def process_environment(cls, extra_paths=None):
        env = dict(cls.resolve())
        appdata = os.environ.get('APPDATA', '')
        localappdata = os.environ.get('LOCALAPPDATA', '')
        home = os.path.expanduser('~')

        essential = [
            os.path.join(appdata, 'npm'),
            os.path.join(localappdata, 'Programs', 'Claude'),
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

        # Prevent AI CLIs from emitting terminal escape sequences.
        env['TERM'] = 'dumb'
        return env
