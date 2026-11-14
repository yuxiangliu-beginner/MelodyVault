import json
import sqlite3
from pathlib import Path
import pytest
from melodyvault.catalog.models import Artist,Recording,CatalogError
from melodyvault.catalog.grouping import group_recordings
from melodyvault.catalog.review import ReviewService,suggestions,recording_set
from melodyvault.database import initialize_database,connect
from melodyvault.database.catalog import CatalogRepository
from melodyvault.database.reviews import ReviewRepository
from catalog_fixtures import ARTIST_ID,recording,credit,OTHER_ID


@pytest.fixture
def review_data(tmp_path):
    repo=CatalogRepository(tmp_path/'review.sqlite3');initialize_database(repo.path)
    artist=Artist.from_payload({'id':ARTIST_ID,'name':'周杰倫'})
    repo.save_artist('周杰伦',artist)
    records=[Recording.from_payload(recording(i,'晴天' if i<4 else '另一首')) for i in range(1,5)]
    repo.save_recordings(artist,records)
    details=[]
    for number,work in ((1,'w1'),(3,'w2')):
        details.append({**records[number-1].payload,'relations':[{'type':'performance','target-type':'work','work':{'id':work,'title':'晴天'},'attributes':[]}]})
    repo.save_details(details);repo.save_works([{'id':wid,'title':'晴天','aliases':[]} for wid in ('w1','w2')])
    service=ReviewService(repo,actor='qa_automation')
    return repo,artist,records,service


def find(snapshot,mbid):
    return next(s for s in snapshot['result'].songs if mbid in recording_set(s))


def test_weak_suggestions_are_review_only_and_work_conflicts_block_merge(review_data):
    repo,artist,records,service=review_data;snap=service.load(artist)
    source=find(snap,records[1].mbid);target=find(snap,records[0].mbid)
    candidates=suggestions(artist,source,snap['result'].songs,snap['works'])
    assert any(c['target_song_id']==target.id and c['confidence'].startswith('低') for c in candidates)
    assert source.pending_confirmation and len(snap['result'].songs)==4
    with pytest.raises(CatalogError,match='不同.*Work'):
        service.decide(artist,'merge',find(snap,records[2].mbid).id,target.id,'不能合并同名不同作品')
    assert not ReviewRepository(repo).events(artist.mbid)


def test_merge_and_undo_append_audit_preserve_all_raw_and_versions(review_data):
    repo,artist,records,service=review_data;snap=service.load(artist)
    with connect(repo.path) as db:before=list(db.execute('SELECT mbid,payload_json FROM catalog_recordings ORDER BY mbid'))
    source=find(snap,records[1].mbid);target=find(snap,records[0].mbid)
    merged=service.decide(artist,'merge',source.id,target.id,'已人工核对作品，保留不同录音版本')
    assert len(find(merged,records[0].mbid).recordings)==2
    assert find(merged,records[0].mbid).reviewed
    assert merged['result'].summary['manually_reviewed_item_count']==1
    event=merged['events'][-1]
    assert event['actor']=='qa_automation' and event['payload']['candidate_evidence']['confidence'].startswith('低')
    reloaded=service.load(artist)
    assert len(find(reloaded,records[0].mbid).recordings)==2
    undone=service.decide(artist,'undo',undo_of=event['id'],reason='撤销测试决定')
    assert len(undone['result'].songs)==4
    assert find(undone,records[1].mbid).pending_confirmation
    assert len(undone['events'])==2 and undone['statuses'][event['id']]['status']=='undone'
    with connect(repo.path) as db:assert [tuple(r) for r in before]==[tuple(r) for r in db.execute('SELECT mbid,payload_json FROM catalog_recordings ORDER BY mbid')]


