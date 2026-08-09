"""
THE portfolio factory for the EIDR Python SDK ``Client``.

Extracted verbatim from eidr-wikidata ``eidr/registry_client.py``
(2026-08-05, register Phase 3 item 5 / R5; original authored 2026-05-12 and
production-proven by the Alt ID registry remediation). Portfolio policy: ALL
registry API interaction goes through the Python SDK, and every SDK client is
constructed HERE — one place for credentials precedence, registry-target
selection (sandbox2 default; production is an explicit operator choice), the
superparty write gate, and one import path to audit when reviewing
registry-write changes. Consumers: eidr-wikidata (via its shim), eidr-dq's
``registry_sync_verify`` (adoption pending, its thread's call), future
Shim-mode services. EIDR MCP stays exempt until the SDK grows mirror-ingest
surfaces.

Why this module exists (original rationale)
-------------------------------------------
The originating project has two distinct EIDR-data paths:

  * **Read path (Phase 2 / Phase 4 augment).** Sources EIDR records from
    the local PostgreSQL mirror via ``eidr/mirror_client.py``. The
    mirror is ~6.5 h faster per BMR run than the live registry API
    and stays as the canonical read path for the foreseeable future.
  * **Live-registry path (Phase 4+ writes, Phase 5 propagate).** Any
    operation that needs to MODIFY EIDR records — BMR Match/Merge,
    Alt-ID propagation, future record registration — must go through
    the live registry API. The official EIDR Python SDK is the
    canonical client for those operations.

Pre-2026-05-12 the project had no live-registry code at all. This
module is the forward-looking entry point: when a new caller needs to
hit the registry it imports ``get_registry_client`` from here rather
than constructing an ``eidr.Client`` directly. That gives us:

  * one place to set credentials precedence (project ``.secrets.json``
    or SDK auto-detect);
  * one place to pick the registry target (sandbox vs production);
  * one place to opt into / out of the SDK's superparty write gate;
  * a single import path the operator can audit when reviewing
    registry-write changes.

Today the module is not wired into any production call site — there
ARE no production call sites. It's the scaffold Phase 4 / 5 / 6 work
will plug into. Keeping the wrapper tiny means we don't lock in a
schema before we know what the write phases need.

Usage (Phase 4+ pattern)
------------------------
::

    from eidr_core.registry import get_registry_client, token_operation_status

    with get_registry_client() as client:
        record = client.resolve("10.5240/...")
        token = client.modify(record, immediate=False)

        # Do NOT trust token.operation_result() alone to tell you the write
        # succeeded: as of SDK v1.1.1 a REJECTED write still reports as
        # pending, because the rejection lives in an inner OperationStatus
        # the SDK does not surface. Ask for the registry's actual verdict.
        # See operation_status.py — that gap cost 62 production records.
        status = token_operation_status(token)
        if status is None:
            ...   # no verdict yet — poll again later, do not assume success
        elif status.is_failure:
            log.error("registry rejected %s: %s", token.value, status)

Or with explicit credentials lifted from the project's secrets:

::

    from eidr_wikidata.secrets import load_secrets
    from eidr_core.registry import (
        build_registry_credentials, get_registry_client,
    )

    secrets = load_secrets()
    creds = build_registry_credentials(secrets)
    with get_registry_client(credentials=creds) as client:
        ...

Why a lazy import
-----------------
``eidr.Client`` requires the SDK's ``[client]`` extra (``httpx``).
Codec-only test paths and the existing mirror-DB pipeline don't need
that import — so the module imports ``eidr`` inside the factory
rather than at module load. Callers that only need the mirror DB
never pay for the SDK import or the httpx transport.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

# Re-exported so callers get the factory and the verdict reader from one
# import. Stdlib-only, so this costs nothing to consumers that never write
# — unlike the SDK itself, which stays lazily imported below.
from .operation_status import (
    CODE_SUCCESS,
    OperationStatus,
    parse_operation_status,
    parse_operation_statuses,
    token_operation_status,
)

__all__ = [
    "CODE_SUCCESS",
    "DEFAULT_REGISTRY",
    "OperationStatus",
    "build_registry_credentials",
    "get_registry_client",
    "parse_operation_status",
    "parse_operation_statuses",
    "token_operation_status",
]

if TYPE_CHECKING:
    # Type-check-only imports so static analysis sees the SDK types
    # without forcing the runtime import on mirror-DB-only callers.
    from eidr import Client as _SDKClient
    from eidr import Credentials as _SDKCredentials


log = logging.getLogger(__name__)


# Default registry target. Sandbox2 mirrors the production schema
# but is safe to write against — every Phase 4+ change starts there.
# Switch to ``"production"`` only after sandbox validation has signed
# off the operator. Production writes also require a live, party-id-
# bound credential — the project's ``.secrets.json`` must carry the
# write credentials at that point.
DEFAULT_REGISTRY = "sandbox2"


def build_registry_credentials(secrets: Optional[dict] = None) -> "_SDKCredentials":
    """
    Build SDK ``Credentials`` from the project's loaded secrets dict
    (the same shape ``load_secrets`` returns), falling back to the
    SDK's own auto-detection chain when no project-side section is
    present.

    Project secrets convention — the operator's actual ``.secrets.json``
    (added 2026-07-14; see ``sample.secrets.json``) uses a
    ``"registry"`` section with uppercase keys and no base URL (the
    registry endpoint is selected per-run from the SDK's named
    registries, never stored in secrets)::

        {
            "mirror_db": { ... },
            "registry": {
                "USER_ID":  "10.5238/...",
                "PARTY_ID": "10.5237/...",
                "PASSWORD": "..."
            }
        }

    The pre-2026-07-14 anticipated shape (``eidr_registry`` section,
    lowercase keys, optional ``base_url``) is still honoured for
    backward compatibility. Keys in either section are matched
    case-insensitively.

    Falls back to ``eidr.Credentials.load()`` (env vars / EIDR XML
    config / SDK JSON / AWS Secrets Manager) when neither section is
    present — useful for ad-hoc scripts that prefer the SDK's own
    auto-detect.

    Raises:
        ``ImportError`` if the ``eidr`` SDK is not installed.
        ``KeyError`` if a section is present but incomplete.
        ``EIDRCredentialsNotFoundError`` if no source can resolve.
    """
    from eidr import Credentials  # lazy

    if secrets is not None:
        section = secrets.get("registry") or secrets.get("eidr_registry")
        if not section:
            # Top-level fallback (2026-07-14): the operator's live
            # .secrets.json carries USER_ID / PARTY_ID / PASSWORD at
            # the top level rather than nested under a "registry"
            # section (the sample file shows the nested shape; both
            # are accepted).
            top = {str(k).lower(): v for k, v in secrets.items()}
            if {"user_id", "party_id", "password"} <= set(top):
                section = secrets
        if section:
            # Case-insensitive key access: the operator's file uses
            # USER_ID / PARTY_ID / PASSWORD; older docs used lowercase.
            lower = {str(k).lower(): v for k, v in section.items()}
            log.debug(
                "registry_client: building Credentials from the secrets "
                "registry section"
            )
            return Credentials(
                # .strip(): the file is hand-edited; a stray leading/
                # trailing space in any field yields an opaque
                # "authentication error" (code=4) from the registry.
                user_id=str(lower["user_id"]).strip(),
                party_id=str(lower["party_id"]).strip(),
                password=str(lower["password"]).strip(),
                base_url=(str(lower["base_url"]).strip()
                          if lower.get("base_url") else None),
            )

    log.debug(
        "registry_client: no registry section in secrets; falling back "
        "to eidr.Credentials.load()"
    )
    return Credentials.load()


def get_registry_client(
    *,
    registry: str = DEFAULT_REGISTRY,
    credentials: Optional["_SDKCredentials"] = None,
    secrets: Optional[dict] = None,
    transport_config: Optional[Any] = None,
    tracing: Optional[Any] = None,
    enforce_superparty_gate: bool = True,
) -> "_SDKClient":
    """
    Construct a configured SDK ``Client`` ready for context-manager use.

    Args:
        registry: SDK registry selector. ``"sandbox2"`` (default),
            ``"sandbox1"``, ``"production"``, or a custom URL. The
            SDK's ``registries`` module enumerates the known
            endpoints.
        credentials: Optional pre-built ``Credentials``. When None,
            built from ``secrets`` via ``build_registry_credentials``
            (which falls back to ``Credentials.load()`` if no
            project section is present).
        secrets: The project's loaded secrets dict (return value of
            ``load_secrets``). Only consulted when ``credentials`` is
            None.
        transport_config: Optional SDK ``TransportConfig`` for
            timeouts / retries / TLS verification. Sensible SDK
            defaults are usually fine.
        tracing: Optional SDK ``TraceSink`` (or ``True`` for the
            default file sink) to capture request / response
            diagnostics. Off by default.
        enforce_superparty_gate: Mirror the SDK default. Disable
            only when the caller has explicitly verified the
            party-write policy with the registry operator.

    Returns:
        A configured ``eidr.Client`` instance. Use it as a context
        manager — the SDK requires ``with`` for transport cleanup::

            with get_registry_client() as client:
                record = client.resolve(...)

    Raises:
        ``ImportError`` if the SDK is not installed with the
        ``[client]`` extra (httpx).
    """
    from eidr import Client, registries  # lazy

    if credentials is None:
        credentials = build_registry_credentials(secrets)

    # The SDK accepts the registry as either a Registry instance,
    # a short string name ("sandbox2"), or a base URL. Lower-case
    # the input for the short-name path so call sites can spell it
    # however they like.
    registry_target: Any = registry
    if isinstance(registry, str) and not registry.startswith(("http://", "https://")):
        registry_target = registry.lower()

    return Client(
        registry=registry_target,
        credentials=credentials,
        transport_config=transport_config,
        tracing=tracing,
        enforce_superparty_gate=enforce_superparty_gate,
    )
