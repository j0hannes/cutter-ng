SHELL = bash

VERSION = "2.1"

.PHONY: version

default: run_tests

run_tests:
	./test.py test/*.yaml -s

version:
	echo "$(VERSION) (rev: $$(git rev-parse --short HEAD))" > $@
