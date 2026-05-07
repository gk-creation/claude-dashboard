# Claude Files Dashboard

A local file browser for your Claude projects — runs entirely on your Mac, no cloud, no account needed.
<img width="1458" height="898" alt="Scherm­afbeelding 2026-05-07 om 07 47 12" src="https://github.com/user-attachments/assets/7eca10a0-db57-4377-96fb-3892afaaa7da" />

Integrated bug, fixes en idea's notes -> marked and saved locally on the project folder ma
<img width="299" height="856" alt="Scherm­afbeelding 2026-05-07 om 07 51 22" src="https://github.com/user-attachments/assets/0040f657-6420-48dd-a26d-8d921feff0cf" />

Easy access to your locally hosted SKILL.md -> all skills are structered + easy to adjust and make annotions to it (saved locally)
<img width="354" height="631" alt="Scherm­afbeelding 2026-05-07 om 07 50 16" src="https://github.com/user-attachments/assets/173a5213-e8e5-4691-98a1-213df16a8f42" />




## What it does

- **📁 Projects** — browse all folders under `~/claude/` with Finder, VS Code and Claude (Ghostty) shortcuts
- **⚙️ Config** — browse `~/.claude/` (Claude Code settings, MCP configs, etc.)
- **⭐ Favourites** — bookmark files and folders you open often
- **🕐 Recents** — everything you opened, grouped by day
- **📋 All Notes** — overview of all notes across every project
- **Notes panel** — add 💡 Idea, 🐛 Bug or 📌 Todo notes to any folder
- **Sort bar** — sort projects A-Z, by recent activity, or collapse all folders at once
- **Spotlight** (⌘K) — fuzzy search across projects, files and notes
- **Dark / Light mode** toggle

All data (favourites, notes, recents) is stored locally in `~/claude/` — nothing leaves your machine.

## Requirements

| Requirement | Notes |
|-------------|-------|
| macOS | Tested on macOS 14+ |
| Python 3.9+ | Ships with macOS, or install via `brew install python` |
| `~/claude/` folder | Your Claude projects live here |
| [Claude Code](https://claude.ai/code) (optional) | For the "Claude" open button (uses Ghostty terminal) |
| [Ghostty](https://ghostty.org) (optional) | Terminal used to open Claude Code sessions |
| [VS Code](https://code.visualstudio.com) (optional) | For the "VS Code" open button |

## Setup

### 1. Create your projects folder

```bash
mkdir -p ~/claude
```

Put your Claude project folders inside `~/claude/`. Each project can have its own `CLAUDE.md` with context for Claude Code.

### 2. Download the dashboard

```bash
# Clone this repo into ~/claude/claude-dashboard
git clone https://github.com/gk-creation/claude-dashboard.git ~/claude/claude-dashboard
```

Or just download `dashboard.py` and drop it anywhere — it is a single file.

### 3. Run it

```bash
python3 ~/claude/claude-dashboard/dashboard.py
```

The dashboard opens automatically at **http://localhost:3333**.

### 4. (Optional) Add a shell alias

```bash
# Add to ~/.zshrc or ~/.bashrc
alias dashboard="python3 ~/claude/claude-dashboard/dashboard.py"
```

Then just type `dashboard` to launch.

## Folder structure

```
~/claude/                          ← projects root (scanned by dashboard)
│
├── my-project/
│   ├── CLAUDE.md                  ← Claude Code context file
│   └── ...
│
├── another-project/
│   └── ...
│
└── claude-dashboard/
    └── dashboard.py               ← this file
```

```
~/.claude/                         ← Claude Code config (also browseable)
├── settings.json
├── .dashboard_favorites.json      ← your starred items (auto-created)
├── .dashboard_notes.json          ← your notes (auto-created)
└── .dashboard_recents.json        ← recent opens (auto-created)
```

> Data files are stored in `~/claude/` (not inside this repo), so they are never accidentally committed.

## Customising

Open `dashboard.py` and edit the constants at the top:

```python
PORT = 3333                        # change the port if needed

ROOTS = {
    'projects': HOME / 'claude',   # your projects root
    'config':   HOME / '.claude',  # Claude Code config folder
}
```

## Keyboard shortcuts

| Shortcut | Action |
|----------|--------|
| `⌘K` | Open Spotlight search |
| `Escape` | Close Spotlight / Notes panel |

## Notes

- The dashboard only reads your filesystem — it never writes files except for the three data files listed above.
- Stopping the server (`Ctrl+C`) is instant and safe.
- Runs on port `3333` by default; change `PORT` at the top of `dashboard.py` if that conflicts.

## License

MIT — free to use, modify and share.
