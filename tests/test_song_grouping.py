"""Evidence rules, deliberately adversarial identities; fixtures are offline only."""
from copy import deepcopy
import pytest
from melodyvault.catalog.models import Artist, Recording
from melodyvault.catalog.grouping import group_recordings, grouping_statistics, version_kind
from melodyvault.catalog.normalize import title_key
from catalog_fixtures import ARTIST_ID, OTHER_ID, credit, recording

ARTIST = Artist(ARTIST_ID,'周杰倫')


def rec(n, title='龍拳', work=None, kind=None, isrc=None, artist=ARTIST_ID, official=True, contexts=None):
    data=recording(n,title,**{'artist-credit':[credit(artist)]})
    if isrc: data['isrcs']=[isrc]
    result=Recording.from_payload(data,official)
    result.details=deepcopy(data)
    result.details['relations']=[]
    if work:
        result.details['relations']=[{'target-type':'work','type':'performance','work':{'id':work,'title':title},'attributes':[kind] if kind else []}]
    elif kind:
        result.version=kind
        result.details['disambiguation']=kind
    result.contexts=contexts or []
    return result


def context(group='g1',position=1,kind='Album',secondary=None,release='r1',count=1):
    return {'release_group_mbid':group,'medium_position':1,'position':position,'status':'Official',
            'primary_type':kind,'secondary_types':secondary or [],'release_mbid':release,
            'credits':[credit()],'date':'2002-01-01','medium_track_count':count}


def test_same_work_studio_live_remix_and_primary():
    studio=rec(1,work='w1',contexts=[context()])
    live=rec(2,work='w1',kind='live',contexts=[context(secondary=['Live'])])
    remix=rec(3,work='w1',kind='remix')
    songs=group_recordings(ARTIST,[live,remix,studio],{'w1':{'title':'龍拳'}})
    assert len(songs)==1 and len(songs[0].recordings)==3
    assert songs[0].primary_recording_mbid==studio.mbid
    assert not songs[0].pending_confirmation
    assert version_kind(live)[0]=='live' and version_kind(remix)[0]=='remix'


def test_same_title_different_work_ids_never_merge_even_same_isrc():
    left=rec(1,work='w1',isrc='TWAAA0100001')
    right=rec(2,work='w2',isrc='TWAAA0100001')
    songs=group_recordings(ARTIST,[left,right],{'w1':{'title':'龙拳'},'w2':{'title':'龙拳'}})
    assert len(songs)==2
    assert {s.work_ids for s in songs}=={('w1',),('w2',)}


def test_same_title_and_artist_alone_is_not_merge_evidence():
    songs=group_recordings(ARTIST,[rec(1),rec(2)],{})
    assert len(songs)==2 and all(s.pending_confirmation for s in songs)
    assert grouping_statistics([rec(1),rec(2)],songs)['independent_song_count']==0


def test_traditional_spaces_punctuation_and_english_alias_need_additional_evidence():
    assert title_key(' 龍 拳！')==title_key('龙拳')
    assert title_key('Dragon-Fist')==title_key('dragon fist')
    anchor=rec(1,work='w1',isrc='TWAAA0100001')
    alias=rec(2,'DRAGON FIST!',isrc='TWAAA0100001')
    unknown=rec(3,'Dragon-Fist')
    works={'w1':{'title':'龍拳','aliases':[{'name':'Dragon Fist'}]}}
    songs=group_recordings(ARTIST,[anchor,alias,unknown],works)
    known=next(s for s in songs if not s.pending_confirmation)
    assert len(known.recordings)==2
    assert len(songs)==2 and next(s for s in songs if s.pending_confirmation).recordings[0].mbid==unknown.mbid


def test_same_recording_multiple_releases_is_one_version_with_duplicate_statistics():
    r=rec(1,work='w1',contexts=[context(release='r1'),context(release='r2'),context(release='r3')])
    songs=group_recordings(ARTIST,[r,deepcopy(r)],{'w1':{'title':'龍拳'}})
    assert len(songs)==1 and len(songs[0].recordings)==1
    stats=grouping_statistics([r],songs)
    assert stats['raw_recording_count']==1 and stats['duplicate_release_count']==2 and stats['version_count']==1


