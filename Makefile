.DEFAULT_GOAL := help

NIX ?= nix
FLAKE ?= path:.
ARGS ?=

.PHONY: help run build dist test shell

help:
	@printf '%s\n' \
	  'make run     Run Viewview in the Nix development environment' \
	  'make build   Build the portable application for the current platform' \
	  'make dist    Build and copy the distributable into dist/' \
	  'make test    Run the application test suite in Nix' \
	  'make shell   Enter the Nix development environment' \
	  '' \
	  'Pass CLI arguments with: make run ARGS="--help"'

run:
	$(NIX) develop "$(FLAKE)" --command python -m viewview $(ARGS)

build:
	$(NIX) build "$(FLAKE)#bundle"

dist: build
	@mkdir -p dist
	@set -eu; case "$$(uname -s)" in \
	  Linux) \
	    cp -fL result dist/Viewview.AppImage; \
	    chmod 755 dist/Viewview.AppImage ;; \
	  Darwin) \
	    ditto -c -k --sequesterRsrc --keepParent result/Viewview.app dist/Viewview-macos-arm64.zip ;; \
	  *) \
	    printf '%s\n' 'Distribution is supported on Linux and Apple Silicon macOS.' >&2; \
	    exit 1 ;; \
	esac

test:
	$(NIX) develop "$(FLAKE)" --command python -m unittest discover -s tests -v

shell:
	$(NIX) develop "$(FLAKE)"
