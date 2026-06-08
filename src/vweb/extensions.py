"""Flask extensions initialized with deferred init_app pattern."""

from authlib.integrations.flask_client import OAuth
from flask_caching import Cache
from flask_wtf.csrf import CSRFProtect

cache = Cache()
oauth = OAuth()
# Shared so individual views (e.g. the Apple callback, which Apple POSTs to
# cross-site without a CSRF token) can be exempted via csrf.exempt(...).
csrf = CSRFProtect()
