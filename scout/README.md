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

5. Run the starter scanners with a configured Inspect model:

   ```bash
   scout scan scout/scanners.py \
     -T ./transcripts \
     --model openai/gpt-5
   ```

6. Review transcripts, cited evidence, and scan results:

   ```bash
   scout view
   ```

The starter scanners cover duplicated work, weak handoffs, and visible
information that was not integrated. Their outputs are model judgments, not
ground truth. Create a human-labeled validation set before using them as
research measures.
