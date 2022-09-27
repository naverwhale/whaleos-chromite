# -*- coding: utf-8 -*-
# Copyright (c) 2006-2014 LOGILAB S.A. (Paris, FRANCE) <contact@logilab.fr>
# Copyright (c) 2012-2015 Google, Inc.
# Copyright (c) 2013 moxian <aleftmail@inbox.ru>
# Copyright (c) 2014-2019 Claudiu Popa <pcmanticore@gmail.com>
# Copyright (c) 2014 frost-nzcr4 <frost.nzcr4@jagmort.com>
# Copyright (c) 2014 Brett Cannon <brett@python.org>
# Copyright (c) 2014 Michal Nowikowski <godfryd@gmail.com>
# Copyright (c) 2014 Arun Persaud <arun@nubati.net>
# Copyright (c) 2015 Mike Frysinger <vapier@gentoo.org>
# Copyright (c) 2015 Fabio Natali <me@fabionatali.com>
# Copyright (c) 2015 Harut <yes@harutune.name>
# Copyright (c) 2015 Mihai Balint <balint.mihai@gmail.com>
# Copyright (c) 2015 Pavel Roskin <proski@gnu.org>
# Copyright (c) 2015 Ionel Cristian Maries <contact@ionelmc.ro>
# Copyright (c) 2016 Petr Pulc <petrpulc@gmail.com>
# Copyright (c) 2016 Moises Lopez <moylop260@vauxoo.com>
# Copyright (c) 2016 Ashley Whetter <ashley@awhetter.co.uk>
# Copyright (c) 2017, 2019 hippo91 <guillaume.peillex@gmail.com>
# Copyright (c) 2017-2018 Bryce Guinta <bryce.paul.guinta@gmail.com>
# Copyright (c) 2017 Krzysztof Czapla <k.czapla68@gmail.com>
# Copyright (c) 2017 Łukasz Rogalski <rogalski.91@gmail.com>
# Copyright (c) 2017 James M. Allen <james.m.allen@gmail.com>
# Copyright (c) 2017 vinnyrose <vinnyrose@users.noreply.github.com>
# Copyright (c) 2018-2020 Pierre Sassoulas <pierre.sassoulas@gmail.com>
# Copyright (c) 2018 Pierre Sassoulas <pierre.sassoulas@wisebim.fr>
# Copyright (c) 2018, 2020 Anthony Sottile <asottile@umich.edu>
# Copyright (c) 2018 Lucas Cimon <lucas.cimon@gmail.com>
# Copyright (c) 2018 Michael Hudson-Doyle <michael.hudson@canonical.com>
# Copyright (c) 2018 Natalie Serebryakova <natalie.serebryakova@Natalies-MacBook-Pro.local>
# Copyright (c) 2018 ssolanki <sushobhitsolanki@gmail.com>
# Copyright (c) 2018 Marcus Näslund <naslundx@gmail.com>
# Copyright (c) 2018 Bryce Guinta <bryce.guinta@protonmail.com>
# Copyright (c) 2018 Mike Frysinger <vapier@gmail.com>
# Copyright (c) 2018 Fureigh <rhys.fureigh@gsa.gov>
# Copyright (c) 2018 Andreas Freimuth <andreas.freimuth@united-bits.de>
# Copyright (c) 2018 Jakub Wilk <jwilk@jwilk.net>
# Copyright (c) 2019 Nick Drozd <nicholasdrozd@gmail.com>
# Copyright (c) 2019 Hugo van Kemenade <hugovk@users.noreply.github.com>

# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/PyCQA/pylint/blob/master/COPYING

"""Python code format's checker.

By default try to follow Guido's style guide :

https://www.python.org/doc/essays/styleguide/

Some parts of the process_token method is based from The Tab Nanny std module.
"""

import keyword
import tokenize

from pylint.checkers import BaseTokenChecker
from pylint.interfaces import IAstroidChecker, IRawChecker, ITokenChecker

_ASYNC_TOKEN = "async"
_CONTINUATION_BLOCK_OPENERS = [
    "elif",
    "except",
    "for",
    "if",
    "while",
    "def",
    "class",
    "with",
]
_KEYWORD_TOKENS = [
    "assert",
    "del",
    "elif",
    "except",
    "for",
    "if",
    "in",
    "not",
    "raise",
    "return",
    "while",
    "yield",
    "with",
]

