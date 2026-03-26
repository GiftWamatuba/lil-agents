"""Shell environment resolution for Linux."""

import os
import subprocess
import shutil


class ShellEnvironment:
    _cached_env = None

    @classmethod
    def resolve(cls):
        """Capture the user's login shell environment, cached after first call."""
        if cls._cached_env is not None:
            return cls._cached_env

        shell = os.environ.get('SHELL', '/bin/bash')
        try:
            result = subprocess.run(
                [shell, '-l', '-i', '-c',
                 "echo '---ENV_START---' && env && echo '---ENV_END---'"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = result.stdout
            start = output.find('---ENV_START---\n')
            end = output.find('\n---ENV_END---')
            if start != -1 and end != -1:
                env_block = output[start + len('---ENV_START---\n'):end]
                env = {}
                for line in env_block.splitlines():
                    if '=' in line:
                        key, _, value = line.partition('=')
                        env[key] = value
                cls._cached_env = env
                return env
        except Exception:
            pass

        cls._cached_env = dict(os.environ)
        return cls._cached_env

    @classmethod
    def find_binary(cls, name, fallback_paths=None):
        """Find a binary using the shell PATH then fallback locations."""
        env = cls.resolve()

        # Search shell PATH
        for directory in env.get('PATH', '').split(':'):
            candidate = os.path.join(directory, name)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate

        # Try system which
        found = shutil.which(name)
        if found:
            return found

        # Explicit fallbacks
        for path in (fallback_paths or []):
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path

        return None

    @classmethod
    def process_environment(cls, extra_paths=None):
        """Build a process environment with essential PATH entries prepended."""
        env = dict(cls.resolve())
        home = os.path.expanduser('~')

        essential = [
            os.path.join(home, '.local', 'bin'),
            os.path.join(home, '.local', 'share', 'claude', 'versions'),
            os.path.join(home, '.npm-global', 'bin'),
            '/usr/local/bin',
            '/usr/bin',
            '/bin',
        ] + (extra_paths or [])

        current = env.get('PATH', '/usr/bin:/bin')
        missing = [p for p in essential if p not in current]
        if missing:
            env['PATH'] = ':'.join(missing + [current])

        env['TERM'] = 'dumb'
        return env
