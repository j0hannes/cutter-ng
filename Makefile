SHELL = bash

default: run_tests

run_tests:
	./test.py test/*.yaml -s

