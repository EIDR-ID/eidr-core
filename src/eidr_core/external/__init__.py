"""External data-source chassis (planned; not yet extracted).

Will hold: the shared access chassis for external sources — response
cache, rate limiter, retry/backoff, serialization helpers — plus, over
time, per-source clients as each gains a second consumer.

One-home-per-source rule until then: Wikidata client lives in
eidr-wikidata (``wikidata/api.py``, ``sparql.py`` with endpoint-fallback
chain); TMDb in eidr-dq (``external/``); IMDb in the planned rate-managed
library.

Chassis seed: eidr-dq ``external/cache.py`` (explicitly written for
extraction).
"""
