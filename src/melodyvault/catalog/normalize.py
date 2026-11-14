"""Display/matching normalization only. Recording identity is always its MBID."""
from functools import lru_cache
import re
import unicodedata

from opencc import OpenCC


@lru_cache(maxsize=4)
def _converter(mode: str) -> OpenCC:
    return OpenCC(mode)


def display_name(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", _converter("t2s").convert(text)).strip()


def name_key(text: str) -> str:
    return display_name(text).casefold()


def normalized_isrc(value: str) -> str | None:
    code=re.sub(r'[-\s]','',str(value)).upper()
    return code if re.fullmatch(r'[A-Z]{2}[A-Z0-9]{3}[0-9]{7}',code) else None


_VERSION = re.compile(r"(?i)\b(live|remix|mix|studio|acoustic|instrumental|demo|karaoke|edit|version)\b|现场|現場|录音室|錄音室|混音|伴奏|演唱会|演唱會")


def base_title(text: str) -> str:
    """Remove explicit bracketed version qualifiers, never arbitrary subtitles."""
    text = display_name(text)
    text = re.sub(r"\s*[（(\[]([^()（）\[\]]*)[）)\]]", lambda m: "" if _VERSION.search(m[1]) else m[0], text).strip()
    return re.sub(r"\s+[-–—]\s+(.+)$", lambda m: "" if _VERSION.search(m[1]) else m[0], text).strip()


def title_key(text: str) -> str:
    """Candidate key only; matching keys are NEVER sufficient merge evidence."""
    text = unicodedata.normalize("NFKD", base_title(text).casefold())
    return "".join(c for c in text if not unicodedata.category(c).startswith(("P", "Z", "M")) and not c.isspace())


def search_names(text: str) -> tuple[str, ...]:
    simplified = display_name(text)
    traditional = _converter("s2t").convert(simplified)
    return tuple(dict.fromkeys((simplified, traditional)))
