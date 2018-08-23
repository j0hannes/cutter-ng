#!/usr/bin/env python3
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4 colorcolumn=80
#     ______________________________________ ______________________
#     \                                     | (_)     (_)    (_)   \
#      `.  http://pub.cl.uzh.ch/purl/cutter |  __________________   }
#        `-.............................____|_(                  )_/
#

import sys
import argparse
import regex
import yaml
import itertools
import collections
import Cutter


class Tester:
    """ Evaluates unit tests for tokenization."""

    # Private

    def _pprint(self, name, gold, test):
        gold_max = max(([len(e[1]) for e in gold]))
        test_max = max(([len(e[1]) for e in test]))
        print(' \033[1;4m{{:^{}}}\033[0m'.format(
            23 + gold_max + test_max).format(name))
        for (g, t) in itertools.zip_longest(gold, test, fillvalue=('', '')):
            check = (g[1] == t[1] and (g[0] is None or g[0] == t[0]))
            print(
                '  \033[{{}}m{{:<{}}} \033[1m{{:<8}}\033[0m'
                ' \033[{{}}m{{:<{}}} \033[1m{{:<8}}\033[0m'
                ' \033[{{}}m{{}}\033[0m'.format(
                    gold_max, test_max).format(
                        33, g[1], '' if g[0] is None else g[0],
                        36, t[1], t[0],
                        32 if check else 31, '✓' if check else '✗'))
        print()

    def _remove_special_chars(self, s):
        return regex.sub('[{}{}{}]'.format(
                Cutter.FIRST_WORD,
                Cutter.COVER_BEGIN,
                Cutter.COVER_END),
            '', s)

    # Public

    def __init__(self, cutter, flags, limit, print_all, report_file):
        self.cutter = cutter
        self.flags = flags
        self.limit = limit
        self.print_all = print_all
        self.report_file = report_file
        self.processed = 0
        self.errors = 0
        self.failed = 0

    def run_tests(self, tests):
        for i, test in enumerate(tests):
            name = test['name'] if 'name' in test else '#{}'.format(i+1);
            if self.limit is not None:
                if name not in self.limit:
                    continue
            self.cutter._log(0, "Running test `{}'".format(name))
            if not 'unit' in test:
                print("Assertion missing.")
                sys.exit(3)
            markers = ['[', ']']
            if 'markers' in test:
                if not type(test['markers']) is list:
                    print("`markers' should be a list.")
                    sys.exit(4)
                if not len(test['markers']) == 2:
                    print("We need exactly two markers.")
                    sys.exit(5)
                if (not type(test['markers'][0]) is str
                        or not type(test['markers'][1]) is str):
                    print("`markers' should be both strings.")
                    sys.exit(6)
                markers = test['markers']
            separator = '|'
            if 'separator' in test:
                if not type(test['separator']) is str:
                    print("`separator' should be a string.")
                    sys.exit(7)
                separator = test['separator']
            if 'tokens' in test:
                text = test['unit']
                tokens_gold = [
                    (
                        list(e.items())[0][0],
                        self._remove_special_chars(list(e.items())[0][1] or '')
                    ) if type(e) is dict
                    else
                        (None, self._remove_special_chars(e))
                    for e in test['tokens']]
            else:
                scanner = regex.finditer(
                    '{0}(?<token>[^{1}{2}]+|)(?:{2}(?<tag>[\S]+))?{1}'
                    '|(?<token>[^\s{0}{2}]+)'.format(
                        regex.escape(markers[0]),
                        regex.escape(markers[1]),
                        regex.escape('|')),
                    self._remove_special_chars(test['unit']),
                    flags=regex.VERSION1)
                tokens_gold = [
                    (m.capturesdict()['tag'][0] if len(m.capturesdict()['tag'])
                    else None, m.capturesdict()['token'][0]) for m in scanner]
                text = regex.sub('{2}[^\s{0}]+{1}|[{0}{1}{2}]'.format(
                        regex.escape(markers[0]),
                        regex.escape(markers[1]),
                        regex.escape('|')),
                    '', test['unit'])
            tokens_test = list(self.cutter.cut(text, flags=self.flags));
            errors = sum([g[1] != t[1] or (g[0] is not None and g[0] != t[0])
                for (g, t) in itertools.zip_longest(
                    tokens_gold,
                    tokens_test,
                    fillvalue=('', ''))])
            self.processed += 1
            self.errors += errors
            if errors:
                self.failed += 1
            if errors or self.print_all:
                self._pprint(name, tokens_gold, tokens_test)


