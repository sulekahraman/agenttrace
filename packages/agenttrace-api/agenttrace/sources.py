from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import httpx
from commsfail import Trace, load
from commsfail.sources.sharednet import SHARE_API, from_share, now
from pydantic import BaseModel, ConfigDict, Field

MAX_SOURCE_BYTES = 5_000_000


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["sharednet_share", "share_json", "local"]
    value: str | dict = Field(description="Share URL, share JSON object, or allowlisted local path.")


def validate_share_url(value: str) -> str:
    url = urlsplit(value)
    if (
        url.scheme != "https"
        or url.netloc not in ("sharednet.ai", "www.sharednet.ai")
        or url.username
        or url.password
        or url.query
        or not re.fullmatch(r"/s/shr_[A-Za-z0-9_-]+/?", url.path)
    ):
        raise ValueError("Enter a public HTTPS sharednet.ai/s/shr_... link.")
    return url.path.rstrip("/").split("/")[-1]


def load_source(source: Source, source_root: Path | None = None) -> Trace:
    if source.type == "share_json":
        if not isinstance(source.value, dict):
            raise ValueError("share_json requires a JSON object.")
        if len(json.dumps(source.value).encode()) > MAX_SOURCE_BYTES:
            raise ValueError("The trace exceeds the 5 MB source limit.")
        return parse_share(source.value, {"kind": "share-file", "loaded_at": now()})

    if not isinstance(source.value, str):
        raise ValueError(f"{source.type} requires a string.")
    if source.type == "local":
        if source_root is None:
            raise ValueError("Local sources are disabled. Set AGENTTRACE_SOURCE_ROOT to allow a data directory.")
        root = source_root.resolve()
        path = (root / source.value).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Local source must be inside AGENTTRACE_SOURCE_ROOT.")
        # A symlink nested in a goal-run directory could escape the allowlist.
        paths = path.rglob("*") if path.is_dir() else [path]
        for item in paths:
            if not item.resolve().is_relative_to(root):
                raise ValueError("Local source contains a symlink outside AGENTTRACE_SOURCE_ROOT.")
        return load(str(path))

    token = validate_share_url(source.value)
    try:
        with httpx.Client(timeout=15, follow_redirects=False) as client:
            with client.stream("GET", SHARE_API.format(token=token)) as response:
                if response.status_code != 200:
                    raise ValueError(f"SharedNet returned HTTP {response.status_code}.")
                chunks = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_SOURCE_BYTES:
                        raise ValueError("The trace exceeds the 5 MB source limit.")
                    chunks.append(chunk)
    except httpx.HTTPError as error:
        raise ValueError(f"Could not load SharedNet: {error}") from error
    data = json.loads(b"".join(chunks))
    return parse_share(
        data,
        {"kind": "share", "token": token[:8] + "...", "url": source.value, "loaded_at": now()},
    )


def parse_share(data: dict, source: dict) -> Trace:
    if not isinstance(data, dict) or not isinstance(data.get("messages"), list):
        raise ValueError("A SharedNet share must contain a messages array.")
    if not isinstance(data.get("room", {}), dict) or not isinstance(data.get("members", []), list):
        raise ValueError("Invalid SharedNet room or members.")
    if data.get("room", {}).get("name") is not None and not isinstance(data["room"]["name"], str):
        raise ValueError("SharedNet room name must be a string.")
    for member in data.get("members", []):
        if (
            not isinstance(member, dict)
            or not isinstance(member.get("handle"), str)
            or any(member.get(field) is not None and not isinstance(member[field], str)
                   for field in ("label", "driver"))
        ):
            raise ValueError("SharedNet members must have string handles, labels and drivers.")
    for message in data["messages"]:
        if (
            not isinstance(message, dict)
            or type(message.get("sequence")) is not int
            or message["sequence"] <= 0
            or not isinstance(message.get("content", ""), str)
            or not isinstance(message.get("sender", {}), dict)
        ):
            raise ValueError("Invalid SharedNet message: sequence, content, or sender.")
        if (
            message.get("created_at") is not None and not isinstance(message["created_at"], str)
            or message.get("sender", {}).get("handle") is not None
            and not isinstance(message["sender"]["handle"], str)
        ):
            raise ValueError("SharedNet message timestamps and sender handles must be strings.")
    return from_share(data, source)
