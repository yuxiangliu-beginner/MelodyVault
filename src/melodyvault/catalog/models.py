"""UI-independent domain values. Raw MusicBrainz titles/credits remain available."""
from dataclasses import dataclass, field
from typing import Any

from melodyvault.catalog.normalize import display_name, name_key


@dataclass(frozen=True)
class Artist:
    mbid: str
    name: str
    aliases: tuple[str, ...] = ()
    country: str = ""
    disambiguation: str = ""
    begin: str = ""
    kind: str = ""
    payload: dict[str, Any] = field(default_factory=dict, compare=False)

    @classmethod
    def from_payload(cls, data: dict) -> "Artist":
        return cls(data["id"], data["name"],
                   tuple(a["name"] for a in data.get("aliases", []) if a.get("name")),
                   data.get("country") or "", data.get("disambiguation") or "",
                   (data.get("life-span") or {}).get("begin") or "",
                   data.get("type") or "", data)

    def matches(self, query: str) -> bool:
        return name_key(query) in {name_key(text) for text in (self.name, *self.aliases)}

    @property
    def label(self) -> str:
        details = " · ".join(value for value in (self.country, self.begin, self.disambiguation) if value)
        return f"{display_name(self.name)} · {details}\n{self.mbid}"


def credit_ids(credits: list) -> set[str]:
    return {c["artist"]["id"] for c in credits if isinstance(c, dict)
            and isinstance(c.get("artist"), dict) and c["artist"].get("id")}


@dataclass
class Recording:
    mbid: str
    original_title: str
    title: str
    version: str
    length_ms: int | None
    credits: list
    official: bool
    origins: set[str]
    payload: dict
    details: dict = field(default_factory=dict)
    contexts: list[dict] = field(default_factory=list)
    identity_links: list[dict] = field(default_factory=list)

    @classmethod
    def from_payload(cls, data: dict, official: bool = False, origin: str = "") -> "Recording":
        return cls(data["id"], data["title"], display_name(data["title"]),
                   display_name(data.get("disambiguation") or ""), data.get("length"),
                   data.get("artist-credit") or [], official, {origin} if origin else set(), dict(data))

    def merge(self, other: "Recording") -> None:
        if self.mbid != other.mbid:
            raise ValueError("Different recording MBIDs cannot be merged")
        self.official = self.official or other.official
        self.origins.update(other.origins)
        if self.length_ms is None:
            self.length_ms = other.length_ms
        if not self.version:
            self.version = other.version
        if not self.credits:
            self.credits = other.credits
        for key, value in other.payload.items():
            if not self.payload.get(key) and value is not None:
                self.payload[key] = value

    @property
    def display_title(self) -> str:
        title=display_name(self.details.get('title',self.title))
        version=display_name((self.details or self.payload).get('disambiguation',self.version) or '')
        if version and name_key(version) not in name_key(title):
            return f"{title}（{version}）"
        return title


@dataclass
class Song:
    id: str
    title: str
    recordings: list[Recording]
    work_ids: tuple[str, ...]
    pending_confirmation: bool
    evidence: list[dict]
    primary_recording_mbid: str | None = None
    primary_reason: str = "没有足够证据选择正式录音室主版本"
    reviewed: bool = False
    review_action: str = ""


@dataclass(frozen=True)
class Progress:
    stage: str
    processed: int
    total: int | None
    message: str
    artist: Artist | None = None


@dataclass
class CatalogResult:
    artist: Artist
    songs: list[Song]
    summary: dict
    recordings: list[Recording] = field(default_factory=list)


class CatalogCancelled(Exception):
    pass


class CatalogError(Exception):
    pass


class ArtistChoiceRequired(CatalogError):
    def __init__(self, candidates: list[Artist]):
        super().__init__("存在同名或近似歌手，请核对地区、出生日期和 MusicBrainz ID 后选择。")
        self.candidates = candidates
