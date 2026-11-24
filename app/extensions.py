from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect()

# Penyimpanan di memori cukup untuk 1 proses. Bila deploy dengan banyak worker,
# ganti ke Redis: storage_uri="redis://localhost:6379"
limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")