_SPACED_OPERATORS = [
    "==",
    "<",
    ">",
    "!=",
    "<>",
    "<=",
    ">=",
    "+=",
    "-=",
    "*=",
    "**=",
    "/=",
    "//=",
    "&=",
    "|=",
    "^=",
    "%=",
    ">>=",
    "<<=",
]
_OPENING_BRACKETS = ["(", "[", "{"]
_CLOSING_BRACKETS = [")", "]", "}"]
_TAB_LENGTH = 8

_EOL = frozenset([tokenize.NEWLINE, tokenize.NL, tokenize.COMMENT])
_JUNK_TOKENS = (tokenize.COMMENT, tokenize.NL)

# Whitespace checking policy constants
_MUST = 0
_MUST_NOT = 1
_IGNORE = 2

# Whitespace checking config constants
_DICT_SEPARATOR = "dict-separator"
_TRAILING_COMMA = "trailing-comma"
_EMPTY_LINE = "empty-line"
_NO_SPACE_CHECK_CHOICES = [_TRAILING_COMMA, _DICT_SEPARATOR, _EMPTY_LINE]
_DEFAULT_NO_SPACE_CHECK_CHOICES = [_TRAILING_COMMA, _DICT_SEPARATOR]

MSGS = {
    "C0330": ("Wrong %s indentation%s%s.\n%s%s", "bad-continuation", "TODO"),
    "C0326": (
        "%s space %s %s %s\n%s",
        "bad-whitespace",
        (
            "Used when a wrong number of spaces is used around an operator, "
            "bracket or block opener."
        ),
        {
            "old_names": [
                ("C0323", "no-space-after-operator"),
                ("C0324", "no-space-after-comma"),
                ("C0322", "no-space-before-operator"),
            ]
        },
    ),
}


def _underline_token(token):
    length = token[3][1] - token[2][1]
    offset = token[2][1]
    referenced_line = token[4]
    # If the referenced line does not end with a newline char, fix it
    if referenced_line[-1] != "\n":
        referenced_line += "\n"
    return referenced_line + (" " * offset) + ("^" * length)


def _column_distance(token1, token2):
    if token1 == token2:
        return 0
    if token2[3] < token1[3]:
        token1, token2 = token2, token1
    if token1[3][0] != token2[2][0]:
        return None
    return token2[2][1] - token1[3][1]


def _last_token_on_line_is(tokens, line_end, token):
    return (
        line_end > 0
        and tokens.token(line_end - 1) == token
        or line_end > 1
        and tokens.token(line_end - 2) == token
        and tokens.type(line_end - 1) == tokenize.COMMENT
    )


def _token_followed_by_eol(tokens, position):
    return (
        tokens.type(position + 1) == tokenize.NL
        or tokens.type(position + 1) == tokenize.COMMENT
        and tokens.type(position + 2) == tokenize.NL
    )


def _get_indent_string(line):
    """Return the indention string of the given line."""
    result = ""
    for char in line:
        if char in " \t":
            result += char
        else:
            break
    return result


def _get_indent_length(line):
    """Return the length of the indentation on the given token's line."""
    result = 0
    for char in line:
        if char == " ":
            result += 1
        elif char == "\t":
            result += _TAB_LENGTH
        else:
            break
    return result


def _get_indent_hint_line(bar_positions, bad_position):
    """Return a line with |s for each of the positions in the given lists."""
    if not bar_positions:
        return "", ""

    bar_positions = [_get_indent_length(indent) for indent in bar_positions]
    bad_position = _get_indent_length(bad_position)
    delta_message = ""
    markers = [(pos, "|") for pos in bar_positions]
    if len(markers) == 1:
        # if we have only one marker we'll provide an extra hint on how to fix
        expected_position = markers[0][0]
        delta = abs(expected_position - bad_position)
        direction = "add" if expected_position > bad_position else "remove"
        delta_message = _CONTINUATION_HINT_MESSAGE % (
            direction,
            delta,
            "s" if delta > 1 else "",
        )
    markers.append((bad_position, "^"))
    markers.sort()
    line = [" "] * (markers[-1][0] + 1)
    for position, marker in markers:
        line[position] = marker
    return "".join(line), delta_message


