"""The shapes a Katha is built from and returned as."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Kind = Literal["place", "city", "day"]
Depth = Literal["quick", "deep"]
ChunkType = Literal["hook", "story", "fact", "sensory", "taste", "practical"]


class Scope(BaseModel):
    kind: Kind
    id: int | str  # place: poi id, city: city name, day: day index in the trip


class SourceRef(BaseModel):
    name: str | None = None
    url: str | None = None


class SourceChunk(BaseModel):
    id: int
    title: str | None
    body: str
    chunk_type: ChunkType
    is_legend: bool


class Segment(BaseModel):
    title: str
    chunk_type: ChunkType
    is_legend: bool
    body_source_chunks: list[SourceChunk]
    sources: list[SourceRef]
    text: str  # the corpus's words; replaced by narration in the chosen language
    words: int
    spine_item: str
    narration: str | None = None
    theme: str | None = None  # set on a city Katha's segments; see city_layer.py


class SpineItem(BaseModel):
    label: str
    query: str
    poi_id: int | None
    city: str
    weight: float
    words: int = 0


class Katha(BaseModel):
    id: str | None = None
    scope: Scope
    duration_min: int
    depth: Depth
    language: str
    segments: list[Segment]
    total_words: int
    spine: list[SpineItem]
    type_sequence: list[str] = Field(default_factory=list)
    note: str | None = None  # "nothing written about X as a city yet", when so
