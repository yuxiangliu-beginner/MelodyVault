"""Small deterministic OFFLINE test fixtures; never used by application code."""
from copy import deepcopy
import time
import httpx

ARTIST_ID = "a223958d-5c56-4b2c-a30a-87e357bc121b"
OTHER_ID = "10000000-0000-4000-8000-000000000099"


def credit(mbid=ARTIST_ID, name="周杰倫"):
    return {"name": name, "joinphrase": "", "artist": {"id": mbid, "name": name}}


def recording(number, title="晴天", **extra):
    return {"id": f"10000000-0000-4000-8000-{number:012d}", "title": title,
            "length": 200000, "video": False, "artist-credit": [credit()], **extra}


def fixture_data():
    artist = {"id": ARTIST_ID, "name": "周杰倫", "country": "TW", "type": "Person",
              "aliases": [{"name": "周杰伦"}, {"name": "Jay Chou"}], "life-span": {"begin": "1979-01-18"}}
    songs = [recording(1), recording(2, disambiguation="live"), recording(3, "MV", video=True),
             recording(4, "千里之外", **{"artist-credit": [credit(), credit(OTHER_ID, "合作者")]}),
             recording(5, "髮如雪")]
    groups = [{"id": f"20000000-0000-4000-8000-{i:012d}", "title": f"offline group {i}", "primary-type": kind}
              for i, kind in enumerate(("Album", "Single", "EP"), 1)]

    def release(number, group, recordings):
        return {"id": f"30000000-0000-4000-8000-{number:012d}", "title": "offline release",
                "status": "Official", "release-group": group, "artist-credit": [credit()],
                "media": [{"position": 1, "track-count": len(recordings), "tracks": [
                    {"id": f"40000000-0000-4000-{number:04d}-{i:012d}", "position": i,
                     "title": song["title"], "artist-credit": song["artist-credit"], "recording": song}
                    for i, song in enumerate(recordings, 1)]}]}

    wrong = recording(9, "其他歌手的曲目", **{"artist-credit": [credit(OTHER_ID, "别人")]})
    releases = [release(1, groups[0], [songs[0], songs[3], wrong]),
                release(2, groups[1], [deepcopy(songs[0]), songs[4]]),
                release(3, groups[2], [songs[3], wrong])]
    return artist, songs, groups, releases


class CatalogTransport:
    def __init__(self, delay=0.0):
        self.calls = []
        self.delay = delay
        self.fail_recording_page = False
        self.fail_all = False
        self.ambiguous = False
        self.repeated_page = False
        self.artist, self.songs, self.groups, self.releases = fixture_data()
        self.works = [{'id': f'50000000-0000-4000-8000-{i:012d}', 'title': title, 'aliases': []}
                      for i,title in enumerate(('晴天','千里之外','髮如雪'),1)]

    def with_work(self, data):
        data = deepcopy(data)
        number = int(data['id'].split('-')[-1])
        work = self.works[0 if number in (1,2) else 1 if number == 4 else 2]
        data['relations'] = [{'target-type':'work','type':'performance','work':work,
                              'attributes':['live'] if number == 2 else []}]
        return data

    def __call__(self, request):
        endpoint = request.url.path.removeprefix("/ws/2/")
        params = dict(request.url.params)
        offset = int(params.get("offset", 0))
        self.calls.append((endpoint, params))
        assert request.headers["User-Agent"].startswith("MelodyVault/")
        if self.delay:
            time.sleep(self.delay)
        if self.fail_all or (self.fail_recording_page and endpoint == 'recording' and offset > 0):
            return httpx.Response(503, json={"error": "offline fixture busy"}, headers={"Retry-After": "0"})
        if endpoint == "artist":
            artists = [self.artist]
            if self.ambiguous:
                artists.append({**self.artist, "id": OTHER_ID})
            data = {"artists": artists, "count": len(artists), "offset": 0}
        elif endpoint == f"artist/{ARTIST_ID}":
            data = self.artist
        elif endpoint == "recording":
            items = self.songs[:2] if offset == 0 or self.repeated_page else self.songs[2:3]
            if 'work-rels' in params.get('inc',''):
                items = [self.with_work(item) for item in items]
            data = {"recordings": items, "recording-count": 3, "recording-offset": offset}
        elif endpoint.startswith('recording/'):
            data = self.with_work(next(song for song in self.songs if song['id'] == endpoint.split('/')[1]))
        elif endpoint == 'work':
            data = {'works':self.works,'work-count':3,'work-offset':offset}
        elif endpoint == "release-group":
            items = self.groups[:1] if offset == 0 else self.groups[1:]
            data = {"release-groups": items, "release-group-count": 3, "release-group-offset": offset}
        elif endpoint == "release" and "track_artist" in params:
            data = {"releases": self.releases[2:], "release-count": 1, "release-offset": offset}
        elif endpoint == "release":
            items = self.releases[:1] if offset == 0 else self.releases[1:2]
            data = {"releases": items, "release-count": 2, "release-offset": offset}
        else:
            raise AssertionError(f"Unexpected offline request: {request.url}")
        return httpx.Response(200, json=deepcopy(data))
