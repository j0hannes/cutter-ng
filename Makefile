SHELL = bash

VERSION = "2.2"

.PHONY: version

default: run_tests

run_tests:
	./test.py test/*.yaml -s

run_smultron_tests:
	./test.py test/smultron/*.yaml -s

version:
	echo "$(VERSION) (rev: $$(git rev-parse --short HEAD))" > $@
