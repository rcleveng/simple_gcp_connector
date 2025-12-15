# Contributing

## Release Process

To create a new release:

1. Update the version in `pyproject.toml`.
2. Commit the changes.
3. Create and push a tag matching the version number (e.g., `v0.1.3`):

```bash
git tag -a v0.1.3 -m v0.1.3
git push --tags
```

This will trigger the CI/CD pipeline, which will:
1. Run the tests.
2. If tests pass, verify the tag is on the `main` branch.
3. Publish to PyPI.
4. Create a GitHub Release.
