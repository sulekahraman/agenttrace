"""Batch analysis against a running localhost AgentTrace API."""
from __future__ import annotations

import argparse
from html import escape
import json
import math
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlencode, urlsplit

import httpx

from .models import now
from .communication import NAME as COMMUNICATION


def save_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.touch(mode=0o600)
    temporary.chmod(0o600)
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def local_server(value: str) -> str:
    url = urlsplit(value)
    if (url.scheme != "http" or url.hostname not in ("localhost", "127.0.0.1", "::1")
            or url.username or url.password or url.query or url.fragment or url.path not in ("", "/")):
        raise argparse.ArgumentTypeError("Server must be a localhost HTTP origin.")
    return value.rstrip("/")


def positive(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Value must be finite and positive.")
    return number


def request(client, method: str, path: str, **kwargs):
    response = client.request(method, path, **kwargs)
    if not response.is_success:
        raise httpx.HTTPStatusError(
            f"{method} {path}: HTTP {response.status_code}: {response.text}",
            request=response.request, response=response,
        )
    return response.json()


def run_batch(client, entries: list[dict], output: Path, server: str, *,
              scout: bool = False, model: str | None = None, rerun: bool = False,
              communication: bool = False,
              wait_timeout: float = 1800, poll_interval: float = 2) -> dict:
    result = {"schema": "agenttrace/batch.v1", "created_at": now(), "server": server,
              "scout_requested": scout, "traces": []}
    setup = None
    if communication:
        result["communication_requested"] = True
    if scout:
        try:
            setup = request(client, "GET", "/api/scout/setup",
                            params={"model": model} if model else {})
        except (httpx.HTTPError, ValueError) as error:
            setup = {"ready": False, "error": str(error), "model": model}
        result["scout_setup"] = setup

    def checkpoint():
        save_json(output / "index.json", result)

    for index, entry in enumerate(entries):
        item = {"name": entry.get("slug") or entry.get("name") or f"trace-{index + 1}",
                "analyses": []}
        result["traces"].append(item)
        folder = output / f"trace-{index + 1:03d}"
        try:
            identifier = entry.get("trace_id")
            if identifier:
                if not isinstance(identifier, str) or not re.fullmatch(r"trace_[a-f0-9]{16}", identifier):
                    raise ValueError("Invalid saved trace_id.")
                report = request(client, "GET", f"/api/traces/{identifier}")
            else:
                payload = {"source": entry["source"]} if "source" in entry else {"url": entry["url"]}
                report = request(client, "POST", "/api/traces", json=payload)
                identifier = report["traceId"]
            item.update(trace_id=identifier, room=report["conversation"]["title"],
                        url=f"{server}/?{urlencode({'trace': identifier})}", status="completed")
            previous = request(client, "GET", f"/api/traces/{identifier}/analyses")
            analyzers = [a for a in report["analyzers"] if a["kind"] == "offline"]
            if scout:
                analyzers.append({"name": "scout_collaboration_v1", "available": True})
            if communication:
                analyzers.append({"name": COMMUNICATION, "available": True})
            for analyzer in analyzers:
                name = analyzer["name"]
                pipeline = name in ("scout_collaboration_v1", COMMUNICATION)
                selected_setup = setup
                if name == COMMUNICATION:
                    selected_setup = request(client, "GET", "/api/communication/setup", params={
                        "trace_id": identifier, **({"model": model} if model else {}),
                    })
                record = {"analyzer": name}
                item["analyses"].append(record)
                if not analyzer["available"]:
                    record.update(status="unavailable", reason=analyzer["unavailable_reason"])
                    checkpoint()
                    continue
                selected_model = selected_setup.get("model") if pipeline else None
                different_model_active = next((
                    a for a in previous if pipeline
                    and a["analyzer"]["name"] == name and a["status"] in ("queued", "running")
                    and (a["provenance"].get("model") != selected_model or (
                        name == COMMUNICATION and a["provenance"].get("configuration_sha256")
                        != selected_setup["configuration_sha256"]
                    ))
                ), None)
                if different_model_active:
                    record.update(status="blocked", reason="Scout is already active with a different model." if name != COMMUNICATION else "Communication analysis is active with a different configuration.",
                                  run_id=different_model_active["id"])
                    item["status"] = "incomplete"
                    checkpoint()
                    continue
                compatible = [
                    a for a in previous if a["analyzer"]["name"] == name
                    and (not pipeline or a["provenance"].get("model") == selected_model)
                    and (name != COMMUNICATION or a["provenance"].get("configuration_sha256")
                         == selected_setup["configuration_sha256"])
                ]
                active = next((a for a in compatible if a["status"] in ("queued", "running")), None)
                completed = next((a for a in compatible if a["status"] == "completed"), None)
                analysis = active or (completed if not rerun else None)
                if analysis is None and pipeline and not selected_setup["ready"]:
                    record.update(status="blocked", setup=selected_setup)
                    item["status"] = "incomplete"
                    checkpoint()
                    continue
                try:
                    reused = analysis is not None
                    if analysis is None:
                        analysis = request(
                            client, "POST", f"/api/traces/{identifier}/analyses/{name}",
                            json={"model": selected_model} if selected_model else {},
                        )
                    record.update(
                        run_id=analysis["id"], status=analysis["status"], reused=reused,
                        url=f"{server}/?{urlencode({'trace': identifier, 'run': analysis['id']})}",
                    )
                    if pipeline and analysis["provenance"].get("model") != selected_model:
                        raise ValueError("Server returned a pipeline run for a different model; requested analysis was not started.")
                    if name == COMMUNICATION and analysis["provenance"].get("configuration_sha256") != selected_setup["configuration_sha256"]:
                        raise ValueError("Server returned a communication run for a different configuration.")
                    checkpoint()
                    deadline = time.monotonic() + wait_timeout
                    while analysis["status"] in ("queued", "running"):
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError("Wait timed out; server job may still be running. Rerun to resume polling.")
                        time.sleep(min(poll_interval, remaining))
                        analysis = request(client, "GET", f"/api/analysis-runs/{analysis['id']}")
                    filename = folder / f"analysis-{len(item['analyses']):02d}.json"
                    save_json(filename, analysis)
                    record.update(status=analysis["status"], error=analysis["error"],
                                  file=str(filename.relative_to(output)))
                    if analysis["status"] != "completed":
                        item["status"] = "incomplete"
                except (httpx.HTTPError, ValueError, TimeoutError) as error:
                    record.update(status="error", error=str(error))
                    item["status"] = "incomplete"
                checkpoint()
            report = request(client, "GET", f"/api/traces/{identifier}")
            save_json(folder / "report.json", report)
            item["report_file"] = str((folder / "report.json").relative_to(output))
        except (httpx.HTTPError, ValueError) as error:
            item.update(status="error", error=str(error))
        checkpoint()
        print(f"{item['name']}: {item['status']}", flush=True)
    result["completed_at"] = now()
    checkpoint()
    rows = []
    for item in result["traces"]:
        trace_link = (
            f'<a href="{escape(item["url"], quote=True)}">{escape(item["name"])}</a>'
            if "url" in item else escape(item["name"])
        )
        links = []
        for record in item["analyses"]:
            text = escape(f'{record["analyzer"]}: {record["status"]}')
            links.append(
                f'<a href="{escape(record["url"], quote=True)}">{text}</a>'
                if "url" in record else text
            )
        rows.append(f"<tr><td>{trace_link}</td><td>{'<br>'.join(links)}</td></tr>")
    page = (
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>AgentTrace batch links</title>'
        "<h1>AgentTrace batch links</h1><p>Local links require the original server/database.</p>"
        "<table><thead><tr><th>Trace</th><th>Analyses</th></tr></thead><tbody>"
        + "".join(rows) + "</tbody></table></html>"
    )
    links_path = output / "links.html"
    links_path.touch(mode=0o600)
    links_path.chmod(0o600)
    links_path.write_text(page)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON array or object with a traces array.")
    parser.add_argument("--output", type=Path, required=True, help="Private export directory; index.json includes links.")
    parser.add_argument("--server", type=local_server, default="http://127.0.0.1:3000")
    parser.add_argument("--scout", action="store_true", help="Explicitly send traces to the configured model provider; charges may apply.")
    parser.add_argument("--communication", action="store_true", help="Run experimental four-class incident analysis; raw trace evidence goes to the configured provider and charges may apply.")
    parser.add_argument("--model", help="Provider/model for explicitly selected pipelines; otherwise use their server defaults.")
    parser.add_argument("--rerun", action="store_true", help="Rerun completed analyses, including paid pipelines when selected.")
    parser.add_argument("--wait-timeout", type=positive, default=1800)
    parser.add_argument("--poll-interval", type=positive, default=2)
    args = parser.parse_args()
    if args.model and not (args.scout or args.communication):
        parser.error("--model requires --scout or --communication.")
    try:
        data = json.loads(args.input.read_text())
    except (OSError, ValueError) as error:
        parser.error(str(error))
    entries = data.get("traces") if isinstance(data, dict) else data
    if not isinstance(entries, list) or not entries or any(
        not isinstance(entry, dict) or not (
            isinstance(entry.get("trace_id"), str)
            or isinstance(entry.get("url"), str)
            or isinstance(entry.get("source"), dict)
        ) for entry in entries
    ):
        parser.error("Provide a nonempty traces array; each entry needs trace_id, url, or source.")
    if args.scout:
        print("Scout explicitly requested: trace content will go to the configured provider; charges may apply.", file=sys.stderr)
    if args.communication:
        print("Communication analysis explicitly requested: trace evidence goes to the configured provider; charges may apply.", file=sys.stderr)
    with httpx.Client(base_url=args.server, timeout=60) as client:
        result = run_batch(client, entries, args.output, args.server, scout=args.scout,
                           model=args.model, rerun=args.rerun,
                           communication=args.communication,
                           wait_timeout=args.wait_timeout, poll_interval=args.poll_interval)
    print(f"Results and links: {args.output / 'index.json'}")
    return 0 if all(t["status"] == "completed" for t in result["traces"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
