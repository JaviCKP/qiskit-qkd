"""Reproducible artifact writers for thesis experiments.

The simulation library stays independent of filesystem output.  Experiment
scripts opt into :func:`write_artifact` at their CLI boundary, so importing a
script or running an individual helper does not create files as a side effect.
"""

from .manifest import ArtifactPaths, build_manifest, write_artifact

__all__ = ["ArtifactPaths", "build_manifest", "write_artifact"]
