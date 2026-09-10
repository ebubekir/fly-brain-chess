# Contributing

1. Fork the repository and create a focused branch.
2. Use the local development setup in README.md.
3. Add tests for changed chess, neural, or protocol behavior. Keep seeded trials reproducible.
4. Run pytest, Ruff, `npm run build`, and the Docker smoke test.
5. Open a pull request explaining the problem, implementation, and verification.

Keep browser dependencies local and preserve the one-command Docker setup.
Do not commit secrets, virtual environments, node_modules, or downloaded datasets.
For biological data, include provenance, release ID, license, filtering rules,
units, and citations. Never describe synthetic activity as measured fly behavior.

By contributing, you agree to license your changes under GPL-3.0-or-later.
