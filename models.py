"""Small, explicit data contracts shared by the UI and deterministic engine."""
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Intent(StrEnum):
    UNSPECIFIED = "Not specified"
    APPLICATION = "Application-only"
    LOCAL = "Host-local"
    EXTERNAL = "External access intended"


@dataclass(frozen=True)
class Port:
    service_name: str
    target_port: int
    published_port: int | None
    host_ip: str | None
    protocol: str
    source_path: str
    source_line: int | None
    index: int
    binding: str  # wildcard, loopback, or non-loopback
    resolution_status: str = "resolved"

    @property
    def description(self) -> str:
        host = self.host_ip or "unspecified host address"
        published = self.published_port or "automatic host port"
        return f"{host} / {published} → {self.target_port}/{self.protocol}"


@dataclass(frozen=True)
class Unresolved:
    field: str
    reason: str
    line: int | None = None


@dataclass
class Service:
    name: str
    alias: str
    ports: list[Port] = field(default_factory=list)
    unresolved: list[Unresolved] = field(default_factory=list)
    networks: set[str] = field(default_factory=set)


@dataclass
class ComposeDocument:
    data: dict[str, Any]
    services: dict[str, Service]


@dataclass(frozen=True)
class Finding:
    rule_id: str
    service_name: str
    title: str
    category: str
    intended_access: str
    observed_configuration: str
    evidence_path: str
    line_number: int | None
    explanation: str
    assumptions: tuple[str, ...]
    unknowns: tuple[str, ...]
    suggested_action: str
    correction_available: bool = False
    port_index: int | None = None


@dataclass
class Analysis:
    findings: list[Finding]
    consistent_services: list[str]


@dataclass
class Candidate:
    text: str
    document: ComposeDocument
    analysis: Analysis
    affected_services: list[str]
    removed_findings: int


LIMITS = (
    "Host firewalls, external routing, authentication, and actual listening processes were not inspected.",
    "No containers were executed and no connectivity or application-function tests were performed.",
    "Only this file was analyzed; override files and deployment environment settings are not merged.",
)
