from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class IPAssetInformationDTO:
    ip: str
    domain_names: list[str] = field(default_factory=list)
    subnets: list[str] = field(default_factory=list)
    contacts: list[str] = field(default_factory=list)
    missions: list[str] = field(default_factory=list)
    nodes: list[dict] = field(default_factory=list)

    @property
    def critical(self) -> int:
        return 1 if self.missions else 0

    def serialize(self) -> dict[Any, Any]:
        information = asdict(self)
        information["critical"] = self.critical
        return information
