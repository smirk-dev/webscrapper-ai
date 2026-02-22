"""Collector registry — discover, register, and run collectors."""

from src.collectors.base import BaseCollector, ClassifiedEvent

# Registry of all available collectors
_COLLECTORS: dict[str, type[BaseCollector]] = {}


def register(name: str):
    """Decorator to register a collector class by name."""

    def wrapper(cls: type[BaseCollector]):
        _COLLECTORS[name] = cls
        return cls

    return wrapper


def get_collector(name: str) -> type[BaseCollector]:
    """Get a registered collector class by name."""
    if name not in _COLLECTORS:
        available = ", ".join(sorted(_COLLECTORS.keys()))
        raise KeyError(f"Unknown collector '{name}'. Available: {available}")
    return _COLLECTORS[name]


def list_collectors() -> list[str]:
    """List all registered collector names."""
    return sorted(_COLLECTORS.keys())


async def run_collector(name: str) -> list[ClassifiedEvent]:
    """Instantiate and run a collector by name."""
    collector_cls = get_collector(name)
    collector = collector_cls()
    raw_events = await collector.collect()
    # Classification happens in a separate step (LLM layer)
    return raw_events
