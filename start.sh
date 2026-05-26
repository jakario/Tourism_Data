#!/usr/bin/env bash
# ========================================
# Tourism Data Analytics - Startup Script
# ========================================
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "🚀 Tourism Data Analytics System"
echo "=================================="
echo ""

# 1. Seed data if database is empty
python3 -c "
import sys; sys.path.insert(0, '.')
from database.schema import get_connection
try:
    c = get_connection()
    cnt = c.execute('SELECT COUNT(*) as n FROM tourism_data').fetchone()['n']
    c.close()
    sys.exit(0 if cnt > 0 else 1)
except:
    sys.exit(1)
" && echo "✅ Database ready" || {
    echo "📦 Seeding tourism data into database..."
    python3 seed.py
    echo "✅ Seeding complete"
}

echo ""

# 2. Kill any existing Flask instance
kill $(pgrep -f "python3 app.py") 2>/dev/null || true
sleep 0.5

# 3. Start Flask
echo "🌐 Starting web app at http://localhost:5000"
echo "   Open in browser: http://localhost:5000"
echo ""
python3 app.py
