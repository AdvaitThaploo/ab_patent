"""Schema for one extracted thermal-stability measurement.

Field descriptions are part of the prompt: the model receives this as the JSON
response schema, so each description is an instruction it reads.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Assay(BaseModel):
    """How the value was measured. A Tm by DSC and a Tm by DSF are different
    numbers for the same molecule, so the method is part of the measurement."""

    method: str | None = Field(description="'DSC', 'DSF', 'nanoDSF', 'CD', 'thermal shift'")
    instrument: str | None = Field(description="e.g. 'MicroCal VP-DSC', 'Prometheus', 'UNcle'")
    method_verbatim: str | None = Field(
        description="The method sentence copied from the text, when present"
    )


class Conditions(BaseModel):
    """Buffer conditions. The same antibody differs by several degrees between
    pH 4.5 and pH 7.5, so a value without them cannot be compared."""

    ph: float | None = None
    buffer: str | None = Field(default=None, description="e.g. '20 mM histidine', 'PBS'")
    concentration_mg_ml: float | None = None
    excipients: str | None = Field(default=None, description="e.g. 'sucrose, polysorbate 80'")


class Measurement(BaseModel):
    property: Literal["thermal_stability", "other"] = Field(
        description="'thermal_stability' for a protein melting/unfolding temperature. "
        "'other' for anything else, including aggregation onset (Tagg), binding "
        "affinity, titre, or nucleic-acid melting temperature."
    )
    property_raw: str = Field(
        description="The patent's own term, verbatim: 'Tm', 'Tm1', 'Tm(CH2)', "
        "'apparent Fab Tm'. Do not normalise it."
    )
    transition: str | None = Field(
        description="Which unfolding transition, when the patent distinguishes "
        "several: 'Tm1', 'Tm2', 'CH2', 'CH3', 'Fab'. Null if only one Tm is "
        "reported. These are different quantities, not repeat measurements."
    )

    value: float | None = Field(description="The value, or the lower bound of a range")
    value_max: float | None = Field(description="Upper bound when operator is 'range'")
    unit: str | None = Field(description="Normally 'C'")
    operator: Literal["eq", "gte", "lte", "range"] = Field(
        description="'eq' for a single value; 'gte'/'lte' for 'greater/less than'; "
        "'range' when both bounds are given"
    )
    is_delta: bool = Field(
        description="True if the value is a change from a baseline (a Tm shift of "
        "+2.4 C) rather than an absolute temperature."
    )

    value_type: Literal["measured", "claimed_range"] = Field(
        description="'measured' for an experimental result on a named molecule; "
        "'claimed_range' for patent-scope language such as 'in some embodiments, "
        "a Tm of greater than about 83.5 C'"
    )
    source_location: Literal["text", "table", "figure_reference"] = Field(
        description="'figure_reference' when the number is only in an image "
        "('see FIG. 2') and cannot be read from the text"
    )

    clone_id: str | None = Field(
        description="The molecule's name as printed: 'SI-1X2', 'Ab-7', 'VH3/Vk5', "
        "'Formulation 1'. Copy it exactly, including a bare number if that is "
        "what the row is labelled with."
    )
    seq_ids: list[int] = Field(
        description="Every SEQ ID NO the patent ties to this molecule, from "
        "anywhere in the document. Empty if the patent never ties it to a sequence."
    )
    molecular_format: str | None = Field(description="e.g. 'IgG1', 'Fab', 'scFv', 'bispecific'")

    assay: Assay
    conditions: Conditions
    verbatim: str = Field(
        description="The exact sentence or table row stating the value, copied "
        "character-for-character from the input. Do not paraphrase."
    )


class Extraction(BaseModel):
    measurements: list[Measurement]
