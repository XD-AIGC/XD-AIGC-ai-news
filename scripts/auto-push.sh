#!/bin/bash
cd /AIGC_Group/XD-AIGC-ai-news
git add docs/data/ reports/markdown/
if ! git diff --cached --quiet; then
    git commit -m "data: daily report $(date +%Y-%m-%d)"
    git push origin main
fi
