import sys, os, shutil

here = os.path.dirname(__file__)
root = os.path.abspath(os.path.join(here, "..", ".."))
sys.path.insert(0, root)

# On Lambda /var/task is read-only — copy DB to /tmp/ for SQLite writes
bundled_db = os.path.join(here, "data", "tourism_cache.db")
if os.path.exists(bundled_db):
    tmp_db = os.path.join("/tmp", "tourism_cache.db")
    if not os.path.exists(tmp_db):
        shutil.copy2(bundled_db, tmp_db)
    os.environ["DATABASE_PATH"] = tmp_db
else:
    os.environ.setdefault("DATABASE_PATH", os.path.join(root, "data", "tourism_cache.db"))

from app import app
from serverless_wsgi import handle_request


def handler(event, context):
    return handle_request(app, event, context)
