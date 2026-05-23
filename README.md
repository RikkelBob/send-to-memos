# send-to-memos

A hotkey-triggered quick-capture tool for [Memos](https://usememos.com). Pop up a small dialog, type a note, optionally attach a screenshot, and save directly to your Memos instance — all without leaving your current window.

## Requirements

```
sudo apt install python3-tk scrot imagemagick libnotify-bin
```

## Setup

1. Copy the example config and fill in your values:

```bash
cp memos-capture.conf.example ~/.config/memos-capture.conf
```

```ini
MEMOS_URL=http://your-memos-instance:5235
MEMOS_TOKEN=your_personal_access_token_here
TAG=#desktop-capture
```

2. Make the script executable:

```bash
chmod +x memos-capture.py
```

3. Bind it to a hotkey in your desktop environment (e.g. `Super+N`):

```
/path/to/memos-capture.py
```

## Usage

- Type your note in the dialog
- Click **Attach Screenshot** to select a screen region with `scrot`
- Press **Ctrl+Enter** or click **Save** to post to Memos
- Press **Esc** to cancel

Notes are saved as private memos and tagged with `#desktop-capture` (configurable).

## Configuration

Config is resolved in this order: hardcoded values at the top of the script → `~/.config/memos-capture.conf` → environment variables (`MEMOS_URL`, `MEMOS_TOKEN`, `TAG`).
