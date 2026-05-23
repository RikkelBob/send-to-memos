#!/usr/bin/env python3
"""
Memos Quick Capture — hotkey-triggered note + screenshot capture.
Requires: python3-tk, scrot
Install:  sudo apt install python3-tk scrot
"""

import tkinter as tk
import subprocess
import urllib.request
import urllib.error
import json
import sys
import os
import tempfile
import base64
from datetime import datetime

# ── Configuration ─────────────────────────────────────────────────────────────
# Option 1: fill in directly here.
MEMOS_URL   = ""                # e.g. "http://192.168.1.100:5235"
MEMOS_TOKEN = ""                # your Memos personal access token
TAG         = "#desktop-capture"

# Option 2: leave blank and use ~/.config/memos-capture.conf (see .example file)
# or set MEMOS_URL / MEMOS_TOKEN environment variables.
# ──────────────────────────────────────────────────────────────────────────────

def _load_config():
    conf_path = os.path.expanduser("~/.config/memos-capture.conf")
    config = {}
    if os.path.exists(conf_path):
        with open(conf_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    config[key.strip()] = value.strip()
    return config

def _resolve(hardcoded, key, config, default=None):
    val = hardcoded or config.get(key) or os.environ.get(key) or default
    if not val:
        sys.exit(f"Error: {key} not configured. Set it at the top of this file or in ~/.config/memos-capture.conf")
    return val

_config     = _load_config()
MEMOS_URL   = _resolve(MEMOS_URL,   "MEMOS_URL",   _config)
MEMOS_TOKEN = _resolve(MEMOS_TOKEN, "MEMOS_TOKEN", _config)
TAG         = _resolve(TAG,         "TAG",         _config, "#desktop-capture")

COLORS = {
    "bg":      "#0f1117",
    "surface": "#181c26",
    "border":  "#272d3d",
    "accent":  "#f5c542",
    "text":    "#e8eaf0",
    "muted":   "#6b7385",
    "error":   "#f87171",
}

# Temp file path passed between two window instances
SHOT_ENV_VAR = "_MEMOS_SCREENSHOT"


def notify(title, message, icon="dialog-information"):
    subprocess.run(["notify-send", "-i", icon, title, message], check=False)


def make_thumbnail(screenshot_path):
    """Return a tk.PhotoImage thumbnail, or None on failure."""
    try:
        thumb_tmp = tempfile.NamedTemporaryFile(suffix=".ppm", delete=False, prefix="memos_thumb_")
        thumb_tmp.close()
        subprocess.run(
            ["convert", screenshot_path, "-thumbnail", "420x120>", thumb_tmp.name],
            check=True, capture_output=True
        )
        img = tk.PhotoImage(file=thumb_tmp.name)
        os.unlink(thumb_tmp.name)
        return img
    except Exception:
        return None


def upload_resource(image_path):
    # Canary API: flat JSON with base64-encoded content
    with open(image_path, "rb") as f:
        image_data = f.read()

    filename = os.path.basename(image_path)
    payload = json.dumps({
        "filename": filename,
        "type": "image/png",
        "content": base64.b64encode(image_data).decode("utf-8"),
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{MEMOS_URL.rstrip('/')}/api/v1/attachments",
        data=payload,
        headers={
            "Authorization": f"Bearer {MEMOS_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        if "code" in data and data["code"] != 0:
            raise Exception(f"API error: {data.get('message', data)}")
        # Returns name like "attachments/abc123"; serve via /file/attachments/...
        return data.get("name") or filename


def save_memo(text, screenshot_path, root):
    content = text.strip()

    attachments = []
    extra_tags = ""
    if screenshot_path and os.path.exists(screenshot_path):
        try:
            resource_name = upload_resource(screenshot_path)
            attachments = [{"name": resource_name}]
            extra_tags = " #screenshot"
        except Exception as e:
            notify("Memos", f"Image upload failed: {e}\nSaving text only.", icon="dialog-warning")

    content += f"\n\n{TAG}{extra_tags}"

    payload = json.dumps({
        "content": content,
        "visibility": "PRIVATE",
        "attachments": attachments,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{MEMOS_URL.rstrip('/')}/api/v1/memos",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {MEMOS_TOKEN}",
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status in (200, 201):
                if screenshot_path:
                    try:
                        os.unlink(screenshot_path)
                    except Exception:
                        pass
                root.destroy()
                notify("Saved to Memos ✓", text[:80] + ("…" if len(text) > 80 else "") or "(screenshot)")
            else:
                notify("Memos: unexpected response", f"HTTP {resp.status}", icon="dialog-error")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            msg = json.loads(body).get("message", body)
        except Exception:
            msg = body
        notify("Memos: save failed", f"HTTP {e.code}: {msg}", icon="dialog-error")
    except urllib.error.URLError as e:
        notify("Memos: connection failed", str(e.reason), icon="dialog-error")


def on_screenshot_click(root, saved_text_var, thumb_label, attach_btn, clear_btn, old_screenshot=None):
    """Destroy window, take screenshot, reopen window with result."""
    saved_text = saved_text_var.get("1.0", "end-1c")

    # Write current text to a temp file so we can restore it
    text_tmp = tempfile.NamedTemporaryFile(suffix=".txt", delete=False, prefix="memos_text_")
    text_tmp.write(saved_text.encode("utf-8"))
    text_tmp.close()

    # Take screenshot with a fresh temp path
    shot_tmp = tempfile.mktemp(suffix=".png", prefix="memos_cap_")

    # Delete old screenshot if retaking
    if old_screenshot and os.path.exists(old_screenshot):
        try:
            os.unlink(old_screenshot)
        except Exception:
            pass

    # Fully destroy Tk so X11 input is free
    root.destroy()

    result = subprocess.run(["scrot", "-s", shot_tmp])

    # Relaunch this script with env vars carrying state
    env = os.environ.copy()
    env[SHOT_ENV_VAR] = shot_tmp if (result.returncode == 0 and os.path.exists(shot_tmp) and os.path.getsize(shot_tmp) > 0) else ""
    env["_MEMOS_TEXT"] = text_tmp.name

    subprocess.Popen([sys.executable, __file__], env=env)


def build_window(screenshot_path=None, initial_text=""):
    root = tk.Tk()
    root.title("Save to Memos")
    root.resizable(False, False)
    root.configure(bg=COLORS["bg"])
    root.attributes("-topmost", True)

    w, h = 480, 420 if screenshot_path else 300
    x = (root.winfo_screenwidth() // 2) - (w // 2)
    y = (root.winfo_screenheight() // 2) - (h // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")

    # ── Header ──
    header = tk.Frame(root, bg=COLORS["bg"])
    header.pack(fill="x", padx=20, pady=(18, 0))
    tk.Label(header, text="📝", bg=COLORS["accent"], fg=COLORS["bg"],
             font=("sans-serif", 12, "bold"), padx=6, pady=2).pack(side="left")
    tk.Label(header, text="  Save to Memos", bg=COLORS["bg"],
             fg=COLORS["text"], font=("sans-serif", 13, "bold")).pack(side="left")

    # ── Text area ──
    text_frame = tk.Frame(root, bg=COLORS["border"], padx=1, pady=1)
    text_frame.pack(fill="both", expand=True, padx=20, pady=12)
    text_area = tk.Text(
        text_frame, wrap="word", height=4 if screenshot_path else 6,
        bg=COLORS["surface"], fg=COLORS["text"],
        insertbackground=COLORS["text"],
        relief="flat", font=("sans-serif", 11),
        padx=10, pady=8,
        selectbackground=COLORS["accent"], selectforeground=COLORS["bg"]
    )
    text_area.pack(fill="both", expand=True)
    if initial_text:
        text_area.insert("1.0", initial_text)
    text_area.focus_set()

    # ── Thumbnail ──
    thumb_label = tk.Label(root, bg=COLORS["bg"], text="", fg=COLORS["muted"],
                           font=("sans-serif", 9))
    thumb_label._img = None

    if screenshot_path and os.path.exists(screenshot_path):
        img = make_thumbnail(screenshot_path)
        if img:
            thumb_label.config(image=img)
            thumb_label._img = img
        else:
            thumb_label.config(text=f"📷 Screenshot attached")
        thumb_label.pack(pady=(0, 4))

    # ── Buttons ──
    btn_frame = tk.Frame(root, bg=COLORS["bg"])
    btn_frame.pack(fill="x", padx=20, pady=(0, 4))

    attach_btn = tk.Button(
        btn_frame,
        text="📷 Retake Screenshot" if screenshot_path else "📷 Attach Screenshot",
        bg=COLORS["surface"], fg=COLORS["text"],
        activebackground=COLORS["border"], activeforeground=COLORS["accent"],
        relief="flat", font=("sans-serif", 10),
        padx=10, pady=6, cursor="hand2",
    )
    attach_btn.config(command=lambda: on_screenshot_click(root, text_area, thumb_label, attach_btn, None, old_screenshot=screenshot_path))
    attach_btn.pack(side="left")

    save_btn = tk.Button(
        btn_frame, text="Save  ↵",
        bg=COLORS["accent"], fg=COLORS["bg"],
        activebackground="#e6b800", activeforeground=COLORS["bg"],
        relief="flat", font=("sans-serif", 10, "bold"),
        padx=14, pady=6, cursor="hand2",
        command=lambda: save_memo(text_area.get("1.0", "end-1c"), screenshot_path, root)
    )
    save_btn.pack(side="right")

    root.bind("<Control-Return>", lambda e: save_memo(text_area.get("1.0", "end-1c"), screenshot_path, root))
    root.bind("<Escape>", lambda e: root.destroy())

    tk.Label(root, text="Ctrl+Enter to save  ·  Esc to cancel",
             bg=COLORS["bg"], fg=COLORS["muted"],
             font=("sans-serif", 8)).pack(pady=(0, 10))

    root.mainloop()


def main():
    # Check if we're being relaunched after a screenshot
    shot_path = os.environ.get(SHOT_ENV_VAR, "")
    text_file = os.environ.get("_MEMOS_TEXT", "")

    initial_text = ""
    if text_file and os.path.exists(text_file):
        with open(text_file, "r") as f:
            initial_text = f.read()
        os.unlink(text_file)

    if shot_path and not os.path.exists(shot_path):
        notify("Memos", "Screenshot cancelled.", icon="dialog-warning")
        shot_path = ""

    build_window(screenshot_path=shot_path or None, initial_text=initial_text)


if __name__ == "__main__":
    main()
