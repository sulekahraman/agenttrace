# Inspect Scout bridge

TraceScope's primary report remains deterministic. The optional Scout bridge
converts the same normalized messages into a transcript database for semantic
scanning.

## Export and import

1. Analyze a SharedNet conversation in TraceScope.
2. Select **Export for Scout**.
3. Create a Python environment and install Scout:

   ```bash
   python -m venv .venv-scout
   source .venv-scout/bin/activate
   pip install -r scout/requirements.txt
   ```

4. Import the downloaded bridge file:

   ```bash
   python scout/import_transcript.py tracescope-scout-transcript.json \
     --output ./transcripts
   ```

   Re-import bridges created before the message-annotation integration. Older
   transcript databases do not contain the bounded annotation context.

5. Generate reusable message annotations:

   ```bash
   scout scan scout/message_annotations.py \
     -T ./transcripts \
     --model openai/gpt-5 \
     --cache
   ```

6. Run the annotation-guided collaboration scanner:

   ```bash
   scout scan scout/scanners.py \
     -T ./transcripts \
     --model openai/gpt-5 \
     --cache
   ```

7. Review transcripts, cited evidence, and scan results:

   ```bash
   scout view
   ```

See [`MESSAGE_ANNOTATION.md`](../MESSAGE_ANNOTATION.md) for the taxonomy,
bounded context, labeling rules, and scanner architecture. Annotations and
findings are model judgments, not ground truth. Create a human-labeled
validation set before using them as research measures.
