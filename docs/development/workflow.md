# Git Workflow

## Branch Naming

| Branch | Purpose |
|--------|---------|
| `main` | Production-ready code |
| `feat/<description>` | New feature |
| `fix/<description>` | Bug fix |
| `docs/<description>` | Documentation only |
| `chore/<description>` | Tooling, dependencies, CI |

Examples: `feat/add-rag-endpoint`, `fix/tesseract-fallback`, `docs/api-extraction`

## Development Flow

```bash
# 1. Start from a fresh main
git checkout main
git pull origin main

# 2. Create your feature branch
git checkout -b feat/my-feature

# 3. Make changes and commit often
git add backend/api/routes.py
git commit -m "feat(api): add document summary endpoint"

# 4. Push to GitHub
git push -u origin feat/my-feature

# 5. Open a Pull Request on GitHub
```

## Commit Message Format

Follow [Conventional Commits](style.md#commit-messages):

```
feat(ocr): add PaddleOCR engine integration

- Add PaddleOCREngine class implementing the OCREngine interface
- Register engine in ocr_engine.py
- Add optional paddleocr dependency
```

The first line is a short summary (≤ 72 chars). The body explains *why*, not *what*.

## Pull Request Checklist

Before opening a PR:

- [ ] Feature branch is up-to-date with `main` (`git rebase main`)
- [ ] All tests pass (`cd backend && pytest`)
- [ ] No linting errors (`flake8 backend/` and `npm run lint`)
- [ ] New API endpoints are documented in `docs/api/`
- [ ] PR description explains what changed and why

## Code Review

- At least one reviewer approval is required to merge.
- Respond to review comments within 48 hours.
- Address all comments before merging; use "Resolved" to indicate a comment is addressed.

## Merging

- Use **Squash and merge** for feature branches to keep history clean.
- Use **Merge commit** only for release branches that need a merge record.
- Delete the feature branch after merging.

## Versioning

PDF Manager uses [Semantic Versioning](https://semver.org/):

- `MAJOR.MINOR.PATCH`
- Bump `PATCH` for bug fixes
- Bump `MINOR` for new features (backwards compatible)
- Bump `MAJOR` for breaking API changes
