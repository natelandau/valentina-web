"""Flask extensions initialized with deferred init_app pattern."""

from authlib.integrations.flask_client import OAuth
from flask_caching import Cache

cache = Cache()
oauth = OAuth()
