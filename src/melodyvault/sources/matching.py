"""Display-only matching. A score is never authorization or recording identity."""
from difflib import SequenceMatcher
import re
from melodyvault.catalog.normalize import title_key,name_key


def version_from_text(text):
    for kind,pattern in [('live',r'\blive\b|现场|現場|演唱会|演唱會'),('karaoke',r'karaoke|伴奏|卡拉'),
                         ('instrumental',r'instrumental|纯音乐|純音樂|钢琴|鋼琴|piano(?:\s|[-_])+(?:cover|version|collection|\d)'),('cover',r'\bcover\b|翻唱'),
                         ('remix',r'remix|混音'),('rerecording',r're-record|重录|重錄')]:
        if re.search(pattern,text,re.I):return kind
    return 'unknown'


def match_candidate(query,candidate):
    exact=title_key(candidate.title) in {title_key(t) for t in query.titles}
    artist_match=name_key(candidate.performer) in {name_key(a) for a in query.artist_names} if candidate.performer else False
    similarity=max((SequenceMatcher(None,title_key(candidate.title),title_key(t)).ratio() for t in query.titles),default=0)
    reasons=['标题/官方别名一致' if exact else f'标题相似度 {similarity:.2f}（仅线索）',
             '演唱者名称一致，身份仍需核对' if artist_match else '演唱者缺失或不一致，不认定原唱']
    kind=candidate.version if candidate.version!='unknown' else version_from_text(candidate.title)
    candidate.version=kind
    mismatch=(kind in {'cover','karaoke','instrumental'} and kind not in query.versions) or (kind not in {'unknown','studio'} and 'studio' in query.versions and kind!='studio')
    candidate.match_status='VERSION_MISMATCH' if mismatch else 'METADATA_MATCH' if exact and artist_match else 'REVIEW_REQUIRED'
    if mismatch:reasons.append('版本与目标不兼容，不能当作原曲')
    if candidate.duration_seconds and query.lengths_ms:
        gap=min(abs(candidate.duration_seconds-float(v)/1000) for v in query.lengths_ms)
        reasons.append(f'最小时长差 {gap:.1f} 秒（不能证明录音身份）')
    candidate.match_score=min(95,round(similarity*50)+(35 if artist_match else 0)+(5 if exact else 0)) if not mismatch else 0
    candidate.match_reasons=reasons+['元数据匹配不等于确认原唱/同一录音，也不构成授权证据']
    return candidate
