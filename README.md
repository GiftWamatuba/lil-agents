# lil agents

![lil agents](hero-thumbnail.png)

Tiny AI companions that live on your macOS dock.

**Bruce** and **Jazz** walk back and forth above your dock. Click one to open a Claude AI terminal. They walk, they think, they vibe.

## features

- Animated characters rendered from transparent HEVC video
- Click a character to chat with Claude AI in a themed popover terminal
- Four visual themes: Peach, Midnight, Cloud, Moss
- Thinking bubbles with playful phrases while Claude works
- Sound effects on completion
- First-run onboarding with a friendly welcome
- Auto-updates via Sparkle

## requirements

- macOS Sonoma (14.0+)
- [Claude Code CLI](https://claude.ai/download)

## building

Open `lil-agents.xcodeproj` in Xcode and hit run.

## privacy

lil agents runs entirely on your Mac and sends no personal data anywhere.

- **Your data stays local.** The app plays bundled animations and calculates your dock size to position the characters. No project data, file paths, or personal information is collected or transmitted.
- **Claude AI.** Conversations are handled entirely by the Claude Code CLI process running locally. lil agents does not intercept, store, or transmit your chat content. Any data sent to Anthropic is governed by their terms and privacy policy.
- **No accounts.** No login, no user database, no analytics in the app.
- **Updates.** lil agents uses Sparkle to check for updates, which sends your app version and macOS version. Nothing else.

## license

MIT License. See [LICENSE](LICENSE) for details.
