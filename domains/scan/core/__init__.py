"""scan core pipeline shim."""

from domains._shared.waste_pipeline import PipelineError, process_waste_classification

__all__ = ["PipelineError", "process_waste_classification"]
