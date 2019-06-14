SHELL = bash

VERSION = "2.5"

.PHONY: version


default: test

tests:
	./test.py test/*.yaml -s

treebank_tests:
	./test.py test/smultron/*.yaml -s

version:
	echo "$(VERSION) (rev: $$(git rev-parse --short HEAD))" > $@
