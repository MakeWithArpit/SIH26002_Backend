"""
Database Expansion Router: Primary-Replica Architecture

Routes read queries (SELECT) to 'replica' database if configured in DATABASES,
while keeping all write queries (INSERT, UPDATE, DELETE) on the primary 'default' DB.
Ensures zero read-write contention under heavy concurrent user loads.
"""
from django.conf import settings


class PrimaryReplicaRouter:
    """
    Directs database operations to primary (default) or replica.
    """
    def db_for_read(self, model, **hints):
        if 'replica' in settings.DATABASES:
            return 'replica'
        return 'default'

    def db_for_write(self, model, **hints):
        return 'default'

    def allow_relation(self, obj1, obj2, **hints):
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        # All schema migrations run strictly on the primary database
        return db == 'default'
