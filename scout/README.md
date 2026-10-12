# Optional standalone Scout bridge

AgentTrace's normal workflow runs Scout directly from the UI through the Python
API. No export/import is required. This bridge remains available for standalone
Inspect Scout transcript databases, scans and `scout view`.

Install the editable monorepo packages first (`make install` in the root), then
activate that environment:

```bash
source .venv/bin/activate
```

Analyze a trace in AgentTrace and select **Export for Scout**, then:

```bash
python scout/import_transcript.py agenttrace-scout-transcript.json --output ./transcripts

scout scan scout/message_annotations.py \
  -T ./transcripts \
  --model provider/model \
  --cache

scout scan scout/scanners.py \
  -T ./transcripts \
  --model provider/model \
  --cache

scout view
```

Replace `provider/model` and configure its credentials in your environment.
Scans send data to that provider and may incur charges. The compatibility
scanner files delegate to the installed `agenttrace.scout` implementation.
They do not contain a second pipeline.

Bridge version `1.0` is still readable. New exports use the canonical trace
identifier and AgentTrace metadata; old exports retain their old identities.
Re-export/re-import pre-annotation bridges to obtain bounded earlier context.
See [MESSAGE_ANNOTATION.md](../MESSAGE_ANNOTATION.md) for the taxonomy,
candidate limits, evidence validation and research limitations.
