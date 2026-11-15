import threading,time
import pytest
from melodyvault.catalog.models import CatalogCancelled
from melodyvault.search.orchestrator import SearchOrchestrator,UnifiedCandidate


class Provider:
    def __init__(self,name,status='AVAILABLE',fail=False,delay=0):
        self.provider_id=name;self.status=status;self.fail=fail;self.delay=delay
    def get_status(self):return {'status':self.status}
    def search(self,query):
        time.sleep(self.delay)
        if self.fail:raise RuntimeError('simulated unavailable')
        return [UnifiedCandidate(self.provider_id,'https://example.org/a','Song',version_type='LIVE'),
                UnifiedCandidate(self.provider_id,'https://example.org/a','Song',version_type='LIVE'),
                UnifiedCandidate(self.provider_id,'https://example.org/a','Song',version_type='REMIX')]


def test_isolated_failure_progress_and_version_preservation():
    events=[]
    result=SearchOrchestrator([Provider('slow',delay=.1),Provider('failed',fail=True),Provider('restricted','RESTRICTED')],
        on_result=events.append).search('晴天')
    assert result['failed']['status']=='FAILED' and result['restricted']['status']=='RESTRICTED'
    assert {c.version_type for c in result['slow']['candidates']}=={'LIVE','REMIX'}
    assert events[-1]['provider_id']=='slow'
    assert all(c.download_permission=='PERMISSION_UNKNOWN' for c in result['slow']['candidates'])


def test_cancel_prevents_late_delivery():
    cancel=threading.Event();events=[]
    timer=threading.Timer(.02,cancel.set);timer.start()
    with pytest.raises(CatalogCancelled):
        SearchOrchestrator([Provider('slow',delay=.3)],cancel=cancel,on_result=events.append).search('test')
    timer.join();time.sleep(.35)
    assert not events


def test_rejects_duplicate_provider_ids():
    with pytest.raises(ValueError):SearchOrchestrator([Provider('x'),Provider('x')])
