"""Compiled providers only. Metadata is data, never executable discovery plugins."""
from typing import Protocol, runtime_checkable
from melodyvault.sources.models import SourceQuery,Candidate


@runtime_checkable
class SourceProvider(Protocol):
    name: str
    enabled: bool
    policy_url: str
    def search(self,query:SourceQuery,http)->list[Candidate]: ...
    def get_metadata(self,external_id:str,http)->list[Candidate]: ...
