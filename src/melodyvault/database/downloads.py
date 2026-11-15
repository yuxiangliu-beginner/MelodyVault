"""Persistent queue, immutable evidence and verified files. No catalog writes."""
import json,hashlib
from dataclasses import asdict
from uuid import uuid4
from melodyvault.database import connect
from melodyvault.database.catalog import utc_now,encode
from melodyvault.downloads.models import DownloadSettings,STATES
from melodyvault.privacy import redact_payload


class DownloadRepository:
    def __init__(self,path):self.path=path
    def settings(self):
        with connect(self.path) as db:row=db.execute('SELECT payload_json FROM download_settings WHERE id=1').fetchone()
        return DownloadSettings(**json.loads(row[0])).validate() if row else DownloadSettings()
    def save_settings(self,settings):
        settings.validate()
        with connect(self.path) as db:db.execute('INSERT INTO download_settings VALUES(1,?) ON CONFLICT(id) DO UPDATE SET payload_json=excluded.payload_json',(encode(asdict(settings)),))
    def enqueue(self,target,settings,batch_id=None,candidate=None):
        settings.validate();dry=not settings.automatic_download
        if candidate:target={**target,'source_hint':candidate}
        target=redact_payload(target);candidate=redact_payload(candidate)
        key=hashlib.sha256(encode([target['song_id'],target['recording_id'],target.get('artist',{}).get('id',''),dry,(candidate or {}).get('provider'),(candidate or {}).get('external_id')]).encode()).hexdigest()
        with connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            existing=db.execute("SELECT id FROM download_jobs WHERE dedupe_key=? AND state IN ('QUEUED','SEARCHING','VERIFYING','READY','DOWNLOADING','PAUSED')",(key,)).fetchone()
            if existing:db.commit();return existing[0]
            jid=str(uuid4());now=utc_now()
            db.execute('INSERT INTO download_jobs(id,batch_id,dedupe_key,target_json,candidate_json,state,dry_run,settings_json,created_at,updated_at) VALUES(?,?,?,?,?,\'QUEUED\',?,?,?,?)',
                (jid,batch_id or str(uuid4()),key,encode(target),encode(candidate or {}),int(dry),encode(asdict(settings)),now,now));db.commit()
        return jid
    def get(self,jid):
        with connect(self.path) as db:row=db.execute('SELECT * FROM download_jobs WHERE id=?',(jid,)).fetchone()
        if not row:raise KeyError(jid)
        data=dict(row)
        for field in ('target','candidate','settings','result'):data[field]=json.loads(data[field+'_json'])
        return data
    def rows(self,limit=200):
        with connect(self.path) as db:rows=db.execute("SELECT id,batch_id,state,reason,reason_code,dry_run,bytes_received,total_bytes,speed,eta,updated_at,json_object('title',json_extract(target_json,'$.title'),'artist',json_object('name',json_extract(target_json,'$.artist.name'))) AS target_json,json_object('provider',json_extract(candidate_json,'$.provider')) AS candidate_json FROM download_jobs ORDER BY created_at DESC LIMIT ?",(limit,)).fetchall()
        return [dict(row) for row in rows]
    def ids(self,states):
        states=list(states)
        with connect(self.path) as db:return [r[0] for r in db.execute('SELECT id FROM download_jobs WHERE state IN ('+','.join('?' for _ in states)+') ORDER BY created_at',states)]
    def update(self,jid,**fields):
        allowed={'state','reason_code','reason','candidate_json','bytes_received','total_bytes','speed','eta','part_path','etag','last_modified','resource_url','attempt_count','result_json'}
        if not fields or set(fields)-allowed:raise ValueError('Invalid download update')
        if 'state' in fields and fields['state'] not in STATES:raise ValueError('Invalid download state')
        for name in ('candidate_json','result_json'):
            if name in fields:fields[name]=encode(redact_payload(json.loads(fields[name])))
        fields['updated_at']=utc_now()
        with connect(self.path) as db:db.execute('UPDATE download_jobs SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',(*fields.values(),jid))
    def recover(self):
        with connect(self.path) as db:
            db.execute("UPDATE download_jobs SET state='PAUSED',speed=0,eta=NULL,reason_code='RESTART_RECOVERY',reason='上次任务未结束，等待用户继续；续传前重新核验来源和对象',updated_at=? WHERE state IN ('SEARCHING','VERIFYING','DOWNLOADING')",(utc_now(),))
    def evidence(self,jid,step,decision,payload):
        with connect(self.path) as db:db.execute('INSERT INTO download_evidence VALUES(?,?,?,?,?,?)',(str(uuid4()),jid,step,decision,encode(redact_payload(payload)),utc_now()))
    def evidence_rows(self,jid):
        with connect(self.path) as db:return [dict(r) for r in db.execute('SELECT * FROM download_evidence WHERE job_id=? ORDER BY created_at',(jid,))]
    def attempt(self,jid,number,status,details):
        with connect(self.path) as db:db.execute('INSERT INTO download_attempts VALUES(?,?,?,?,?,?)',(str(uuid4()),jid,number,status,encode(details),utc_now()))
    def files(self,provider,external_id):
        with connect(self.path) as db:return [dict(r) for r in db.execute('SELECT * FROM downloaded_files WHERE provider=? AND external_id=?',(provider,external_id))]
    def completed_files(self):
        """Read verified archives for future upload, without changing upload state."""
        with connect(self.path) as db:
            rows=db.execute('SELECT * FROM downloaded_files ORDER BY verified_at,id').fetchall()
        result=[]
        for row in rows:
            item=dict(row); evidence=json.loads(item['evidence_json']); media=json.loads(item['media_json'])
            result.append({'song_id':evidence.get('song_id',''), 'recording_id':item['recording_id'],
                'artist':evidence.get('artist_name',''), 'title':evidence.get('title',''),
                'path':item['path'], 'format':media.get('format') or evidence.get('file_format',''),
                'size':item['bytes'], 'sha256':item['sha256'], 'completed_at':item['verified_at'],
                'provider':item['provider'], 'external_id':item['external_id'],
                'source_url':evidence.get('source_page_url',''), 'status':'COMPLETED'})
        return result
    def register_file(self,jid,candidate,path,verified,reused=False):
        result={**verified,'path':str(path),'reused':reused}
        with connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO downloaded_files VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(fingerprint,sha256) DO UPDATE SET path=excluded.path,media_json=excluded.media_json,evidence_json=excluded.evidence_json,verified_at=excluded.verified_at',(str(uuid4()),candidate.provider,candidate.external_id,candidate.recording_id,candidate.fingerprint,str(path),verified['sha256'],verified['sha1'],verified['bytes'],encode(verified),encode(redact_payload(candidate.to_dict())),utc_now()))
            db.execute("UPDATE download_jobs SET state='COMPLETED',reason_code='',reason='文件已验证并安全归档',bytes_received=?,total_bytes=?,speed=0,eta=NULL,result_json=?,updated_at=? WHERE id=?",(verified['bytes'],verified['bytes'],encode(result),utc_now(),jid));db.commit()
    def summary(self,batch_id=None):
        clause=' WHERE batch_id=?' if batch_id else ''
        with connect(self.path) as db:counts={r[0]:r[1] for r in db.execute('SELECT state,count(*) FROM download_jobs'+clause+' GROUP BY state',(batch_id,) if batch_id else ())}
        return {'total':sum(counts.values()),**{state:counts.get(state,0) for state in STATES}}