class _ContinuedIndent:
    __slots__ = (
        "valid_outdent_strings",
        "valid_continuation_strings",
        "context_type",
        "token",
        "position",
    )

    def __init__(
        self,
        context_type,
        token,
        position,
        valid_outdent_strings,
        valid_continuation_strings,
    ):
        self.valid_outdent_strings = valid_outdent_strings
        self.valid_continuation_strings = valid_continuation_strings
        self.context_type = context_type
        self.position = position
        self.token = token


# The contexts for hanging indents.
# A hanging indented dictionary value after :
HANGING_DICT_VALUE = "dict-value"
# Hanging indentation in an expression.
HANGING = "hanging"
# Hanging indentation in a block header.
HANGING_BLOCK = "hanging-block"
# Continued indentation inside an expression.
CONTINUED = "continued"
# Continued indentation in a block header.
CONTINUED_BLOCK = "continued-block"

SINGLE_LINE = "single"
WITH_BODY = "multi"

_CONTINUATION_MSG_PARTS = {
    HANGING_DICT_VALUE: ("hanging", " in dict value"),
    HANGING: ("hanging", ""),
    HANGING_BLOCK: ("hanging", " before block"),
    CONTINUED: ("continued", ""),
    CONTINUED_BLOCK: ("continued", " before block"),
}

_CONTINUATION_HINT_MESSAGE = " (%s %d space%s)"  # Ex: (remove 2 spaces)


def _Indentations(*args):
    """Valid indentation strings for a continued line."""
    return {a: None for a in args}


def _BeforeBlockIndentations(single, with_body):
    """Valid alternative indentation strings for continued lines before blocks.

    :param int single: Valid indentation string for statements on a single logical line.
    :param int with_body: Valid indentation string for statements on several lines.

    :returns: A dictionary mapping indent offsets to a string representing
        whether the indent if for a line or block.
    :rtype: dict
    """
    return {single: SINGLE_LINE, with_body: WITH_BODY}


class TokenWrapper:
    """A wrapper for readable access to token information."""

    def __init__(self, tokens):
        self._tokens = tokens

    def token(self, idx):
        return self._tokens[idx][1]

    def type(self, idx):
        return self._tokens[idx][0]

    def start_line(self, idx):
        return self._tokens[idx][2][0]

    def start_col(self, idx):
        return self._tokens[idx][2][1]

    def line(self, idx):
        return self._tokens[idx][4]

    def line_indent(self, idx):
        """Get the string of TABs and Spaces used for indentation of the line of this token"""
        return _get_indent_string(self.line(idx))

    def token_indent(self, idx):
        """Get an indentation string for hanging indentation, consisting of the line-indent plus
        a number of spaces to fill up to the column of this token.

        e.g. the token indent for foo
        in "<TAB><TAB>print(foo)"
        is "<TAB><TAB>      "
        """
        line_indent = self.line_indent(idx)
        return line_indent + " " * (self.start_col(idx) - len(line_indent))


