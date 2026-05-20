# Release Checklist

1. Run CLI smoke tests:
   - `python -m llm_wiki --help`
   - `python -m llm_wiki init --help`
   - `python -m llm_wiki doctor --root kb`
   - `python -m llm_wiki sync --root kb --check`
   - `python -m llm_wiki upgrade --root kb --dry-run`
2. Build distributions:
   - `python -m build`
3. Install the wheel in a clean virtual environment.
4. Verify bundled assets are present:
   - `llm_wiki/assets/templates/`
   - `llm_wiki/assets/schema/`
   - `llm_wiki/assets/tools/`
   - `llm_wiki/assets/skills/`
5. Create a GitHub release with the source archive and wheel artifacts.
6. Publish to PyPI after the local wheel install passes.
