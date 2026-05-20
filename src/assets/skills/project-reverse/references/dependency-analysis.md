# Dependency Analysis And Reuse Scoring

Use this reference to convert repository structure into module evidence and reuse signals.

## Module Dependency Signals

Capture these signals where cheap and deterministic:

- local imports between top-level directories or packages
- manifest workspace members and path dependencies
- package exports and barrel files
- public interfaces/types used across modules
- tests that cross module boundaries
- config or global state shared by many modules

## Language Patterns

- TypeScript/JavaScript: `import ... from`, `require(...)`, `export * from`, package workspaces.
- Python: `import`, `from ... import`, package `__init__.py`, `pyproject.toml`.
- Rust: workspace members, path dependencies, `use crate::`, `use super::`, public modules.
- Go: module path imports and package directories.
- Java/C#: package namespaces, project files, DI registrations.

## Reuse Score

Use a 1-5 score:

- `5`: fully independent, clear public interface, few dependencies, reusable as a package.
- `4`: mostly independent, minor adapters or config extraction needed.
- `3`: moderately coupled, needs adapter layer or dependency injection.
- `2`: tightly coupled to runtime, config, or shared state.
- `1`: core architectural piece or domain-specific module not worth extracting.

Record score evidence:

- dependency footprint
- public API clarity
- test coverage
- config isolation
- domain specificity
- license or packaging constraints

Use the score conservatively. A directory with many public symbols is not automatically reusable: lower the score when it depends on global config, runtime lifecycle, generated code, infrastructure side effects, or private package conventions.

If enough data is available, include a short factor breakdown:

- `independence`: external and sibling dependencies
- `generality`: project-specific terminology and assumptions
- `testability`: isolated tests vs full-system boot
- `packaging`: manifest/export clarity
- `configuration`: whether behavior can be parameterized without code edits

## Coupling Risks

Flag:

- bidirectional imports
- shared mutable global state
- modules importing concrete internals instead of interfaces
- many unrelated responsibilities in one directory
- tests that require full-system boot for narrow behavior
- generated code or macros that obscure contracts
- circular or bidirectional imports
- shared config, database connections, or mutable global state used across module boundaries