class ContinuedLineState:
    """Tracker for continued indentation inside a logical line."""

    def __init__(self, tokens, config):
        self._line_start = -1
        self._cont_stack = []
        self._is_block_opener = False
        self.retained_warnings = []
        self._config = config
        self._tokens = TokenWrapper(tokens)

    @property
    def has_content(self):
        return bool(self._cont_stack)

    @property
    def _block_indent_string(self):
        return self._config.indent_string.replace("\\t", "\t")

    @property
    def _continuation_string(self):
        return self._block_indent_string[0] * self._config.indent_after_paren

    def handle_line_start(self, pos):
        """Record the first non-junk token at the start of a line."""
        if self._line_start > -1:
            return

        check_token_position = pos
        if self._tokens.token(pos) == _ASYNC_TOKEN:
            check_token_position += 1
        self._is_block_opener = (
            self._tokens.token(check_token_position) in _CONTINUATION_BLOCK_OPENERS
        )
        self._line_start = pos

    def next_physical_line(self):
        """Prepares the tracker for a new physical line (NL)."""
        self._line_start = -1
        self._is_block_opener = False

    def next_logical_line(self):
        """Prepares the tracker for a new logical line (NEWLINE).

        A new logical line only starts with block indentation.
        """
        self.next_physical_line()
        self.retained_warnings = []
        self._cont_stack = []

    def add_block_warning(self, token_position, state, valid_indentations):
        self.retained_warnings.append((token_position, state, valid_indentations))

    def get_valid_indentations(self, idx):
        """Returns the valid offsets for the token at the given position."""
        # The closing brace on a dict or the 'for' in a dict comprehension may
        # reset two indent levels because the dict value is ended implicitly
        stack_top = -1
        if (
            self._tokens.token(idx) in ("}", "for")
            and self._cont_stack[-1].token == ":"
        ):
            stack_top = -2
        indent = self._cont_stack[stack_top]
        if self._tokens.token(idx) in _CLOSING_BRACKETS:
            valid_indentations = indent.valid_outdent_strings
        else:
            valid_indentations = indent.valid_continuation_strings
        return indent, valid_indentations.copy()

    def _hanging_indent_after_bracket(self, bracket, position):
        """Extracts indentation information for a hanging indent

        Case of hanging indent after a bracket (including parenthesis)

        :param str bracket: bracket in question
        :param int position: Position of bracket in self._tokens

        :returns: the state and valid positions for hanging indentation
        :rtype: _ContinuedIndent
        """
        indentation = self._tokens.line_indent(position)
        if (
            self._is_block_opener
            and self._continuation_string == self._block_indent_string
        ):
            return _ContinuedIndent(
                HANGING_BLOCK,
                bracket,
                position,
                _Indentations(indentation + self._continuation_string, indentation),
                _BeforeBlockIndentations(
                    indentation + self._continuation_string,
                    indentation + self._continuation_string * 2,
                ),
            )
        if bracket == ":":
            # If the dict key was on the same line as the open brace, the new
            # correct indent should be relative to the key instead of the
            # current indent level
            paren_align = self._cont_stack[-1].valid_outdent_strings
            next_align = self._cont_stack[-1].valid_continuation_strings.copy()
            next_align_keys = list(next_align.keys())
            next_align[next_align_keys[0] + self._continuation_string] = True
            # Note that the continuation of
            # d = {
            #       'a': 'b'
            #            'c'
            # }
            # is handled by the special-casing for hanging continued string indents.
            return _ContinuedIndent(
                HANGING_DICT_VALUE, bracket, position, paren_align, next_align
            )
        return _ContinuedIndent(
            HANGING,
            bracket,
            position,
            _Indentations(indentation, indentation + self._continuation_string),
            _Indentations(indentation + self._continuation_string),
        )

    def _continuation_inside_bracket(self, bracket, position):
        """Extracts indentation information for a continued indent."""
        indentation = self._tokens.line_indent(position)
        token_indent = self._tokens.token_indent(position)
        next_token_indent = self._tokens.token_indent(position + 1)
        if (
            self._is_block_opener
            and next_token_indent == indentation + self._block_indent_string
        ):
            return _ContinuedIndent(
                CONTINUED_BLOCK,
                bracket,
                position,
                _Indentations(token_indent),
                _BeforeBlockIndentations(
                    next_token_indent, next_token_indent + self._continuation_string
                ),
            )
        return _ContinuedIndent(
            CONTINUED,
            bracket,
            position,
            _Indentations(token_indent, next_token_indent),
            _Indentations(next_token_indent),
        )

    def pop_token(self):
        self._cont_stack.pop()

    def push_token(self, token, position):
        """Pushes a new token for continued indentation on the stack.

        Tokens that can modify continued indentation offsets are:
          * opening brackets
          * 'lambda'
          * : inside dictionaries

        push_token relies on the caller to filter out those
        interesting tokens.

        :param int token: The concrete token
        :param int position: The position of the token in the stream.
        """
        if _token_followed_by_eol(self._tokens, position):
            self._cont_stack.append(self._hanging_indent_after_bracket(token, position))
        else:
            self._cont_stack.append(self._continuation_inside_bracket(token, position))


