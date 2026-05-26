import sys, os

here = os.path.dirname(__file__)
root = os.path.abspath(os.path.join(here, "..", ".."))
sys.path.insert(0, root)

os.environ.setdefault("DATABASE_PATH", os.path.join(root, "data", "tourism_cache.db"))

from app import app
from serverless_wsgi import handle_request


def handler(event, context):
    return handle_request(app, event, context)
