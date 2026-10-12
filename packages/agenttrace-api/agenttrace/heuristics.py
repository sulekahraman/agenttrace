from .view_model import build_view_model


class StructuralHeuristics:
    """Lexical and turn-taking research prompts, not task-outcome judgments."""

    name = "agenttrace_heuristics_v1"
    version = "1.0.0"
    schema = "schemas/heuristics.v1.json"

    def annotate(self, trace):
        report = build_view_model(trace)
        return {
            "metrics": report["metrics"],
            "participants": report["participants"],
            "transitions": report["transitions"],
            "failureModes": report["failureModes"],
        }