class FormatChecker(BaseTokenChecker):
    """checks for :
    * unauthorized constructions
    * strict indentation
    * line length
    """

    __implements__ = (ITokenChecker, IAstroidChecker, IRawChecker)

    # configuration section name
    name = "format"
    # messages
    msgs = MSGS
    # configuration options
    # for available dict keys/values see the optik parser 'add_option' method
    options = (
        (
            "no-space-check",
            {
                "default": ",".join(_DEFAULT_NO_SPACE_CHECK_CHOICES),
                "metavar": ",".join(_NO_SPACE_CHECK_CHOICES),
                "type": "multiple_choice",
                "choices": _NO_SPACE_CHECK_CHOICES,
                "help": (
                    "List of optional constructs for which whitespace "
                    "checking is disabled. "
                    "`" + _DICT_SEPARATOR + "` is used to allow tabulation "
                    "in dicts, etc.: {1  : 1,\\n222: 2}. "
                    "`" + _TRAILING_COMMA + "` allows a space between comma "
                    "and closing bracket: (a, ). "
                    "`" + _EMPTY_LINE + "` allows space-only lines."
                ),
            },
        ),
    )

    def __init__(self, linter=None, config=None):
        BaseTokenChecker.__init__(self, linter)
        self._bracket_stack = [None]
        self.config = config

    def _pop_token(self):
        self._bracket_stack.pop()
        self._current_line.pop_token()

    def _push_token(self, token, idx):
        self._bracket_stack.append(token)
        self._current_line.push_token(token, idx)

    def process_module(self, _module):
        self._keywords_with_parens = set()

    def _opening_bracket(self, tokens, i):
        self._push_token(tokens[i][1], i)
        # Special case: ignore slices
        if tokens[i][1] == "[" and tokens[i + 1][1] == ":":
            return

        if i > 0 and (
            tokens[i - 1][0] == tokenize.NAME
            and not (keyword.iskeyword(tokens[i - 1][1]))
            or tokens[i - 1][1] in _CLOSING_BRACKETS
        ):
            self._check_space(tokens, i, (_MUST_NOT, _MUST_NOT))
        else:
            self._check_space(tokens, i, (_IGNORE, _MUST_NOT))

    def _closing_bracket(self, tokens, i):
        if self._inside_brackets(":"):
            self._pop_token()
        self._pop_token()
        # Special case: ignore slices
        if tokens[i - 1][1] == ":" and tokens[i][1] == "]":
            return
        policy_before = _MUST_NOT
        if tokens[i][1] in _CLOSING_BRACKETS and tokens[i - 1][1] == ",":
            if _TRAILING_COMMA in self.config.no_space_check:
                policy_before = _IGNORE

        self._check_space(tokens, i, (policy_before, _IGNORE))

    def _has_valid_type_annotation(self, tokens, i):
        """Extended check of PEP-484 type hint presence"""
        if not self._inside_brackets("("):
            return False
        # token_info
        # type string start end line
        #  0      1     2    3    4
        bracket_level = 0
        for token in tokens[i - 1 :: -1]:
            if token[1] == ":":
                return True
            if token[1] == "(":
                return False
            if token[1] == "]":
                bracket_level += 1
            elif token[1] == "[":
                bracket_level -= 1
            elif token[1] == ",":
                if not bracket_level:
                    return False
            elif token[1] in (".", "..."):
                continue
            elif token[0] not in (tokenize.NAME, tokenize.STRING, tokenize.NL):
                return False
        return False

    def _check_equals_spacing(self, tokens, i):
        """Check the spacing of a single equals sign."""
        if self._has_valid_type_annotation(tokens, i):
            self._check_space(tokens, i, (_MUST, _MUST))
        elif self._inside_brackets("(") or self._inside_brackets("lambda"):
            self._check_space(tokens, i, (_MUST_NOT, _MUST_NOT))
        else:
            self._check_space(tokens, i, (_MUST, _MUST))

    def _open_lambda(self, tokens, i):  # pylint:disable=unused-argument
        self._push_token("lambda", i)

    def _handle_colon(self, tokens, i):
        # Special case: ignore slices
        if self._inside_brackets("["):
            return
        if self._inside_brackets("{") and _DICT_SEPARATOR in self.config.no_space_check:
            policy = (_IGNORE, _IGNORE)
        else:
            policy = (_MUST_NOT, _MUST)
        self._check_space(tokens, i, policy)

        if self._inside_brackets("lambda"):
            self._pop_token()
        elif self._inside_brackets("{"):
            self._push_token(":", i)

    def _handle_comma(self, tokens, i):
        # Only require a following whitespace if this is
        # not a hanging comma before a closing bracket.
        if tokens[i + 1][1] in _CLOSING_BRACKETS:
            self._check_space(tokens, i, (_MUST_NOT, _IGNORE))
        else:
            self._check_space(tokens, i, (_MUST_NOT, _MUST))
        if self._inside_brackets(":"):
            self._pop_token()

    def _check_surrounded_by_space(self, tokens, i):
        """Check that a binary operator is surrounded by exactly one space."""
        self._check_space(tokens, i, (_MUST, _MUST))

    def _check_space(self, tokens, i, policies):
        def _policy_string(policy):
            if policy == _MUST:
                return "Exactly one", "required"
            return "No", "allowed"

        def _name_construct(token):
            if token[1] == ",":
                return "comma"
            if token[1] == ":":
                return ":"
            if token[1] in "()[]{}":
                return "bracket"
            if token[1] in ("<", ">", "<=", ">=", "!=", "=="):
                return "comparison"
            if self._inside_brackets("("):
                return "keyword argument assignment"
            return "assignment"

        good_space = [True, True]
        token = tokens[i]
        pairs = [(tokens[i - 1], token), (token, tokens[i + 1])]

        for other_idx, (policy, token_pair) in enumerate(zip(policies, pairs)):
            if token_pair[other_idx][0] in _EOL or policy == _IGNORE:
                continue

            distance = _column_distance(*token_pair)
            if distance is None:
                continue
            good_space[other_idx] = (policy == _MUST and distance == 1) or (
                policy == _MUST_NOT and distance == 0
            )

        warnings = []
        if not any(good_space) and policies[0] == policies[1]:
            warnings.append((policies[0], "around"))
        else:
            for ok, policy, position in zip(good_space, policies, ("before", "after")):
                if not ok:
                    warnings.append((policy, position))
        for policy, position in warnings:
            construct = _name_construct(token)
            count, state = _policy_string(policy)
            self.add_message(
                "bad-whitespace",
                line=token[2][0],
                args=(count, state, position, construct, _underline_token(token)),
                col_offset=token[2][1],
            )

    def _inside_brackets(self, left):
        return self._bracket_stack[-1] == left

    def _prepare_token_dispatcher(self):
        raw = [
            (_OPENING_BRACKETS, self._opening_bracket),
            (_CLOSING_BRACKETS, self._closing_bracket),
            (["="], self._check_equals_spacing),
            (_SPACED_OPERATORS, self._check_surrounded_by_space),
            ([","], self._handle_comma),
            ([":"], self._handle_colon),
            (["lambda"], self._open_lambda),
        ]

        dispatch = {}
        for tokens, handler in raw:
            for token in tokens:
                dispatch[token] = handler
        return dispatch

    def process_tokens(self, tokens):
        """process tokens and search for :

         _ non strict indentation (i.e. not always using the <indent> parameter as
           indent unit)
         _ too long lines (i.e. longer than <max_chars>)
         _ optionally bad construct (if given, bad_construct must be a compiled
           regular expression).
        """
        self._bracket_stack = [None]
        indents = [0]
        check_equal = False
        line_num = 0
        token_handlers = self._prepare_token_dispatcher()
        last_blank_line_num = 0

        self._current_line = ContinuedLineState(tokens, self.config)
        for idx, (tok_type, token, start, _, line) in enumerate(tokens):
            if start[0] != line_num:
                line_num = start[0]

            if tok_type == tokenize.NEWLINE:
                # a program statement, or ENDMARKER, will eventually follow,
                # after some (possibly empty) run of tokens of the form
                #     (NL | COMMENT)* (INDENT | DEDENT+)?
                # If an INDENT appears, setting check_equal is wrong, and will
                # be undone when we see the INDENT.
                check_equal = True
                self._process_retained_warnings(TokenWrapper(tokens), idx)
                self._current_line.next_logical_line()
            elif tok_type == tokenize.INDENT:
                check_equal = False
                indents.append(indents[-1] + 1)
            elif tok_type == tokenize.DEDENT:
                # there's nothing we need to check here!  what's important is
                # that when the run of DEDENTs ends, the indentation of the
                # program statement (or ENDMARKER) that triggered the run is
                # equal to what's left at the top of the indents stack
                check_equal = True
                if len(indents) > 1:
                    del indents[-1]
            elif tok_type == tokenize.NL:
                if not line.strip("\r\n"):
                    last_blank_line_num = line_num
                self._check_continued_indentation(TokenWrapper(tokens), idx + 1)
                self._current_line.next_physical_line()
            elif tok_type not in (tokenize.COMMENT, tokenize.ENCODING):
                self._current_line.handle_line_start(idx)

            if tok_type == tokenize.NUMBER and token.endswith("l"):
                self.add_message("lowercase-l-suffix", line=line_num)

            try:
                handler = token_handlers[token]
            except KeyError:
                pass
            else:
                handler(tokens, idx)

        line_num -= 1  # to be ok with "wc -l"

    def _process_retained_warnings(self, tokens, current_pos):
        single_line_block_stmt = not _last_token_on_line_is(tokens, current_pos, ":")

        for indent_pos, state, indentations in self._current_line.retained_warnings:
            block_type = indentations[tokens.token_indent(indent_pos)]
            hints = {k: v for k, v in indentations.items() if v != block_type}
            if single_line_block_stmt and block_type == WITH_BODY:
                self._add_continuation_message(state, hints, tokens, indent_pos)
            elif not single_line_block_stmt and block_type == SINGLE_LINE:
                self._add_continuation_message(state, hints, tokens, indent_pos)

    def _check_continued_indentation(self, tokens, next_idx):
        def same_token_around_nl(token_type):
            return (
                tokens.type(next_idx) == token_type
                and tokens.type(next_idx - 2) == token_type
            )

        # Do not issue any warnings if the next line is empty.
        if not self._current_line.has_content or tokens.type(next_idx) == tokenize.NL:
            return

        state, valid_indentations = self._current_line.get_valid_indentations(next_idx)
        # Special handling for hanging comments and strings. If the last line ended
        # with a comment (string) and the new line contains only a comment, the line
        # may also be indented to the start of the previous token.
        if same_token_around_nl(tokenize.COMMENT) or same_token_around_nl(
            tokenize.STRING
        ):
            valid_indentations[tokens.token_indent(next_idx - 2)] = True

        # We can only decide if the indentation of a continued line before opening
        # a new block is valid once we know of the body of the block is on the
        # same line as the block opener. Since the token processing is single-pass,
        # emitting those warnings is delayed until the block opener is processed.
        if (
            state.context_type in (HANGING_BLOCK, CONTINUED_BLOCK)
            and tokens.token_indent(next_idx) in valid_indentations
        ):
            self._current_line.add_block_warning(next_idx, state, valid_indentations)
        elif tokens.token_indent(next_idx) not in valid_indentations:
            length_indentation = len(tokens.token_indent(next_idx))
            if not any(
                length_indentation == 2 * len(indentation)
                for indentation in valid_indentations
            ):
                self._add_continuation_message(
                    state, valid_indentations, tokens, next_idx
                )

    def _add_continuation_message(self, state, indentations, tokens, position):
        readable_type, readable_position = _CONTINUATION_MSG_PARTS[state.context_type]
        hint_line, delta_message = _get_indent_hint_line(
            indentations, tokens.token_indent(position)
        )
        self.add_message(
            "bad-continuation",
            line=tokens.start_line(position),
            args=(
                readable_type,
                readable_position,
                delta_message,
                tokens.line(position),
                hint_line,
            ),
        )


class Config:
    def __init__(self, cfg):
        #self.config.no_space_check: = cfg.option_value('no-space-check')
        self.indent_string = cfg.option_value('indent-string')
        self.indent_after_paren = cfg.option_value('indent-after-paren')


def register(linter, config):
    """required method to auto register this checker """
    linter.register_checker(FormatChecker(linter, Config(config)))
