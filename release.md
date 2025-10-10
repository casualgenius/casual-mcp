# Releasing a New Version of casual-mcp

## ✅ 1. Bump the Version Number

Use bump-my-version to update the version (e.g., to 0.2.3):

```bash
uvx bump-my-version bump patch  # or use minor / major
```

This will:
- Update the version in pyproject.toml
- Commit the change (if configured)
- Tag the version (if configured)

You can verify the new version with:

```bash
uvx bump-my-version show
```

## ✅ 2. Build the Distributions

Make sure you're in the root of the project and then build the wheel and source distribution:

```bash
python -m build
```

This creates:
- dist/casual_mcp-X.Y.Z.tar.gz
- dist/casual_mcp-X.Y.Z-py3-none-any.whl

## ✅ 3. Upload to PyPI

Make sure you have a valid API token saved (or copy it from https://pypi.org/account/token/
).

Upload using twine:

```bash
twine upload dist/*
```

If needed, you can use:

```bash
twine upload dist/* -u __token__ -p pypi-***your-api-token***
```

If you accidentally try to upload an older version, PyPI will reject it with a "File already exists" error — just make sure your version bump was successful.

## ✅ 4. (Optional) Push Tags to GitHub

If bump-my-version created a tag and you want it pushed:

```bash
git push origin main --tags
```

## 🧠 Troubleshooting Tips

If you forgot to build after bumping the version, just run python -m build again — it'll pick up the new version from pyproject.toml.

Make sure you delete old files from dist/ if you're testing locally before a real upload:

```bash
rm dist/*
```