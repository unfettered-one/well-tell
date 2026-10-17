"""Small, backwards-compatible visual contract. No business rules live here."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DisplayField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str = Field(min_length=1)
    label: str | None = None
    unit: str | None = None
    format: Literal["text", "number", "date", "datetime", "percent"] | None = None
    decimals: int | None = Field(default=None, ge=0, le=10)


class ResultLimit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    truncated: bool = False
    total: int | None = Field(default=None, ge=0)
    limit: int | None = Field(default=None, ge=0)


class Visual(BaseModel):
    # Keep unknown legacy display attributes, but validate every supported mapping.
    model_config = ConfigDict(extra="allow")
    type: Literal["status_card", "table", "line", "bar", "map", "heatmap"]
    title: str | None = None
    data: list[dict]
    columns: list[DisplayField] | None = None
    x: DisplayField | None = None
    y: list[DisplayField] | None = Field(default=None, min_length=1)
    series: str | None = None
    latitude: str | None = None
    longitude: str | None = None
    well_id: str | None = None
    row: DisplayField | None = None
    column: DisplayField | None = None
    value: DisplayField | None = None
    result_limit: ResultLimit | None = None

    @model_validator(mode="before")
    @classmethod
    def legacy_explicit_mappings(cls, value):
        """Accept old explicit field names; never infer axes from row values."""
        if not isinstance(value, dict):
            return value
        value = dict(value)
        if value.get("type") == "heatmap":
            if isinstance(value.get("x"), str):
                value.setdefault("column", {"field": value.pop("x")})
            if isinstance(value.get("y"), str):
                value.setdefault("row", {"field": value.pop("y")})
            if isinstance(value.get("value"), str):
                value["value"] = {"field": value["value"]}
        else:
            if isinstance(value.get("x"), str):
                value["x"] = {"field": value["x"]}
            if isinstance(value.get("y"), str):
                value["y"] = [{"field": value["y"]}]
            elif isinstance(value.get("y"), list):
                value["y"] = [{"field": f} if isinstance(f, str) else f for f in value["y"]]
        return value

    @model_validator(mode="after")
    def referenced_fields_exist(self):
        fields = [*(self.columns or []), *(self.y or [])]
        fields += [f for f in (self.x, self.row, self.column, self.value) if f]
        names = [f.field for f in fields]
        names += [f for f in (self.series, self.latitude, self.longitude, self.well_id) if f]
        keys = {key for row in self.data for key in row}
        if self.data and any(name not in keys for name in names):
            raise ValueError("Visual mappings must reference returned data fields")
        return self
