from melodyvault.catalog.identity import build_identity_links
from melodyvault.catalog.grouping import group_recordings,identity_work_ids
from melodyvault.catalog.models import Artist,Recording
from catalog_fixtures import ARTIST_ID,OTHER_ID,recording,credit

ARTIST=Artist(ARTIST_ID,'周杰倫')


def aux(number,title='晴天',work='w1',isrc='TWAAA0100001',artist=ARTIST_ID):
    return {**recording(number,title), 'artist-credit':[credit(artist)],'video':True,'isrcs':[isrc],
            'relations':[{'type':'performance','target-type':'work','work':{'id':work,'title':title},'attributes':[]}]}


def test_video_same_isrc_explicit_work_supplies_identity_without_adding_video_version():
    rec=Recording.from_payload({**recording(1),'isrcs':['TWAAA0100001']})
    video=aux(2)
    links=build_identity_links(ARTIST,[rec],{'w1':{'title':'晴天'}},{video['id']:video})
    rec.identity_links=links[rec.mbid]
    songs=group_recordings(ARTIST,[rec],{'w1':{'title':'晴天'}})
    assert len(songs)==1 and not songs[0].pending_confirmation
    assert songs[0].work_ids==('w1',) and len(songs[0].recordings)==1
    assert 'relations' not in rec.payload


def test_same_title_duration_without_isrc_relation_does_not_add_identity():
    rec=Recording.from_payload(recording(1));video=aux(2)
    assert not build_identity_links(ARTIST,[rec],{'w1':{'title':'晴天'}},{video['id']:video})


def test_conflicting_work_and_other_singer_are_not_hidden():
    rec=Recording.from_payload({**recording(1),'isrcs':['TWAAA0100001']})
    rec.details={**rec.payload,'relations':[{'type':'performance','target-type':'work','work':{'id':'w2','title':'晴天'},'attributes':[]}]}
    video=aux(2)
    rec.identity_links=build_identity_links(ARTIST,[rec],{'w1':{'title':'晴天'}},{video['id']:video})[rec.mbid]
    assert identity_work_ids(rec)=={'w1','w2'}
    assert group_recordings(ARTIST,[rec],{})[0].pending_confirmation
    foreign=aux(3,artist=OTHER_ID)
    assert not build_identity_links(ARTIST,[Recording.from_payload({**recording(1),'isrcs':['TWAAA0100001']})],{}, {foreign['id']:foreign})


def test_reverse_work_performance_is_explicit_evidence():
    rec=Recording.from_payload(recording(1))
    work={'id':'w1','title':'晴天','relations':[{'type':'performance','target-type':'recording','recording':{'id':rec.mbid}}]}
    links=build_identity_links(ARTIST,[rec],{'w1':work},{})
    assert links[rec.mbid][0]['rule']=='work_reverse_performance'


def test_shared_isrc_with_conflicting_live_studio_version_is_not_safe_bridge():
    rec=Recording.from_payload({**recording(1),'isrcs':['TWAAA0100001'],'disambiguation':'live'})
    other=aux(2);other['disambiguation']='studio'
    assert not build_identity_links(ARTIST,[rec],{}, {other['id']:other})


def test_enriched_version_updates_display_without_mutating_original_recording():
    raw={**recording(1),'disambiguation':'live, old'}
    rec=Recording.from_payload(raw)
    rec.details={**raw,'disambiguation':'live, 2025 concert'}
    assert '2025 concert' in rec.display_title and rec.payload['disambiguation']=='live, old'
    rec.details={**raw,'disambiguation':''}
    from melodyvault.catalog.grouping import version_kind
    assert version_kind(rec)[0]=='unknown' and 'old' not in rec.display_title
