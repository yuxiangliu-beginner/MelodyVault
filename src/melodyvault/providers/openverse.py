"""Openverse is a discovery index; only the underlying source can authorize a file."""
from urllib.parse import urlsplit, quote
from melodyvault.catalog.models import CatalogError
from melodyvault.sources.models import Candidate
from melodyvault.sources.matching import version_from_text


class OpenverseProvider:
    name = 'openverse'
    enabled = True
    policy_url = 'https://docs.openverse.org/api/guides/quickstart.html'

    @staticmethod
    def _candidate(item):
        identifier = str(item.get('id') or '')
        link = str(item.get('foreign_landing_url') or '')
        try:
            parsed = urlsplit(link)
            valid = parsed.scheme == 'https' and parsed.hostname and not parsed.username and parsed.port in (None, 443)
        except ValueError:
            valid = False
        if not identifier or not valid:
            return None
        title = str(item.get('title') or '')[:500]
        duration = item.get('duration')
        # Openverse documents audio duration in milliseconds.
        try:
            duration = float(duration) / 1000 if duration is not None else None
        except (TypeError, ValueError):
            duration = None
        c = Candidate('openverse', identifier, title, str(item.get('creator') or '')[:300], link,
                      duration, version=version_from_text(title),
                      license_url=str(item.get('license_url') or ''),
                      license_reason='Openverse 是聚合索引；须在原始来源核验具体完整文件、权利链及下载条件',
                      evidence={'index_url':'https://openverse.org/audio/'+quote(identifier, safe=''),
                                'original_provider':str(item.get('source') or item.get('provider') or ''),
                                'policy_url':OpenverseProvider.policy_url,
                                'preview_not_full_file':True})
        c.file_format = str(item.get('filetype') or '')[:20]
        return c

    def search(self, query, http):
        # Title-only fallback retains leads without claiming they are the same recording.
        terms = list(dict.fromkeys(' '.join(pair).strip() for pair in query.keyword_pairs))
        terms += [query.title] if query.title not in terms else []
        found = {}
        for term in terms[:4]:
            data = http.json('https://api.openverse.org/v1/audio/', {'q':term, 'page_size':20})
            items = data.get('results')
            if not isinstance(items, list):
                raise CatalogError('Openverse 搜索响应不完整')
            for item in items:
                if not isinstance(item, dict):
                    continue
                candidate = self._candidate(item)
                if candidate:
                    found[candidate.external_id] = candidate
            if found:
                break
        return list(found.values())

    def get_metadata(self, external_id, http):
        data = http.json('https://api.openverse.org/v1/audio/'+quote(str(external_id), safe='')+'/')
        candidate = self._candidate(data)
        return [candidate] if candidate else []
