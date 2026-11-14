"""Append source attempts; cache by immutable query snapshot, never by title alone."""
import json,time
from uuid import uuid4
from dataclasses import asdict
from melodyvault.database import connect
from melodyvault.database.catalog import encode,utc_now
from melodyvault.privacy import redact_payload


class SourceRepository:
    def __init__(self,path):self.path=path
    def begin(self,artist,queries):
        run_id=str(uuid4())
        with connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                db.execute('INSERT INTO source_runs VALUES (?,?,\'running\',?,NULL,\'{}\')',(run_id,artist,utc_now()))
                db.executemany('INSERT INTO source_jobs VALUES (?,?,?,\'pending\',\'{}\')',[(run_id,q.song_id,encode(asdict(q))) for q in queries])
                db.commit()
            except BaseException:db.rollback();raise
        return run_id
    def cached(self,provider,fingerprint,ttl=24*3600):
        with connect(self.path) as db:
            rows=db.execute("SELECT * FROM source_attempts WHERE provider=? AND fingerprint=? AND status='ok' ORDER BY checked_at DESC LIMIT 1",(provider,fingerprint)).fetchall()
        if not rows:return None
        row=dict(rows[0]);candidates=json.loads(row['candidates_json'])
        max_age=ttl if candidates else 6*3600
        return candidates if time.time()-row['checked_at']<max_age else None
    def attempt(self,run_id,query,provider,status,candidates,error=''):
        with connect(self.path) as db:
            db.execute('INSERT INTO source_attempts VALUES (?,?,?,?,?,?,?,?,?,?)',(str(uuid4()),run_id,query.song_id,provider,
                query.fingerprint,status,time.time(),error,encode(asdict(query)),encode(redact_payload(candidates))))
    def job(self,run_id,query,status,summary):
        with connect(self.path) as db:
            db.execute('UPDATE source_jobs SET status=?,summary_json=? WHERE run_id=? AND song_id=?',(status,encode(redact_payload(summary)),run_id,query.song_id))
    def finish(self,run_id,status,summary):
        with connect(self.path) as db:
            db.execute('UPDATE source_runs SET status=?,finished_at=?,summary_json=? WHERE id=?',(status,utc_now(),encode(redact_payload(summary)),run_id))
    def latest_jobs(self,artist_mbid):
        with connect(self.path) as db:
            rows=db.execute('SELECT j.*,r.started_at FROM source_jobs j JOIN source_runs r ON r.id=j.run_id WHERE r.artist_mbid=? ORDER BY r.started_at DESC',(artist_mbid,)).fetchall()
        latest={}
        for row in rows:
            if row['song_id'] not in latest:
                latest[row['song_id']]={**dict(row),'summary':json.loads(row['summary_json']),'query':json.loads(row['query_json'])}
        return latest
    def browser_check(self,url,status,evidence):
        with connect(self.path) as db:
            db.execute('INSERT INTO source_browser_checks VALUES (?,?,?,?,?)',(str(uuid4()),url,status,utc_now(),encode(evidence)))
