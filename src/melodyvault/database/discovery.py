"""Registry policy and health are independent of any file's copyright license."""
import json,time,hashlib
from uuid import uuid4
from dataclasses import asdict
from melodyvault.database import connect
from melodyvault.database.catalog import encode
from melodyvault.discovery.models import domain_key,public_url,STATES
from melodyvault.privacy import redact_payload

BUILTINS = {
    'commons.wikimedia.org': ('Wikimedia Commons','commons'),
    'archive.org': ('Internet Archive','archive'),
    'api.jamendo.com': ('Jamendo API','jamendo'),
    'ccmixter.org': ('ccMixter','ccmixter'),
}


class DiscoveryRepository:
    def __init__(self,path): self.path=path
    def discover(self,hit):
        url=public_url(hit.url);domain=domain_key(url);now=time.time()
        with connect(self.path) as db:
            db.execute('INSERT OR IGNORE INTO discovered_sources(domain,name,first_url,discovered_at) VALUES (?,?,?,?)',
                       (domain,hit.name[:240],url,now))
            db.execute('INSERT INTO source_discovery_history VALUES (?,?,?,?,?,?,?)',
                       (str(uuid4()),domain,hit.query,hit.channel,url,encode(redact_payload(hit.evidence)),now))
        return domain
    def rows(self):
        with connect(self.path) as db:
            rows=db.execute('SELECT s.*,c.payload_json FROM discovered_sources s LEFT JOIN source_capabilities c USING(domain) ORDER BY s.discovered_at DESC').fetchall()
        return [{**dict(r),'capabilities':json.loads(r['payload_json'] or '{}')} for r in rows]
    def get(self,domain):return next((r for r in self.rows() if r['domain']==domain),None)
    def verify(self,domain,capabilities):
        state=capabilities['state']
        if state not in STATES:raise ValueError('Unknown discovery state')
        failed=state in {'UNAVAILABLE','UNSAFE'};now=time.time()
        with connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                row=db.execute('SELECT * FROM discovered_sources WHERE domain=?',(domain,)).fetchone()
                if row is None:raise ValueError('Unknown source')
                failures=row['failures']+1 if failed else 0
                db.execute('UPDATE discovered_sources SET checked_at=?,state=?,risk=?,failures=?,enabled=?,last_error=? WHERE domain=?',
                           (now,state,capabilities.get('risk','UNKNOWN'),failures,
                            int(not row['manual_disabled'] and failures<3 and state!='UNSAFE'),capabilities.get('error',''),domain))
                db.execute('INSERT OR REPLACE INTO source_capabilities VALUES (?,?)',(domain,encode(redact_payload(capabilities))))
                db.execute('INSERT INTO source_verification_history VALUES (?,?,?,?,?)',(str(uuid4()),domain,'check',encode(redact_payload(capabilities)),now))
                db.commit()
            except BaseException:db.rollback();raise
    def set_enabled(self,domain,enabled):
        with connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                db.execute('UPDATE discovered_sources SET enabled=?,manual_disabled=? WHERE domain=?',(int(enabled),int(not enabled),domain))
                db.execute('INSERT INTO source_verification_history VALUES (?,?,?,?,?)',(str(uuid4()),domain,'manual_enable' if enabled else 'manual_disable','{}',time.time()))
                db.commit()
            except BaseException:db.rollback();raise
    def approve_compiled(self,domain,provider,policy):
        # This is code-reviewed policy, not a UI "trust this website" button.
        if BUILTINS.get(domain,('',None))[1]!=provider:raise ValueError('Only compiled audited adapters can be approved')
        row=self.get(domain)
        if not row or row['state'] in {'UNSAFE','UNAVAILABLE','RESTRICTED'}:raise ValueError('Source check required')
        if not row['capabilities'].get('automation_allowed'):raise ValueError('Automation permission required')
        with connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                db.execute("UPDATE discovered_sources SET provider=?,review_status='APPROVED',kind='official_api' WHERE domain=?",(provider,domain))
                db.execute('INSERT INTO source_verification_history VALUES (?,?,?,?,?)',(str(uuid4()),domain,'compiled_policy_review',encode(policy),time.time()))
                db.commit()
            except BaseException:db.rollback();raise
    def provider_allowed(self,provider):
        if provider=='archive_chrome':provider='archive'
        rows=[r for r in self.rows() if r['provider']==provider or BUILTINS.get(r['domain'],('',None))[1]==provider]
        if not rows:return provider!='ccmixter'  # injected compiled/test providers retain their own policy
        return any(r['enabled'] and r['review_status']=='APPROVED' and r['state'] not in {'UNSAFE','UNAVAILABLE','RESTRICTED'}
                   and r['capabilities'].get('automation_allowed') is True and time.time()-r['checked_at']<7*86400 for r in rows)
    def attempt(self,provider,success,hit=False,error=''):
        rows=[r for r in self.rows() if r['provider']==provider]
        for r in rows:
            with connect(self.path) as db:
                db.execute('UPDATE discovered_sources SET attempts=attempts+1,hits=hits+?,failures=?,enabled=?,last_error=? WHERE domain=?',
                    (int(hit),0 if success else r['failures']+1,int(not r['manual_disabled'] and (success or r['failures']+1<3)),error,r['domain']))
                db.execute('INSERT INTO source_verification_history VALUES (?,?,?,?,?)',(str(uuid4()),r['domain'],'provider_attempt',encode({'success':success,'hit':hit,'error':error}),time.time()))
    def observe_candidates(self,provider,items):
        """File evidence updates capabilities; it never grants provider-wide rights."""
        import re
        for row in self.rows():
            if row['provider']!=provider:continue
            full=[c for c in items if c.get('duration_seconds') and c.get('file_size') and c.get('audio_url')
                  and not re.search(r'preview|excerpt|sample|snippet',c.get('title',''),re.I)
                  and not set(c.get('evidence',{}).get('tags',[])) & {'sample','stems','loops','spoken_word'}]
            cap=row['capabilities']
            cap['formats']=sorted(set(cap.get('formats',[]))|{c['file_format'] for c in items if c.get('file_format')})
            cap['full_audio']=bool(cap.get('full_audio') or full)
            cap['candidate_files_observed']=cap.get('candidate_files_observed',0)+len(items)
            cap['file_licenses_observed']=cap.get('file_licenses_observed',0)+sum(c.get('license_status')=='LICENSE_VERIFIED' for c in items)
            cap['download_permission']='LICENSE_UNVERIFIED'  # only Eligibility can grant per-file execution
            with connect(self.path) as db:
                db.execute('UPDATE source_capabilities SET payload_json=? WHERE domain=?',(encode(redact_payload(cap)),row['domain']))
                db.execute('INSERT INTO source_verification_history VALUES (?,?,?,?,?)',
                    (str(uuid4()),row['domain'],'file_observations',encode({'external_ids':[c.get('external_id') for c in items],
                     'full_candidates':len(full),'file_license_verified':sum(c.get('license_status')=='LICENSE_VERIFIED' for c in items)}),time.time()))
    def history(self,domain):
        with connect(self.path) as db:
            return {'discoveries':[dict(r) for r in db.execute('SELECT * FROM source_discovery_history WHERE domain=? ORDER BY created_at DESC LIMIT 100',(domain,))],
                    'checks':[dict(r) for r in db.execute('SELECT * FROM source_verification_history WHERE domain=? ORDER BY created_at DESC LIMIT 100',(domain,))]}
    def cache(self,key,value=None,ttl=6*3600):
        key=hashlib.sha256(key.encode()).hexdigest()
        with connect(self.path) as db:
            if value is not None:
                db.execute('INSERT OR REPLACE INTO source_discovery_cache VALUES (?,?,?)',(key,encode(redact_payload(value)),time.time()));return value
            row=db.execute('SELECT * FROM source_discovery_cache WHERE cache_key=?',(key,)).fetchone()
        return json.loads(row['payload_json']) if row and time.time()-row['checked_at']<ttl else None