def test_reject_independent_undo_and_rejection_survives_auto_refresh(review_data):
    repo,artist,records,service=review_data;snap=service.load(artist)
    source=find(snap,records[1].mbid);target=find(snap,records[0].mbid)
    rejected=service.decide(artist,'reject',source.id,target.id,'名称相同不足以证明同一作品')
    assert find(rejected,records[1].mbid).pending_confirmation
    assert find(rejected,records[1].mbid).review_action=='reject'
    repo.save_details([{**records[1].payload,'relations':[{'type':'performance','target-type':'work','work':{'id':'w1','title':'晴天'},'attributes':[]}]}])
    refreshed=service.load(artist)
    assert find(refreshed,records[1].mbid).id!=find(refreshed,records[0].mbid).id
    separate=service.decide(artist,'independent',find(refreshed,records[1].mbid).id,reason='人工确认保留独立条目')
    assert not find(separate,records[1].mbid).pending_confirmation
    assert find(separate,records[1].mbid).review_action=='independent'
    undone=service.decide(artist,'undo',undo_of=separate['events'][-1]['id'],reason='撤销独立确认')
    assert find(undone,records[1].mbid).pending_confirmation


def test_undo_dependency_marks_later_review_stale_instead_of_remerging(review_data):
    repo,artist,records,service=review_data;snap=service.load(artist)
    first=service.decide(artist,'merge',find(snap,records[1].mbid).id,find(snap,records[0].mbid).id,'第一次确认')
    first_id=first['events'][-1]['id']
    second=service.decide(artist,'merge',find(first,records[3].mbid).id,find(first,records[0].mbid).id,'第二次依赖已合并目标')
    second_id=second['events'][-1]['id']
    undone=service.decide(artist,'undo',undo_of=first_id,reason='撤销前序决定')
    assert undone['statuses'][second_id]['status']=='stale'
    assert find(undone,records[0].mbid).id!=find(undone,records[1].mbid).id
    assert undone['result'].summary['stale_review_count']==1


def test_new_conflicting_work_makes_old_manual_merge_stale(review_data):
    repo,artist,records,service=review_data;snap=service.load(artist)
    merged=service.decide(artist,'merge',find(snap,records[1].mbid).id,find(snap,records[0].mbid).id,'此前人工确认')
    event_id=merged['events'][-1]['id']
    repo.save_details([{**records[1].payload,'relations':[{'type':'performance','target-type':'work','work':{'id':'w2','title':'晴天'},'attributes':[]}]}])
    updated=service.load(artist)
    assert updated['statuses'][event_id]['status']=='stale'
    assert find(updated,records[0].mbid).id!=find(updated,records[1].mbid).id


def test_audit_is_append_only_and_optimistic_commit_rejects_stale_head(review_data):
    repo,artist,records,service=review_data;snap=service.load(artist)
    service.decide(artist,'independent',find(snap,records[1].mbid).id,reason='独立保存')
    for sql in ('DELETE FROM catalog_review_events','UPDATE catalog_review_events SET reason="tamper"'):
        with connect(repo.path) as db:
            with pytest.raises(sqlite3.IntegrityError,match='append-only'):db.execute(sql)
    with pytest.raises(CatalogError,match='历史已变化'):
        ReviewRepository(repo).commit(artist,snap['result'].songs,'test',None)
    assert len(ReviewRepository(repo).events(artist.mbid))==1


def test_review_reason_required_and_cross_artist_ids_rejected(review_data):
    repo,artist,records,service=review_data;snap=service.load(artist)
    with pytest.raises(CatalogError,match='理由'):
        service.decide(artist,'independent',find(snap,records[1].mbid).id,reason='')
    with pytest.raises(CatalogError,match='源条目'):
        service.decide(artist,'merge','other-artist-song',find(snap,records[0].mbid).id,'不能跨歌手')


def test_live_and_rerecorded_remain_distinct_recording_versions(review_data):
    repo,artist,records,service=review_data
    live={**records[1].payload,'disambiguation':'live'}
    rerecorded={**records[3].payload,'disambiguation':'re-recording'}
    for payload in (live,rerecorded):
        repo.save_details([{**payload,'relations':[{'type':'performance','target-type':'work','work':{'id':'w1','title':'晴天'},'attributes':[]}]}])
    snap=service.load(artist)
    song=find(snap,records[0].mbid)
    assert len(song.recordings)==3
    from melodyvault.catalog.grouping import version_kind
    assert {version_kind(r)[0] for r in song.recordings} >= {'live','rerecording'}
