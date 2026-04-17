# Auto-Open CangreDashboard on macOS Startup

Two options depending on whether you want it to start **on login** (LaunchAgent) or **on demand with a single command** (shell alias).

---

## Option 1 — macOS LaunchAgent (recommended, starts on login)

Create the plist file at `~/Library/LaunchAgents/com.openclaw.cangredashboard.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.openclaw.cangredashboard</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/zsh</string>
        <string>-c</string>
        <string>cd /Users/fedeh/github/CangreDashboard/backend && bash run.sh &amp; sleep 5 &amp;&amp; open /Users/fedeh/github/CangreDashboard/frontend/build/index.html</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>/tmp/cangredashboard.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/cangredashboard.err</string>
</dict>
</plist>
```

Load it without rebooting:
```bash
launchctl load ~/Library/LaunchAgents/com.openclaw.cangredashboard.plist
```

To unload (stop auto-start):
```bash
launchctl unload ~/Library/LaunchAgents/com.openclaw.cangredashboard.plist
```

---

## Option 2 — Shell alias (on-demand, one command)

Add to `~/.zshrc`:

```zsh
alias cangre='(cd ~/github/CangreDashboard/backend && bash run.sh &); sleep 4 && open ~/github/CangreDashboard/frontend/build/index.html'
```

Then reload:
```bash
source ~/.zshrc
```

Usage: just type `cangre` in any terminal.

---

## Notes

- The backend runs at `http://127.0.0.1:5001`
- The frontend opens as a local file (`file://...`). No web server required.
- Logs from the LaunchAgent go to `/tmp/cangredashboard.log`
- To check if the backend is already running: `lsof -i :5001`
