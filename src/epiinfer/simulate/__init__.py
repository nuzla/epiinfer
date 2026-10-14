"""Synthetic age-structured agent-based simulator (AgeMixABM) used in the paper."""

from .abm import (
    CONTACT_MATRICES,
    PAPER_GROUP_SIZES,
    AgeMixConfig,
    simulate,
    write_dataset,
)

__all__ = ["AgeMixConfig", "CONTACT_MATRICES", "PAPER_GROUP_SIZES", "simulate", "write_dataset"]
