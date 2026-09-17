"""Structures de données du convertisseur MQ V5.3 -> V8.1."""

from __future__ import annotations

from dataclasses import dataclass, field


TYPE_TO_CATALOGUE_KEY = {
    "QMGR": "qmgr",
    "QLOCAL": "qlocal",
    "QMODEL": "qmodel",
    "QALIAS": "qalias",
    "QREMOTE": "qremote",
    "CHANNEL": "channel",
    "PROCESS": "process",
    "NAMELIST": "namelist",
}


@dataclass
class MQAttribute:
    """Un attribut MQSC : ATTR(valeur) ou un mot-clé booléen sans parenthèses."""

    name: str
    value: str
    is_flag: bool = False
    line: int = 0


@dataclass
class MQObject:
    """Un objet MQ tel que rendu par un bloc DISPLAY ... ALL."""

    obj_type: str  # QMGR, QLOCAL, QMODEL, QALIAS, QREMOTE, CHANNEL, PROCESS, NAMELIST
    name: str
    attributes: dict[str, MQAttribute] = field(default_factory=dict)
    chltype: str | None = None  # uniquement pour obj_type == CHANNEL
    source_line: int = 0

    def is_system(self) -> bool:
        return self.name.upper().startswith("SYSTEM.")

    def get(self, attr_name: str) -> str | None:
        attr = self.attributes.get(attr_name.upper())
        return attr.value if attr else None


@dataclass
class ParseIssue:
    """Une ligne, un fragment ou un message que le parseur n'a pas su/voulu interpréter."""

    kind: str  # "error_message" | "unparsed_fragment"
    line: int
    text: str


@dataclass
class ParseResult:
    objects: list[MQObject] = field(default_factory=list)
    issues: list[ParseIssue] = field(default_factory=list)
    source_qmgr: str | None = None


@dataclass
class ConversionNote:
    """Une entrée du rapport de conversion."""

    category: str  # "removed" | "renamed" | "unknown_attr" | "ignored_object" | "review"
    obj_type: str
    obj_name: str
    detail: str


@dataclass
class ConversionResult:
    queues: list[MQObject] = field(default_factory=list)
    channels: list[MQObject] = field(default_factory=list)
    qmgr: MQObject | None = None
    processes: list[MQObject] = field(default_factory=list)
    namelists: list[MQObject] = field(default_factory=list)
    notes: list[ConversionNote] = field(default_factory=list)
    ignored_system_objects: list[MQObject] = field(default_factory=list)
