"""Append-only local review audit; event and derived mapping commit atomically."""
import json
import time
from melodyvault.catalog.models import CatalogError
from melodyvault.database import connect
from melodyvault.database.catalog import CatalogRepository, encode


class ReviewRepository:
    def __init__(self, catalog: CatalogRepository):
        self.catalog=catalog

    def events(self, artist_mbid):
        with connect(self.catalog.path) as db:
            rows=db.execute('SELECT rowid AS sequence,* FROM catalog_review_events WHERE artist_mbid=? ORDER BY rowid',(artist_mbid,)).fetchall()
        return [{**dict(row),'payload':json.loads(row['payload_json'])} for row in rows]

    def commit(self,artist,songs,rule_version,expected_head,event=None,summary=None):
        with self.catalog.transaction() as db:
            head=db.execute('SELECT id FROM catalog_review_events WHERE artist_mbid=? ORDER BY rowid DESC LIMIT 1',(artist.mbid,)).fetchone()
            if (head[0] if head else None)!=expected_head:
                raise CatalogError('审核历史已变化，请刷新后重试；未覆盖其他审核决定。')
            if event:
                db.execute('INSERT INTO catalog_review_events VALUES (?,?,?,?,?,?,?,?)',
                    (event['id'],artist.mbid,event['action'],encode(event['payload']),event['reason'],event['actor'],event['created_at'],event.get('undo_of')))
            self.catalog.write_grouping(db,artist,songs,rule_version)
            if summary is not None:
                payload={'head':event['id'] if event else expected_head,'summary':summary}
                db.execute("INSERT INTO catalog_task_cache VALUES ('review_summary',?,'v1','current',?,?) ON CONFLICT(kind,entity_id,profile) DO UPDATE SET checked_at=excluded.checked_at,payload_json=excluded.payload_json",
                           (artist.mbid,time.time(),encode(payload)))
