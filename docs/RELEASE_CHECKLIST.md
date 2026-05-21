# Release Checklist

1. Run CLI smoke tests:
   - `python -m src --help`
   - `python -m src init --help`
   - `python -m src ingest --help`
   - `python -m src query --help`
   - `python -m src lint --help`
   - `python -m src doctor --root kb`
   - `python -m src sync --root kb --check`
   - `python -m src upgrade --root kb --dry-run`
2. Build distributions:
   - `python -m build`
3. Install the wheel in a clean virtual environment.
4. Verify bundled assets are present:
   - `src/assets/templates/`
   - `src/assets/schema/`
   - `src/assets/tools/`
   - `src/assets/skills/`
5. Create a GitHub release with the source archive and wheel artifacts.
6. Publish to PyPI after the local wheel install passes.
