#!/usr/bin/env python3
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4 colorcolumn=80
#     ______________________________________ ______________________
#     \                                     | (_)     (_)    (_)   \
#      `.  http://pub.cl.uzh.ch/purl/cutter |  __________________   }
#        `-.............................____|_(                  )_/
#

import os
import regex
import yaml
import collections
import pickle

__author__ = 'Johannes Graën'
__email__ = 'graen@cl.uzh.ch'
__credits__ = """Johannes Graën, Martin Volk, Mara Bertamini,
    Chantal Amrhein, Phillip Ströbel, Anne Göhring, Michael Amsler,
    Natalia Korchagina, Simon Clematide, Daniel Wüest, Alex Flückiger,
    Magdalena Plamada, Anastassia Shaitarova, Peter Makarov"""
__license__ = 'LGPL'
__version__ = '2.5'
__status__ = 'Development'


# Flags
WHITESPACE_TOKENS = 1  # Return whitespace tokens.
EMPTY_TOKENS = 2       # Return empty tokens.
TOKENIZATION_TAGS = 4  # Show tokenization tags.

DEFAULT_FLAGS = EMPTY_TOKENS + TOKENIZATION_TAGS

# Special characters
FIRST_WORD = '\u241F'   # Marks the probable start of a new sentence.
COVER_BEGIN = '\u2402'  # Marks the begin of a covered word.
COVER_END = '\u2403'    # Marks the end of a covered word.

# Special tag for whitespace tokens
WHITESPACE_TAG = '_'

# Types of expressions
BRANCH = 1
ASSERTION = 2
META_CHAR = 3
OPTIONAL_PART = 4
WHITESPACE = 5
REGULAR_TOKEN = 6

part_expression = [
    ('\\\\\w+', BRANCH),        # e.g. \left
    ('[?][<]?[=!]', ASSERTION), # e.g. ?<!
    ('-\w+', META_CHAR),        # e.g. -marker
    ('[(].*', OPTIONAL_PART),   # e.g. (
    ('_[?]?', WHITESPACE),      # _ or _?
    ('(.*)', REGULAR_TOKEN),
]


profiles = {
    'ca': 'Catalan',
    'de': 'German',
    'en': 'English',
    'es': 'Spanish',
    'fr': 'French',
    'it': 'Italian',
    'nl': 'Dutch',
    'pt': 'Portuguese',
    'rm': 'Romansh',
    'sv': 'Swedish',
}


class CompilationError(Exception):
    def __init__(self, msg):
        Exception.__init__(self, msg)


class FormatError(Exception):
    def __init__(self, msg):
        Exception.__init__(self, msg)


class RuleSyntaxError(Exception):
    def __init__(self, msg):
        Exception.__init__(self, msg)


class LanguageProfileUndefined(Exception):
    def __init__(self, msg):
        Exception.__init__(self, msg)


class MissingFiles(Exception):
    def __init__(self, msg):
        Exception.__init__(self, msg)


