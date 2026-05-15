import os
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from core.db import get_sqlalchemy_url

_REDIS_URL = os.environ.get("REDIS_URL", "")

# Limiter initialization
# Note: app will be initialized later via limiter.init_app(app)
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_REDIS_URL or "memory://",
    default_limits=[],
)

# Scheduler initialization
scheduler = BackgroundScheduler(
    daemon=True,
    jobstores={"default": SQLAlchemyJobStore(url=get_sqlalchemy_url())},
)
