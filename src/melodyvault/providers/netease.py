"""NetEase search capability boundary pending a verified authorized API.

SuiSound's GD integration is a third-party aggregator; its search results and
stream URLs do not establish rights to access or download individual tracks.
This placeholder does not call that service or undocumented NetEase endpoints.
"""
from dataclasses import dataclass


class NeteaseUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class NeteaseSearchRequest:
    artist: str = ''
    title: str = ''
    album: str = ''
    song_id: str = ''


class NeteaseMusicSearchProvider:
    provider_id = 'netease'
    provider_name = '网易云音乐'
    provider_type = 'MUSIC_PLATFORM'
    is_enabled = False

    def get_status(self):
        return {'status': 'RESTRICTED', 'reason': '尚未核实适用于本应用的搜索接口及下载使用条件；SuiSound 的 GD 聚合接口不证明网易授权。'}

    def get_capabilities(self):
        return {'search': False, 'download': False, 'reason': self.get_status()['reason']}

    def search(self, query: NeteaseSearchRequest):
        if not any((query.artist.strip(), query.title.strip(), query.album.strip(), query.song_id.strip())):
            raise ValueError('请输入歌手、歌曲、专辑或歌曲 ID')
        raise NeteaseUnavailable(self.get_status()['reason'])
