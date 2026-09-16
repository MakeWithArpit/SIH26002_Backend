from .base import *

DEBUG = False

# Parse ALLOWED_HOSTS from env; fallback to onrender.com and localhost
allowed_env = os.getenv('ALLOWED_HOSTS', '')
if allowed_env:
    ALLOWED_HOSTS = [host.strip() for host in allowed_env.split(',') if host.strip()]
else:
    ALLOWED_HOSTS = ['.onrender.com', 'localhost', '127.0.0.1']
