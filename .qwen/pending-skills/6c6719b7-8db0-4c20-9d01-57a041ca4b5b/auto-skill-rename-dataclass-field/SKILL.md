---
name: rename-dataclass-field
description: Procedure to rename a dataclass field, change its type, and update all construction/access sites across a codebase using parallel agents.
source: auto-skill
extracted_at: '2026-07-13T15:33:40.878Z'
---

# Renaming a dataclass field + changing its type across the codebase

Use this when you need to rename a field on a `@dataclass`, change its type (e.g. `Dict[str, Any]` → a structured dataclass), and update every construction site and accessor.

## Steps

### 1. Design the new type(s)

Define the replacement type alongside the old field. If the old value was a raw dict used as JSON Schema, create a structured dataclass with a `to_dict()` method that downstream callers can use:

```python
@dataclass
class ToolParameter:
    name: str
    type: str = "string"
    description: str = ""
    required: bool = True
    enum: Optional[List[str]] = None
    default: Optional[Any] = None

@dataclass
class ToolSchema:
    type: str = "object"
    properties: List[ToolParameter] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        required = []
        props = {}
        for p in self.properties:
            prop = {"type": p.type}
            if p.description:
                prop["description"] = p.description
            if p.enum:
                prop["enum"] = p.enum
            if p.default is not None:
                prop["default"] = p.default
            props[p.name] = prop
            if p.required:
                required.append(p.name)
        result = {"type": self.type, "properties": props}
        if required:
            result["required"] = required
        return result
```

### 2. Rename the field + update the type in the dataclass

```python
@dataclass
class Tool:
    name: str
    description: str
    schemas: ToolSchema          # was: parameters: Dict[str, Any]
    handler: Callable[..., Any]
```

Also update `__str__` or any other method that references the old name.

### 3. Resolve name conflicts

If the new class name shadows an existing type alias elsewhere (e.g. `ToolSchema` was already a `TypeAlias = dict[str, ...]`), rename the type alias to something like `ToolSchemaDict` and update all its usages.

### 4. Update immediate consumers

These are the files that **access** the field (not just construct it):

- `tool.handler(**tool.parameters)` → `tool.handler(**tool.schemas.to_dict())`
- `json_schema_object(tool.parameters)` → `tool.schemas.to_dict()`
- `Tool.__str__` string interpolation

### 5. Update handler / type-hint files

Files that import and use the old type alias need their imports and type annotations updated.

### 6. Launch parallel agents for construction sites

Use background agents to handle the bulk of the work. Group files by directory and assign each agent a batch. Each agent should:

1. Fix the import line (e.g. `from ..tool import Tool` → `from ..llm_types import Tool, ToolSchema, ToolParameter`)
2. Convert every `parameters={...}` dict to `schemas=ToolSchema(properties=[ToolParameter(...), ...])`
3. Drop fields not supported by the new type (e.g. `minimum`, `maximum`, `additionalProperties`, `items`)
4. Set `required=False` for parameters not in the old `"required"` list
5. Preserve `description`, `enum`, `default`

### 7. Fix remaining broken imports

Search for any `from ..tool import Tool` or `from llmfetcher.tool import Tool` patterns and update them.

### 8. Verify

- `grep` for zero remaining old field name (`\.parameters` or `parameters=`)
- `grep` for zero remaining old import path (`\.tool import Tool`)
- `py_compile.compile()` each modified file to catch syntax errors
