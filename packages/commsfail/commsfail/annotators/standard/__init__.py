"""Annotation of failure incidents by agents: a bundle, two annotators, a judge, a verdict (annotation.v1).

    from commsfail.annotators.standard import annotate, DockerCodex
    record = annotate("runs/rom_abc", "out/rom_abc", DockerCodex(), grade="runs/rom_abc/score.json")

See pipeline.py for the steps, bundle.py for what the agents read, check.py for what their replies must pass.
"""
from .bundle import build as build_bundle
from .check import annotation as check_annotation, judged as check_judged, sweep as check_sweep, verdict as check_verdict
from .pipeline import DockerCodex, annotate

__all__ = ["annotate", "DockerCodex", "build_bundle", "check_annotation", "check_judged", "check_sweep",
           "check_verdict"]

# Runs through annotate/annotate-batch; excluded from the offline Trace annotator registry.
PIPELINE = True
