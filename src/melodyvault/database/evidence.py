"""Timestamped positive/negative official evidence checks; batch writes."""
import json
import time
from melodyvault.database import connect


def fresh_checks(repository, kind, profile, ttl=7*86400):
    with connect(repository.path) as db:
        return {r[0] for r in db.execute('SELECT entity_id FROM catalog_task_cache WHERE kind=? AND profile=? AND checked_at>?',
                                        (kind,profile,time.time()-ttl))}


def save_checks(repository, kind, profile, items):
    with repository.transaction() as db:
        for entity_id, status, payload in items:
            db.execute('INSERT INTO catalog_task_cache VALUES (?,?,?,?,?,?) ON CONFLICT(kind,entity_id,profile) DO UPDATE SET status=excluded.status,checked_at=excluded.checked_at,payload_json=excluded.payload_json',
                       (kind,entity_id,profile,status,time.time(),json.dumps(payload)))