class Cutter:
    """Represents a particular Cutter configuration."""

    # Private

    def _log(self, level, msg, extraindent=0):
        if self.verbosity > level:
            print('{}* {}'.format('  ' * (level+extraindent), msg))

    def _assemble_re(self, parts, letters):
        """Convert every rule part into a (matching) expression."""
        consume = False
        for i, part in enumerate(parts):
            if type(part) is dict:
                (handle, rulepart) = (
                    list(part.keys())[0],
                    list(part.values())[0])
            else:
                (handle, rulepart) = (part, None)
            self._log(
                4, "handle `{}': \033[7m{}\033[0m".format(
                    handle, rulepart or ''))
            for (re, handler) in part_expression:
                match = regex.fullmatch(re, handle)
                if match:
                    if i == 0 and handler != BRANCH:
                        # Skip letter 'a' if first part is not branching.
                        next(letters)
                    if handler == BRANCH:
                        yield ('(?<{}>{})'.format(
                            next(letters), rulepart or '.*?'), None, None)
                    elif handler == ASSERTION:
                        yield (('({}{})'.format(
                            handle, rulepart)), None, None)
                    elif handler == META_CHAR:
                        yield (('{}'.format(
                            rulepart)), None, None)
                        consume = True
                    elif handler == OPTIONAL_PART:
                        yield ('(?:', None, None)
                        yield from self._assemble_re(rulepart, letters)
                        yield (')?', None, None)
                    elif handler == WHITESPACE:
                        key = next(letters)
                        yield ('(?<{}>{})'.format(
                            key, rulepart or '\pZ{}'.format(
                                    '*' if len(handle) == 2 else '+')),
                                key, WHITESPACE_TAG)
                    elif handler == REGULAR_TOKEN:
                        key = next(letters)
                        if type(rulepart) is list:
                            rulepart = '|'.join(rulepart)
                        yield ('(?<{}>{})'.format(
                                key, rulepart or ''),
                            key, handle)
                        consume = consume or rulepart
                    else:
                        raise RuleSyntaxError(
                            "Could not handle key `{}'".format(handle))
                    break
        def does_consume():
            return consume

    def _compile_rule(self, name, parts):
        """Transform a rule into a regular expression."""
        letters = iter([char for char in 'abcdefghijklmnopqrstuvwxyz'])
        reparts = []
        tags = {}
        for repart, letter, tag in self._assemble_re(parts, letters):
            reparts.append(repart)
            if letter:
                tags[letter] = tag
            self._log(
                3, 'regex: \033[7m{}\033[0m ({})'.format(
                    repart, tag or ''))
        re = ''.join(reparts)
        try:
            rx = regex.compile(re, flags=regex.VERSION1 + regex.VERBOSE)
        except Exception as e:
            raise CompilationError(
                "Could not compile rule `{}', original regex error was "
                "`{}' at {}".format(name, e.msg, e.pos))
        self._log(
            2, "Rule `{}' compiled: \033[34m{}\033[0m".format(
                name, repr(rx)))
        return (rx, tags)

    def _cut_rec(self, text, startrule=0, level=0):
        """Apply the first matching tokenization rule, return the
        identified tokens and proceed recursively with the others.
        """
        self._log(
            1, 'Process {} character{}: \033[35;7m{}\033[0m'.format(
                len(text), '' if len(text) == 1 else 's', repr(text)),
            extraindent=level)
        for i, rule in enumerate(self.rules):
            if i < startrule:
                continue
            self._log(
                1, "Trying rule {} `{}': \033[34m{}\033[0m".format(
                    i, rule['name'], rule['rx']),
                extraindent=level)
            match = regex.fullmatch(rule['rx'], text)
            if match:
                self._log(2, 'Match:', extraindent=level)
                for letter, part in sorted(match.capturesdict().items()):
                    self._log(2, '{}: \033[33;7m{}\033[0m'.format(
                            letter, repr(part[0]) if part else '<undefined>'),
                        extraindent=level+1)
                self._log(2, 'Tags: \033[36m{}\033[0m'.format(
                        rule['tags']),
                    extraindent=level)
                for name, part in sorted(match.capturesdict().items()):
                    if part:
                        self._log(
                            3, "Start handling `{}': \033[7m{}\033[0m".format(
                                name, part),
                            extraindent=level)
                        if name in rule['tags']:
                            yield (part[0], rule['tags'][name], level)
                        else:
                            if part[0]:
                                yield from self._cut_rec(
                                    part[0],
                                    startrule=i + 1 if name == 'a' else 0,
                                    level=level + 1)
                        self._log(
                            3, "End handling `{}': \033[7m{}\033[0m".format(
                                name, part),
                            extraindent=level)
                return
        yield (text, '+final', level)

    # Public

    def __init__(self, verbosity=0, desc='', profile=None):
        self.verbosity = verbosity
        self.desc = desc
        self.abbr = set()
        self.init = set()
        self.ruletree = collections.defaultdict(
            lambda: collections.defaultdict(list))
        self.rules = []
        self.compiled = False
        self._log(0, 'New Cutter: {}'.format(
            desc if desc else '<no description>'))
        if profile is not None:
            self.load_profile(profile)

    def load_profile(self, profile):
        """Load the default profile for a language.
        """
        if not profile in profiles:
            raise LanguageProfileUndefined(
                "Profile for language `{}' undefined".format(profile))
        try:
            self.add_abbrs(open('{0}/abbr/{1}.list'.format(
                os.path.dirname(os.path.realpath(__file__)),
                profile), 'r', encoding='utf-8'))
            self.add_inits(open('{0}/init/{1}.list'.format(
                os.path.dirname(os.path.realpath(__file__)),
                profile), 'r', encoding='utf-8'))
            self.add_rules(open('{0}/rule/common.yaml'.format(
                os.path.dirname(os.path.realpath(__file__))),
                'r', encoding='utf-8'))
            self.add_rules(open('{0}/rule/{1}.yaml'.format(
                os.path.dirname(os.path.realpath(__file__)),
                profile), 'r', encoding='utf-8'))
        except IOError as exc:
            raise MissingFiles('Files missing: {}'.format(exc)) from None

    def add_abbrs(self, file):
        """Add abbreviations from file; ignore lines starting with #.
        """
        c = 0
        for line in file:
            m = regex.match('^(?!#)([^\t\n]+)', line)
            if m:
                self.abbr.add(m.captures()[0])
                self.abbr.add(
                    m.captures()[0][0].upper()
                    + m.captures()[0][1:])
                c += 1
        self._log(1, '{} abbreviation{} added'.format(
            c, '' if c == 1 else 's'))

    def add_inits(self, file):
        """Add sentence-initial words from file; ignore lines starting with #.
        """
        c = 0
        for line in file:
            m = regex.match('^(?!#)([^\t\n]+)', line)
            if m:
                self.init.add(m.captures()[0])
                c += 1
        self._log(1, '{} initial word{} added'.format(
            c, '' if c == 1 else 's'))

    def add_rules(self, file):
        """Parse rule file (written in YAML).
        """
        try:
            rstruct = yaml.load(file, Loader=yaml.FullLoader)
        except yaml.YAMLError as exc:
            raise FormatError('YAML format error: {}'.format(exc))
        c = 0
        if rstruct:
            for rname, ruleset in rstruct.items():
                m = regex.fullmatch('(.*?)(\d+)', rname)
                self.ruletree[m.captures(2)[0]][m.captures(1)[0]] = ruleset
                c += 1
            self._log(1, '{} ruleset{} added'.format(c, '' if c == 1 else 's'))
        else:
            self._log(1, 'no rulesets added')

    def compile(self):
        """Compile regular expressions for abbreviations, sentence-initial
        words and tokenization rules.
        """
        for stage, sub in sorted(self.ruletree.items()):
            for lang, ruleset in sub.items():
                for rule in ruleset:
                    rule['name'] = '({}) {}'.format(lang, rule['name'])
                    (rule['rx'], rule['tags']) = self._compile_rule(
                        rule['name'], rule['parts'])
                    self.rules.append(rule)
        self.initx = regex.compile(
            '(?<![\pL\pP])(?=(?:{})(?!\pL))'.format('|'.join(
                [regex.escape(i) for i in self.init])),
            flags=regex.VERSION1)
        abbr = list(self.abbr)
        abbr.sort()
        abbr.sort(key=lambda s: -len(s))
        self.abbrx = regex.compile(
            '(?<![\pL\d])({})(?!\pL)'.format('|'.join(
                [regex.escape(a) for a in abbr])),
            flags=regex.VERSION1 + regex.REVERSE)
        self.compiled = True

    def cut(self, text, flags=DEFAULT_FLAGS):
        """Perform tokenization and filter results according to given flags.
        """
        if not self.compiled:
            self.compile()
        self._log(
            0, 'Original text: \033[7m{}\033[0m'.format(
                repr(text)))
        if self.init:
            text = regex.sub(self.initx, '{}'.format(FIRST_WORD), text)
        self._log(
            0, 'Sentence-intial words marked: \033[7m{}\033[0m'.format(
                repr(text)))
        if self.abbr:
            text = regex.subf(self.abbrx, '{}{{}}{}'.format(
                    COVER_BEGIN, COVER_END), text)
        self._log(
            0, 'Abbreviations marked: \033[7m{}\033[0m'.format(
                repr(text)))
        pos = 0
        for token, tag, level in self._cut_rec(text):
            token = regex.sub(
                '[' + FIRST_WORD + COVER_BEGIN + COVER_END + ']', '', token)
            oldpos = pos
            pos += len(token)
            if not flags & WHITESPACE_TOKENS and tag == WHITESPACE_TAG:
                continue
            if token == '' and (
                    not flags & EMPTY_TOKENS or tag == WHITESPACE_TAG):
                continue
            yield (token, tag, level, oldpos, pos)

    def cut_and_pack(self, text, flags=DEFAULT_FLAGS):
        """Perform tokenization and split the result on sentence boundaries.
        """
        sentence = []
        for token, tag, level, oldpos, pos in self.cut(text, flags):
            if tag[:4] == '+EOS':
                if sentence:
                    yield (sentence)
                sentence = []
            else:
                sentence.append((token, tag, level, oldpos, pos))
        if sentence:
            yield (sentence)




