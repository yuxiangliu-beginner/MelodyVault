"""Try distinct source hints through the original fail-closed verifier.

Each attempt is an independent persisted job; a search score never grants
permission. Other queued jobs are not started. A pause/stop is terminal.
"""
from melodyvault.catalog.musicbrainz import check_cancel
from melodyvault.catalog.musicbrainz import MusicBrainzClient
from melodyvault.catalog.models import CatalogCancelled
from melodyvault.database.catalog import CatalogRepository
from melodyvault.database.discovery import DiscoveryRepository
from melodyvault.downloads.eligibility import DownloadEligibilityService
import threading


class SourceFallbackManager:
    def __init__(self,repository,manager,cancel,progress=None,record=None):
        self.repository=repository;self.manager=manager;self.cancel=cancel
        self.progress=progress or (lambda event:None)
        self.record=record or (lambda event:None)
    def run(self,target,candidates,settings):
        seen=set();attempts=[]
        def add(entry):attempts.append(entry);self.record(entry)
        for candidate in sorted(candidates,key=lambda c:c.match_score,reverse=True):
            check_cancel(self.cancel)
            raw=candidate.raw_source
            key=(raw.get('provider'),raw.get('external_id'))
            if not all(key) or key in seen:continue
            seen.add(key)
            if raw.get('match_status')=='VERSION_MISMATCH':
                add({'source':key,'state':'SKIPPED','reason_code':'VERSION_MISMATCH'});continue
            if not DiscoveryRepository(self.repository.path).provider_allowed(raw['provider']):
                add({'source':key,'state':'SKIPPED','reason_code':'SOURCE_DISABLED','reason':'来源禁用或审核已过期'});continue
            try:
                self.progress({'stage':'verify_and_download','source':key,'job_id':''})
                with self.manager.source_http_factory(self.cancel) as http, MusicBrainzClient(CatalogRepository(self.repository.path),self.cancel) as mb:
                    verified=self.manager.verifier_factory(http,mb).verify(raw,target)
                check_cancel(self.cancel)
                if not DownloadEligibilityService.allowed(verified):
                    add({'source':key,'state':'SKIPPED','reason_code':verified.evidence.get('decision','LICENSE_UNVERIFIED'),
                        'reason':'；'.join(verified.verification_reason)});continue
            except CatalogCancelled:raise
            except Exception as error:
                add({'source':key,'state':'FAILED','reason_code':'VERIFICATION_FAILED','reason':str(error)});continue
            jid=self.repository.enqueue(target,settings,candidate=raw)
            self.progress({'stage':'verify_and_download','job_id':jid,'source':key})
            previous_progress=self.manager.progress
            def report():
                row=self.repository.get(jid)
                self.progress({'stage':'download_progress','job_id':jid,'state':row['state'],
                    'bytes_received':row['bytes_received'],'total_bytes':row['total_bytes'],'reason':row['reason']})
                previous_progress()
            self.manager.progress=report
            finished=threading.Event()
            def watch():
                while not finished.wait(.1):
                    if self.cancel.is_set():
                        self.manager.stop(jid,'CANCELLED');return
            watcher=threading.Thread(target=watch,daemon=True);watcher.start()
            try:self.manager.run(job_ids=[jid],settings_override=settings)
            finally:finished.set();watcher.join();self.manager.progress=previous_progress
            row=self.repository.get(jid)
            add({'source':key,'job_id':jid,'state':row['state'],
                 'reason_code':row['reason_code'],'reason':row['reason']})
            if row['state'] in {'COMPLETED','READY','PAUSED','CANCELLED'}:break
        return attempts
