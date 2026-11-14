"""An explicitly scheduled, cancellable evidence task; never fetches a catalog."""
import hashlib
import json
import time

from melodyvault.catalog.enrichment import enrich_recordings
from melodyvault.catalog.supplement import supplement_pending
from melodyvault.catalog.musicbrainz import check_cancel
from melodyvault.catalog.review import ReviewService
from melodyvault.database import connect


def enrich_artist(repository, client, artist, progress):
    check_cancel(client.cancel)
    with connect(repository.path) as db:
        ids = [r[0] for r in db.execute('SELECT recording_mbid FROM catalog_artist_recordings WHERE artist_mbid=? ORDER BY recording_mbid',(artist.mbid,))]
        profile = hashlib.sha256(json.dumps(ids).encode()).hexdigest()
        cached = db.execute("SELECT checked_at,payload_json FROM catalog_task_cache WHERE kind='deep' AND entity_id=? AND profile=? AND status='ok'",(artist.mbid,profile)).fetchone()
    if cached and not client.force_refresh and time.time()-cached[0] < 7*86400:
        return {**json.loads(cached[1]), 'deep_task_reused':True}
    enrich_recordings(repository,client,artist,progress)
    stats = supplement_pending(repository,client,artist,progress)
    check_cancel(client.cancel)
    ReviewService(repository).load(artist)
    with connect(repository.path) as db:
        db.execute("INSERT INTO catalog_task_cache VALUES ('deep',?,?,'ok',?,?) ON CONFLICT(kind,entity_id,profile) DO UPDATE SET checked_at=excluded.checked_at,status=excluded.status,payload_json=excluded.payload_json",
                   (artist.mbid,profile,time.time(),json.dumps(stats)))
    return {**stats, 'deep_task_reused':False}
