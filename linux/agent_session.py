"""Agent session management for Claude, Codex, and Copilot."""

import os
import json
import subprocess
import threading
from enum import Enum

from shell_environment import ShellEnvironment


class AgentProvider(Enum):
    CLAUDE = 'claude'
    CODEX = 'codex'
    COPILOT = 'copilot'

    @property
    def display_name(self):
        return self.value.capitalize()

    @property
    def install_instructions(self):
        if self == AgentProvider.CLAUDE:
            return (
                "To install Claude Code, run:\n"
                "  curl -fsSL https://claude.ai/install.sh | sh\n\n"
                "Or visit: https://claude.ai/download"
            )
        elif self == AgentProvider.CODEX:
            return "To install Codex, run:\n  npm install -g @openai/codex"
        elif self == AgentProvider.COPILOT:
            return (
                "To install GitHub Copilot CLI, run:\n"
                "  npm install -g @github/copilot-cli\n\n"
                "Or: gh extension install github/gh-copilot"
            )

    def fallback_paths(self):
        home = os.path.expanduser('~')
        paths = [
            os.path.join(home, '.local', 'bin', self.value),
            os.path.join(home, '.npm-global', 'bin', self.value),
            f'/usr/local/bin/{self.value}',
            f'/usr/bin/{self.value}',
        ]
        if self == AgentProvider.CLAUDE:
            paths.insert(0, os.path.join(home, '.claude', 'local', 'bin', 'claude'))
        return paths


class AgentSession:
    def __init__(self, provider: AgentProvider):
        self.provider = provider
        self.process = None
        self.is_running = False
        self.is_busy = False
        self.history = []

        self.on_text = None
        self.on_error = None
        self.on_tool_use = None
        self.on_tool_result = None
        self.on_session_ready = None
        self.on_turn_complete = None
        self.on_process_exit = None

    def start(self):
        path = ShellEnvironment.find_binary(
            self.provider.value,
            self.provider.fallback_paths(),
        )
        if not path:
            msg = (
                f"{self.provider.display_name} CLI not found.\n\n"
                f"{self.provider.install_instructions}"
            )
            if self.on_error:
                self.on_error(msg)
            return
        self._launch(path)

    def _launch(self, binary_path):
        args = [binary_path]
        if self.provider == AgentProvider.CLAUDE:
            args += [
                '-p',
                '--output-format', 'stream-json',
                '--input-format', 'stream-json',
                '--verbose',
                '--dangerously-skip-permissions',
            ]

        try:
            self.process = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=ShellEnvironment.process_environment(),
                cwd=os.path.expanduser('~'),
                text=True,
                bufsize=1,
            )
            self.is_running = True
            threading.Thread(target=self._read_stdout, daemon=True).start()
            threading.Thread(target=self._read_stderr, daemon=True).start()
        except Exception as e:
            msg = (
                f"Failed to launch {self.provider.display_name}.\n\n"
                f"{self.provider.install_instructions}\n\nError: {e}"
            )
            if self.on_error:
                self.on_error(msg)

    def _read_stdout(self):
        try:
            for line in self.process.stdout:
                line = line.rstrip('\n')
                if line:
                    self._parse_line(line)
        except Exception:
            pass
        finally:
            self.is_running = False
            self.is_busy = False
            if self.on_process_exit:
                self.on_process_exit()

    def _read_stderr(self):
        try:
            for line in self.process.stderr:
                line = line.strip()
                if line and self.on_error:
                    self.on_error(line)
        except Exception:
            pass

    def _parse_line(self, line):
        if self.provider == AgentProvider.CLAUDE:
            self._parse_claude(line)
        else:
            if self.on_text:
                self.on_text(line + '\n')

    def _parse_claude(self, line):
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return

        msg_type = data.get('type', '')

        if msg_type == 'system':
            if data.get('subtype') == 'init' and self.on_session_ready:
                self.on_session_ready()

        elif msg_type == 'assistant':
            for block in data.get('message', {}).get('content', []):
                btype = block.get('type', '')
                if btype == 'text' and self.on_text:
                    self.on_text(block.get('text', ''))
                elif btype == 'tool_use' and self.on_tool_use:
                    self.on_tool_use(block.get('name', 'Tool'), block.get('input', {}))

        elif msg_type == 'result':
            self.is_busy = False
            if self.on_turn_complete:
                self.on_turn_complete()

    def send(self, message: str):
        if not self.is_running or not self.process:
            return
        self.is_busy = True
        self.history.append({'role': 'user', 'text': message})

        if self.provider == AgentProvider.CLAUDE:
            payload = {
                'type': 'user',
                'message': {'role': 'user', 'content': message},
            }
            line = json.dumps(payload) + '\n'
        else:
            line = message + '\n'

        try:
            self.process.stdin.write(line)
            self.process.stdin.flush()
        except Exception as e:
            if self.on_error:
                self.on_error(str(e))

    def terminate(self):
        self.is_running = False
        if self.process:
            try:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            except Exception:
                pass
            finally:
                for stream in (self.process.stdin,
                               self.process.stdout,
                               self.process.stderr):
                    try:
                        if stream:
                            stream.close()
                    except Exception:
                        pass
