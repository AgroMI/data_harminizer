from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel
from pydantic.fields import PydanticUndefined

ToolCategory = Literal["query", "metadata", "conversion", "retrieval"]


@dataclass(frozen=True, slots=True)
class ToolFieldDefinition:
    name: str
    type_name: str
    required: bool
    description: str | None = None
    default: Any = None


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    tool_name: str
    description: str
    category: ToolCategory
    read_only: bool
    input_fields: tuple[ToolFieldDefinition, ...]


class BaseTool:
    tool_name: str
    description: str
    category: ToolCategory
    read_only: bool = True
    input_model: type[BaseModel]

    def validate_arguments(self, arguments: dict[str, Any]) -> BaseModel:
        return self.input_model.model_validate(arguments)

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            tool_name=self.tool_name,
            description=self.description,
            category=self.category,
            read_only=self.read_only,
            input_fields=tuple(_tool_field_definitions(self.input_model)),
        )

    def execute(self, arguments: BaseModel) -> dict[str, Any]:
        raise NotImplementedError


def _tool_field_definitions(model_type: type[BaseModel]) -> list[ToolFieldDefinition]:
    field_definitions: list[ToolFieldDefinition] = []
    for field_name, field_info in model_type.model_fields.items():
        field_definitions.append(
            ToolFieldDefinition(
                name=field_name,
                type_name=_annotation_name(field_info.annotation),
                required=field_info.is_required(),
                description=field_info.description,
                default=_field_default(field_info),
            )
        )
    return field_definitions


def _annotation_name(annotation: Any) -> str:
    if annotation is None:
        return "unknown"
    name = getattr(annotation, "__name__", None)
    if isinstance(name, str):
        return name
    return str(annotation).replace("typing.", "")


def _field_default(field_info: Any) -> Any:
    if field_info.is_required():
        return None
    if field_info.default is PydanticUndefined:
        return None
    return field_info.default