def main(argv):
    parser = argparse.ArgumentParser(
        description='Test language models.')
    parser.add_argument(
        '-v', '--verbose',
        action='count', default=0, help='be more verbose')
    parser.add_argument(
        '-r', '--report',
        type=argparse.FileType('w'), default=sys.stdout,
        help='where to write the report')
    parser.add_argument(
        '-l', '--limit',
        nargs='*',
        help='limit to particular test(s) from a set')
    parser.add_argument(
        '-a', '--all',
        action='store_true',
        help='show details for all tests')
    parser.add_argument(
        '-s', '--summary',
        action='store_true',
        help='show only summary')
    parser.add_argument(
        'test',
        nargs='+',
        type=argparse.FileType('r'),
        help='evaluate these tests')
    args = parser.parse_args()

    tests_processed = 0
    tests_failed = 0
    sets_processed = collections.defaultdict(int)
    sets_failed = collections.defaultdict(int)
    errors = 0
    for testfile in args.test:
        try:
           testset = yaml.load(testfile)
        except yaml.YAMLError as exc:
            print("ERROR: loading rule file failed: {}".format(exc))
            sys.exit(2)
        if not 'test' in testset:
            print("No tests found in `{}'.".format(testfile.name))
            sys.exit(3)
        cutter = Cutter.Cutter(verbosity=args.verbose)
        flag_et = 1
        flag_tt = 1
        flag_wt = 0
        name = '{} ({})'.format(
                testset['name'],
                testfile.name
            ) if 'name' in testset else testfile.name
        if 'abbr' in testset:
            for filename in testset['abbr']:
                try:
                    file = open(filename, 'r')
                except FileNotFoundError:
                    print("File not found `{}' (referenced in `{}').".format(
                        filename, testfile.name))
                    sys.exit(4)
                cutter.add_abbrs(file)
        if 'init' in testset:
            for filename in testset['init']:
                try:
                    file = open(filename, 'r')
                except FileNotFoundError:
                    print("File not found `{}' (referenced in `{}').".format(
                        filename, testfile.name))
                    sys.exit(4)
                cutter.add_inits(file)
        if 'flag' in testset:
            for flag in testset['flag']:
                if flag == 'no-empty-tokens':
                    flag_et = 0
                elif flag == 'no-tokenizer-tag':
                    flag_tt = 0
                elif flag == 'whitespace-tokens':
                    flag_wt = 1
                else:
                    print("Unknown flag `{}'".format(flag))
                    sys.exit(5)
        if 'rule' in testset:
            for filename in testset['rule']:
                try:
                    file = open(filename, 'r')
                except FileNotFoundError:
                    print("File not found `{}' (referenced in `{}').".format(
                        filename, testfile.name))
                    sys.exit(4)
                cutter.add_rules(file)
        else:
            print("We don't know which rules to use.")
            sys.exit(6)
        if not 'test' in testset or not testset['test']:
            print("There is no test in `{}'.".format(testfile.name))
            continue
        flags = (
            flag_wt * Cutter.WHITESPACE_TOKENS
            + flag_et * Cutter.EMPTY_TOKENS
            + flag_tt * Cutter.TOKENIZATION_TAGS)
        tester = Tester(
            cutter,
            flags=flags,
            limit=args.limit,
            print_all=args.all,
            report_file=args.report)
        tester.run_tests(testset['test'])
        tests_processed += tester.processed
        tests_failed += tester.failed
        sets_processed[name] += tester.processed
        if tester.failed > 0:
            sets_failed[name] += tester.failed
        errors += tester.errors
    print(
        '\033[31m{} test{} in {} set{} failed ({} error{}).\033[0m'.format(
            tests_failed, '' if tests_failed == 1 else 's',
            len(sets_failed), '' if len(sets_failed) == 1 else 's',
            errors, '' if errors == 1 else 's')
        if sets_failed else
        '\033[32mEverything OK ({} test{} in {} set{} evaluated).\033[0m'
        ''.format(
            tests_processed, '' if tests_processed == 1 else 's',
            len(sets_processed), '' if len(sets_processed) == 1 else 's'))
    if args.summary:
        for testset, n in sets_processed.items():
            print("* {} test{}, \033[{}m{} {}\033[0m `{}'".format(
                n, '' if n == 1 else 's',
                31 if testset in sets_failed else 32,
                '{} out of {}'.format(
                    sets_failed[testset], n) if testset in sets_failed else n,
                'failed' if testset in sets_failed else 'passed',
                testset))
        if len(sets_failed):
            sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])


