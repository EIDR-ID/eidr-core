"""Portfolio secrets loader (register Phase 3 item 7; OVERLAPS row 12).

One implementation of the local-file / AWS-Secrets-Manager loading skeleton
that eidr-dq, XML_to_JSON, and eidr-wikidata each carried a variant of.
Extraction unified the BEST behavior from each variant:

* AWS → local fallback with a VISIBLE stderr warning (from eidr-dq's
  2026-07 fix: a production AWS misconfiguration must never be silently
  masked, but must also not be fatal when a valid local file exists);
* trailing-comma tolerance in the local file (from eidr-wikidata's
  2026-07-14 fix: the file is hand-edited and a trailing comma broke every
  pipeline command — the regex strips only `,}` / `,]`, never valid JSON);
* broad truthiness for the local-mode flag (1/true/yes/on).

What deliberately stays OUT (per-program decisions, LOCAL tier):
* schema validation of the loaded dict — pass a ``validate`` callable;
* section normalization (e.g. eidr-wikidata's legacy-registry flattening);
* the env-var names themselves — each consumer passes its historical names
  so operator environments keep working unchanged.

Consumers (each a thin wrapper passing its env names + validator):
  eidr-dq        src/dq/secrets_loader.py
  XML_to_JSON    secrets_loader.py
  eidr-wikidata  src/eidr_wikidata/secrets.py
EIDR MCP's copy is NOT ported (standing decision: MCP is only touched when
it independently needs a major update; its loader is noted in OVERLAPS).

boto3 is imported lazily — consumers that only ever load locally don't
need it installed (pyproject extra: ``eidr-core[aws]``).
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Sequence


class SecretsError(RuntimeError):
    pass


def _truthy(val: str | None) -> bool:
    return str(val or "").strip().lower() in ("1", "true", "yes", "on")


def _first_env(names: Sequence[str], default: str | None = None) -> str | None:
    for n in names:
        v = os.getenv(n)
        if v:
            return v
    return default


def load_local(path: str | os.PathLike) -> dict:
    """Load a local secrets JSON file, tolerating trailing commas."""
    p = Path(path)
    if not p.exists():
        raise SecretsError(f"Secrets file not found: {p.resolve()}")
    raw = p.read_text(encoding="utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        try:
            return json.loads(re.sub(r",(\s*[}\]])", r"\1", raw))
        except json.JSONDecodeError as exc:
            raise SecretsError(
                f"Secrets file is not valid JSON: {p}: {exc}") from exc


def load_aws(secret_name: str, region: str,
             profile: str | None = None) -> dict:
    """Fetch and parse a secret from AWS Secrets Manager."""
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except Exception as exc:                       # boto3 not installed
        raise SecretsError(
            "boto3 is required to load secrets from AWS "
            "(pip install eidr-core[aws]).") from exc
    try:
        session = (boto3.Session(profile_name=profile) if profile
                   else boto3.Session())
        client = session.client("secretsmanager", region_name=region)
        resp = client.get_secret_value(SecretId=secret_name)
        raw = resp.get("SecretString")
        if not raw and "SecretBinary" in resp:
            raw = resp["SecretBinary"].decode("utf-8")
        if not raw:
            raise SecretsError("AWS secret returned empty payload.")
        return json.loads(raw)
    except (BotoCoreError, ClientError) as exc:
        raise SecretsError(f"AWS Secrets Manager error: {exc}") from exc


def load_secrets(
    path: str | os.PathLike | None = None,
    *,
    default_secret_name: str,
    secret_name_envs: Sequence[str] = ("AWS_SECRET_ID",),
    region_envs: Sequence[str] = ("AWS_REGION",),
    default_region: str = "us-west-2",
    profile_envs: Sequence[str] = ("AWS_PROFILE",),
    default_profile: str | None = None,
    local_flag_envs: Sequence[str] = ("USE_LOCAL_SECRETS",),
    local_path_envs: Sequence[str] = ("SECRETS_PATH",),
    default_local_path: str = ".secrets.json",
    aws_fallback_to_local: bool = True,
    validate: Callable[[dict], Any] | None = None,
) -> dict:
    """Load secrets with the portfolio resolution order:

    1. explicit ``path`` argument (local file);
    2. local file when any of ``local_flag_envs`` is truthy
       (path from the first set env in ``local_path_envs``, else
       ``default_local_path``);
    3. AWS Secrets Manager (name from ``secret_name_envs`` /
       ``default_secret_name``); on ANY AWS failure, fall back to the
       local file if it exists (``aws_fallback_to_local``) with a visible
       stderr warning — otherwise raise.

    ``validate`` (if given) is called with the loaded dict before return
    and may mutate it (e.g. to inject defaults); raise SecretsError (or
    anything) from it to reject.
    """
    local_path = _first_env(local_path_envs, default_local_path)
    if path is not None:
        cfg = load_local(path)
    elif any(_truthy(os.getenv(e)) for e in local_flag_envs):
        if not Path(local_path).exists():
            raise SecretsError(
                f"{'/'.join(local_flag_envs)} is set but secrets file "
                f"not found: {local_path}")
        cfg = load_local(local_path)
    else:
        try:
            cfg = load_aws(
                _first_env(secret_name_envs, default_secret_name),
                _first_env(region_envs, default_region),
                _first_env(profile_envs, default_profile))
        except Exception as aws_err:
            if aws_fallback_to_local and Path(local_path).exists():
                print(f"[secrets WARNING] AWS secrets unavailable "
                      f"({aws_err}); falling back to local secrets file: "
                      f"{local_path}", file=sys.stderr)
                cfg = load_local(local_path)
            else:
                raise SecretsError(
                    f"AWS secrets unavailable ({aws_err}) and no local "
                    f"secrets file found at {local_path}. Set "
                    f"{local_flag_envs[0]}=1 with a valid "
                    f"{local_path_envs[0]}, or fix the AWS "
                    f"configuration.") from aws_err

    if validate is not None:
        validate(cfg)
    return cfg
