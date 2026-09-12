from enum import StrEnum


class PageQuality(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"


class Stage(StrEnum):
    discover = "discover"
    fetch = "fetch"
    extract = "extract"
    summarize = "summarize"
    curate = "curate"
    categorize = "categorize"
    compose = "compose"
    validate = "validate"
    write = "write"
