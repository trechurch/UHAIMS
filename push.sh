#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  push.sh  —  one-command deploy to GitHub
#
#  Usage:
#    ./push.sh                        # auto-generates commit message
#    ./push.sh "your message here"    # uses your message
#
#  From Claude Code terminal:
#    ! ./push.sh
#    ! ./push.sh "nav fix + export tz"
# ─────────────────────────────────────────────────────────────────────────────
set -e
cd "$(dirname "$0")"

# ── Stage all tracked + new files (secrets.toml / docs/ blocked by .gitignore)
git add .

# ── Bail early if there's nothing to commit
if git diff --cached --quiet; then
    echo "✓  Nothing to commit — working tree is clean."
    exit 0
fi

# ── Commit message: arg 1 or auto-timestamp
MSG="${1:-Update $(date '+%Y-%m-%d %H:%M')}"
git commit -m "$MSG"

# ── Push
git push origin main

echo ""
echo "✓  Pushed to origin/main"