def test_official_same_group_slot_anchors_another_recording_id():
    anchor=rec(1,work='w1',contexts=[context()])
    duplicate=rec(2,'龙 拳',contexts=[context(release='r2')])
    songs=group_recordings(ARTIST,[anchor,duplicate],{'w1':{'title':'龍拳'}})
    assert len(songs)==1 and not songs[0].pending_confirmation
    assert any(e['rule']=='release_slot' for e in songs[0].evidence)


def test_unknown_cannot_transitively_bridge_two_different_works():
    left=rec(1,work='w1',isrc='TWAAA0100001',contexts=[context()])
    unknown=rec(2,isrc='TWAAA0100001',contexts=[context()])
    right=rec(3,work='w2',contexts=[context()])
    for records in ([left,unknown,right],[right,unknown,left]):
        songs=group_recordings(ARTIST,records,{'w1':{'title':'龍拳'},'w2':{'title':'龍拳'}})
        assert len(songs)==3
        assert next(s for s in songs if s.recordings[0].mbid==unknown.mbid).pending_confirmation


def test_medley_does_not_merge_two_works_or_choose_primary():
    medley=rec(1,work='w1',contexts=[context()])
    medley.details['relations'].append({'target-type':'work','type':'performance','work':{'id':'w2','title':'另一首'},'attributes':['medley']})
    songs=group_recordings(ARTIST,[medley,rec(2,work='w1'),rec(3,work='w2')],{})
    assert len(songs)==3
    multi=next(s for s in songs if len(s.work_ids)>1)
    assert multi.pending_confirmation and multi.primary_recording_mbid is None


def test_collaborations_share_work_but_fallback_needs_compatible_performers():
    duet=rec(1,work='w1'); duet.credits.append(credit(OTHER_ID,'合作者'))
    solo=rec(2,work='w1')
    assert len(group_recordings(ARTIST,[duet,solo],{}))==1
    other=rec(3,artist=OTHER_ID,isrc='same')
    own=rec(4,isrc='same')
    assert len(group_recordings(ARTIST,[other,own],{}))==2


def test_unlabelled_recording_is_not_automatically_studio_primary():
    r=rec(1,work='w1')
    song=group_recordings(ARTIST,[r],{})[0]
    assert version_kind(r)[0]=='unknown' and song.primary_recording_mbid is None


def test_live_word_in_song_name_does_not_mean_live_version():
    assert version_kind(rec(1,'Live and Let Die'))[0]=='unknown'
    assert version_kind(rec(2,'Dragon Fist - Live'))[0]=='live'
    assert title_key('Dragon Fist - Live')==title_key('Dragon Fist')


def test_other_artist_same_work_is_not_assumed_to_be_target_artist():
    songs=group_recordings(ARTIST,[rec(1,work='w1'),rec(2,work='w1',artist=OTHER_ID)],{'w1':{'title':'龍拳'}})
    assert len(songs)==2 and sum(s.pending_confirmation for s in songs)==1


def test_full_official_medium_reissue_uses_sequence_duration_and_artist():
    anchors=[]; reissue=[]; works={}
    for n,title in enumerate(('第一首','第二首','第三首'),1):
        c1=context(group='album',position=n,release='album',count=3); c1['track_title']=title
        c2=context(group='box',position=n,release='box',count=3); c2['track_title']=title
        anchors.append(rec(n,title,work=f'w{n}',contexts=[c1])); works[f'w{n}']={'title':title}
        reissue.append(rec(n+10,title,contexts=[c2]))
    songs=group_recordings(ARTIST,anchors+reissue,works)
    assert len(songs)==3 and all(len(s.recordings)==2 for s in songs)
    reissue[0].length_ms+=30000
    assert len(group_recordings(ARTIST,anchors+reissue,works))==6
