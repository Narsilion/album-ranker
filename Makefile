.PHONY: install run test

# macOS marks pip-created files with UF_HIDDEN (com.apple.provenance).
# Python 3.14 skips .pth files that have UF_HIDDEN set, which breaks editable
# installs.  Run `make install` instead of plain `pip install -e .`.
install:
	.venv/bin/pip install -e .
	chflags -R nohidden .venv
	xattr -dr com.apple.provenance .venv 2>/dev/null || true

run:
	.venv/bin/album-ranker

test:
	.venv/bin/python -m pytest
