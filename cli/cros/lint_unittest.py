# Copyright 2013 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the lint module."""

import collections
import io
import os
from typing import Iterable, List, NamedTuple, Optional

import astroid

from chromite.cli.cros import lint
from chromite.lib import cros_test_lib
from chromite.lib import osutils


# pylint: disable=protected-access


class DocStringSectionDetailsTest(cros_test_lib.TestCase):
    """Basic DocStringSectionDetails class tests."""

    def testInit(self):
        """Verify constructor behavior."""
        s = lint.DocStringSectionDetails()
        self.assertEqual(None, s.name)
        self.assertEqual(None, s.header)
        self.assertEqual([], s.lines)
        self.assertEqual(None, s.lineno)

        s = lint.DocStringSectionDetails(
            name="Args", header="  Args:", lines=["    foo: Yes."], lineno=2
        )
        self.assertEqual("Args", s.name)
        self.assertEqual("  Args:", s.header)
        self.assertEqual(["    foo: Yes."], s.lines)
        self.assertEqual(2, s.lineno)

    def testStr(self):
        """Sanity check __str__."""
        s = lint.DocStringSectionDetails()
        self.assertNotEqual(None, str(s))

    def testRepr(self):
        """Sanity check __repr__."""
        s = lint.DocStringSectionDetails()
        self.assertNotEqual(None, repr(s))

    def testEqual(self):
        """Sanity check __eq__."""
        s1 = lint.DocStringSectionDetails()
        s2 = lint.DocStringSectionDetails()
        self.assertEqual(s1, s2)

        s2 = lint.DocStringSectionDetails(name="Args")
        self.assertNotEqual(s1, s2)
        s2 = lint.DocStringSectionDetails(header="  Args:")
        self.assertNotEqual(s1, s2)
        s2 = lint.DocStringSectionDetails(lineno=2)
        self.assertNotEqual(s1, s2)

        s1 = lint.DocStringSectionDetails(name="n", header="h", lineno=0)
        s2 = lint.DocStringSectionDetails(name="n", header="h", lineno=0)
        self.assertEqual(s1, s2)


class PylintrcConfigTest(cros_test_lib.TempDirTestCase):
    """Basic _PylintrcConfig tests."""

    def testEmptySettings(self):
        """Check default empty names behavior."""
        lint._PylintrcConfig("/dev/null", "", ())

    def testDefaultValue(self):
        """Check we can read a default."""
        cfg_file = os.path.join(self.tempdir, "pylintrc")
        osutils.WriteFile(cfg_file, '[sect]\nkey = "  "\n')
        cfg = lint._PylintrcConfig(
            cfg_file,
            "sect",
            (
                ("key", {"default": "KEY", "type": "string"}),
                ("foo", {"default": "FOO", "type": "string"}),
            ),
        )
        self.assertEqual("  ", cfg.option_value("key"))
        self.assertEqual("FOO", cfg.option_value("foo"))


class TestNode:
    """Object good enough to stand in for lint funcs"""

    Args = collections.namedtuple(
        "Args", ("args", "vararg", "kwarg", "kwonlyargs")
    )
    Arg = collections.namedtuple("Arg", ("name",))

    def __init__(
        self,
        doc="",
        fromlineno=0,
        path="foo.py",
        args=(),
        vararg=None,
        kwarg=None,
        kwonlyargs=(),
        names=None,
        lineno=0,
        name="module",
        display_type="Module",
        col_offset=None,
    ):
        if names is None:
            names = [("name", None)]
        self.doc = doc
        self.lines = doc.split("\n")
        self.fromlineno = fromlineno
        self.lineno = lineno
        self.file = path
        self.args = self.Args(
            args=[self.Arg(name=x) for x in args],
            vararg=vararg,
            kwarg=kwarg,
            kwonlyargs=kwonlyargs,
        )
        self.names = names
        self.name = name
        self._display_type = display_type
        self.col_offset = col_offset

    def argnames(self):
        return [arg.name for arg in self.args.args]

    def display_type(self):
        return self._display_type


class StatStub:
    """Stub object to stand in for stat checks."""

    def __init__(self, size=0, mode=0o644):
        self.st_size = size
        self.st_mode = mode


class CheckerTestCase(cros_test_lib.TestCase):
    """Helpers for Checker modules"""

    def add_message(
        self, msg_id, node=None, line=None, col_offset=None, args=None
    ):
        """Capture lint checks"""
        # We include node.doc here explicitly so the pretty assert message
        # inclues it in the output automatically.
        doc = node.doc if node else ""
        # Copy args since some functions mutate it after calling `add_message`.
        # Shallow copies should be fine, since all the values we store are
        # immutable.
        if args is not None:
            args = args.copy()
        self.results.append((msg_id, doc, line, args, col_offset))

    def setUp(self):
        assert hasattr(self, "CHECKER"), "TestCase must set CHECKER"

        self.results = []
        self.checker = self.CHECKER()
        self.checker.add_message = self.add_message

    def assertLintPassed(self, msg="Checks failed"):
        """Assert that no lint results have been queued."""
        msg += "\nChecks failed: %s" % ([x[0] for x in self.results],)
        self.assertEqual(self.results, [], msg=msg)

    def assertLintFailed(self, msg="Checks incorrectly passed", expected=()):
        """Assert that failed results matching |expected| have been queued."""
        if expected:
            self.assertEqual(list(expected), [x[0] for x in self.results])
        else:
            self.assertNotEqual(len(self.results), 0, msg=msg)


class DocStringCheckerTest(CheckerTestCase):
    """Tests for DocStringChecker module"""

    GOOD_FUNC_DOCSTRINGS = (
        "Some string",
        """Short summary

      Body of text.
      """,
        """line o text

      Body and comments on
      more than one line.

      Args:
        moo: cow

      Returns:
        some value

      Raises:
        something else
      """,
        """Short summary.

      Args:
        fat: cat

      Yields:
        a spoon
      """,
        """Don't flag args variables as sections.

      Args:
        return: Foo!
      """,
        """the indentation is extra special

      Returns:
        First line is two spaces which is ok.
          Then we indent some more!
      """,
        """Arguments with same names as sections.

      Args:
        result: Valid arg, invalid section.
        return: Valid arg, invalid section.
        returns: Valid arg, valid section.
        arg: Valid arg, invalid section.
        args: Valid arg, valid section.
        attribute: Valid arg, invalid section.
        attributes: Valid arg, valid section.
      """,
    )

    BAD_FUNC_DOCSTRINGS = (
        """
      bad first line
      """,
        """The first line is good
      but the second one isn't
      """,
        """ whitespace is wrong""",
        """whitespace is wrong	""",
        """ whitespace is wrong

      Multiline tickles differently.
      """,
        """First line is OK, but too much trailing whitespace

      """,
        """Should be no trailing blank lines

      Returns:
        a value

      """,
        """ok line

      cuddled end""",
        """we want Args, not Arguments

      Arguments:
        some: arg
      """,
        """we want Args, not Params

      Params:
        some: arg
      """,
        """section order is wrong here

      Raises:
        It raised.

      Returns:
        It returned
      """,
        """sections are duplicated

      Returns:
        True

      Returns:
        or was it false
      """,
        """sections lack whitespace between them

      Args:
        foo: bar
      Returns:
        yeah
      """,
        """yields is misspelled

      Yield:
        a car
      """,
        """We want Examples, not Usage.

      Usage:
        a car
      """,
        """Section name has bad spacing

      Args:\x20\x20\x20
        key: here
      """,
        """too many blank lines


      Returns:
        None
      """,
        """wrongly uses javadoc

      @returns None
      """,
        """the indentation is incorrect

        Args:
          some: day
      """,
        """the final indentation is incorrect

      Blah.
       """,
        """the indentation is incorrect

      Returns:
       one space but should be two
      """,
        """the indentation is incorrect

      Returns:
         three spaces but should be two (and we have just one line)
      """,
        """the indentation is incorrect

      Args:
         some: has three spaces but should be two
      """,
        """the indentation is incorrect

      Args:
       some: has one space but should be two
      """,
        """the indentation is incorrect

      Args:
          some: has four spaces but should be two
      """,
        """"Extra leading quotes.""",
        """Class-only sections aren't allowed.

      Attributes:
        foo: bar.
      """,
        """No lines between section headers & keys.

      Args:

        arg: No blank line above!
      """,
    )

    # The current linter isn't good enough yet to detect these.
    TODO_BAD_FUNC_DOCSTRINGS = (
        """The returns section isn't a proper section

      Args:
        bloop: de

      returns something
      """,
        """Too many spaces after header.

      Args:
        arg:  too many spaces
      """,
    )

    # We don't need to test most scenarios as the func & class checkers share
    # code.  Only test the differences.
    GOOD_CLASS_DOCSTRINGS = (
        """Basic class.""",
        """Class with attributes.

      Attributes:
        foo: bar
      """,
        """Class with examples.

      Examples:
        Do stuff.
      """,
        """Class with examples & attributes.

      Examples:
        Do stuff.

      Attributes:
        foo: bar
      """,
        """Attributes with same names as sections.

      Attributes:
        result: Valid arg, invalid section.
        return: Valid arg, invalid section.
        returns: Valid arg, valid section.
        arg: Valid arg, invalid section.
        args: Valid arg, valid section.
        attribute: Valid arg, invalid section.
        attributes: Valid arg, valid section.
      """,
    )

    BAD_CLASS_DOCSTRINGS = (
        """Class with wrong attributes name.

      Members:
        foo: bar
      """,
        """Class with func-specific section.

      These sections aren't valid for classes.

      Args:
        foo: bar
      """,
        """Class with examples & attributes out of order.

      Attributes:
        foo: bar

      Examples:
        Do stuff.
      """,
    )

    CHECKER = lint.DocStringChecker

    def testGood_visit_functiondef(self):
        """Allow known good docstrings"""
        for dc in self.GOOD_FUNC_DOCSTRINGS:
            self.results = []
            node = TestNode(doc=dc, display_type=None, col_offset=4)
            self.checker.visit_functiondef(node)
            self.assertLintPassed(
                msg='docstring was not accepted:\n"""%s"""' % dc
            )

    def testBad_visit_functiondef(self):
        """Reject known bad docstrings"""
        for dc in self.BAD_FUNC_DOCSTRINGS:
            self.results = []
            node = TestNode(doc=dc, display_type=None, col_offset=4)
            self.checker.visit_functiondef(node)
            self.assertLintFailed(
                msg='docstring was not rejected:\n"""%s"""' % dc
            )

    def testSmoke_visit_module(self):
        """Smoke test for modules"""
        self.checker.visit_module(TestNode(doc="foo"))
        self.assertLintPassed()
        self.checker.visit_module(TestNode(doc="", path="/foo/__init__.py"))
        self.assertLintPassed()

    def testGood_visit_classdef(self):
        """Allow known good docstrings"""
        for dc in self.GOOD_CLASS_DOCSTRINGS:
            self.results = []
            node = TestNode(doc=dc, display_type=None, col_offset=4)
            self.checker.visit_classdef(node)
            self.assertLintPassed(
                msg='docstring was not accepted:\n"""%s"""' % dc
            )

    def testBad_visit_classdef(self):
        """Reject known bad docstrings"""
        for dc in self.BAD_CLASS_DOCSTRINGS:
            self.results = []
            node = TestNode(doc=dc, display_type=None, col_offset=4)
            self.checker.visit_classdef(node)
            self.assertLintFailed(
                msg='docstring was not rejected:\n"""%s"""' % dc
            )

    def testSmoke_visit_classdef(self):
        """Smoke test for classes"""
        self.checker.visit_classdef(TestNode(doc="bar"))

    def testGood_check_first_line(self):
        """Verify _check_first_line accepts good inputs"""
        docstrings = ("Some string",)
        for dc in docstrings:
            self.results = []
            node = TestNode(doc=dc)
            self.checker._check_first_line(node, node.lines)
            self.assertLintPassed(
                msg='docstring was not accepted:\n"""%s"""' % dc
            )

    def testBad_check_first_line(self):
        """Verify _check_first_line rejects bad inputs"""
        docstrings = ("\nSome string\n",)
        for dc in docstrings:
            self.results = []
            node = TestNode(doc=dc)
            self.checker._check_first_line(node, node.lines)
            self.assertLintFailed(expected=("C9009",))

    def testGood_check_second_line_blank(self):
        """Verify _check_second_line_blank accepts good inputs"""
        docstrings = (
            "Some string\n\nThis is the third line",
            "Some string",
        )
        for dc in docstrings:
            self.results = []
            node = TestNode(doc=dc)
            self.checker._check_second_line_blank(node, node.lines)
            self.assertLintPassed(
                msg='docstring was not accepted:\n"""%s"""' % dc
            )

    def testBad_check_second_line_blank(self):
        """Verify _check_second_line_blank rejects bad inputs"""
        docstrings = ("Some string\nnonempty secondline",)
        for dc in docstrings:
            self.results = []
            node = TestNode(doc=dc)
            self.checker._check_second_line_blank(node, node.lines)
            self.assertLintFailed(expected=("C9014",))

    def testGoodFuncVarKwArg(self):
        """Check valid inputs for *args and **kwargs"""
        for vararg in (None, "args", "_args"):
            for kwarg in (None, "kwargs", "_kwargs"):
                self.results = []
                node = TestNode(vararg=vararg, kwarg=kwarg)
                self.checker._check_func_signature(node)
                self.assertLintPassed()

    def testMisnamedFuncVarKwArg(self):
        """Reject anything but *args and **kwargs"""
        for vararg in ("arg", "params", "kwargs", "_moo"):
            self.results = []
            node = TestNode(vararg=vararg)
            self.checker._check_func_signature(node)
            self.assertLintFailed(expected=("C9011",))

        for kwarg in ("kwds", "_kwds", "args", "_moo"):
            self.results = []
            node = TestNode(kwarg=kwarg)
            self.checker._check_func_signature(node)
            self.assertLintFailed(expected=("C9011",))

    def testGoodFuncArgs(self) -> None:
        """Verify normal args in Args are allowed"""

        class TestData(NamedTuple):
            """Helper for creating testcases."""

            dc: str
            args: tuple
            vararg: Optional[str] = None
            kwarg: Optional[str] = None

        datasets = (
            TestData(
                """args are correct, and cls is ignored

         Args:
           moo: cow
         """,
                (
                    "cls",
                    "moo",
                ),
            ),
            TestData(
                """args are correct, and self is ignored

         Args:
           moo: cow
           *args: here
         """,
                (
                    "self",
                    "moo",
                ),
                "args",
                "kwargs",
            ),
            TestData(
                """args are allowed to wrap

         Args:
           moo:
             a big fat cow
             that takes many lines
             to describe its fatness
         """,
                ("moo",),
                kwarg="kwargs",
            ),
        )
        for dc, args, vararg, kwarg in datasets:
            self.results = []
            node = TestNode(doc=dc, args=args, vararg=vararg, kwarg=kwarg)
            sections = self.checker._parse_docstring_sections(node, node.lines)
            self.checker._check_all_args_in_doc(node, node.lines, sections)
            self.assertLintPassed()

    def testBadFuncArgs(self) -> None:
        """Verify bad/missing args in Args are caught"""

        class TestData(NamedTuple):
            """Helper for creating testcases."""

            dc: str
            args: tuple
            vararg: Optional[str] = None
            kwarg: Optional[str] = None

        datasets = (
            TestData(
                """missing 'bar'

         Args:
           moo: cow
         """,
                (
                    "moo",
                    "bar",
                ),
            ),
            TestData(
                """missing 'cow' but has 'bloop'

         Args:
           moo: cow
         """,
                ("bloop",),
            ),
            TestData(
                """too much space after colon

         Args:
           moo:  cow
         """,
                ("moo",),
            ),
            TestData(
                """not enough space after colon

         Args:
           moo:cow
         """,
                ("moo",),
            ),
            TestData(
                """deprecated use of type

         Args:
           moo (str): Ok.
         """,
                ("moo",),
            ),
            TestData(
                """deprecated use of type

         Args:
           moo: (str) Ok.
         """,
                ("moo",),
            ),
            TestData(
                """duplicated arg

                Args:
                    moo: Ok.
                    moo: Ok.
                """,
                ("moo",),
            ),
            TestData(
                """*args must be *args, not args

                Args:
                    args: Foo.
                """,
                (),
                "args",
            ),
            TestData(
                """**kwargs must be **kwargs, not kwargs

                Args:
                    kwargs: Foo.
                """,
                (),
                kwarg="kwargs",
            ),
        )
        for dc, args, vararg, kwarg in datasets:
            self.results = []
            node = TestNode(doc=dc, args=args, vararg=vararg, kwarg=kwarg)
            sections = self.checker._parse_docstring_sections(node, node.lines)
            self.checker._check_all_args_in_doc(node, node.lines, sections)
            self.assertLintFailed()

    def test_parse_docstring_sections(self):
        """Check docstrings are parsed."""
        datasets = (
            (
                """Some docstring

         Args:
           foo: blah

         Raises:
           blaaaaaah

         Note:
           This section shouldn't be checked.

         Returns:
           some value
         """,
                collections.OrderedDict(
                    (
                        (
                            "Args",
                            lint.DocStringSectionDetails(
                                name="Args",
                                header="         Args:",
                                lines=["           foo: blah"],
                                lineno=3,
                            ),
                        ),
                        (
                            "Raises",
                            lint.DocStringSectionDetails(
                                name="Raises",
                                header="         Raises:",
                                lines=["           blaaaaaah"],
                                lineno=6,
                            ),
                        ),
                        (
                            "Returns",
                            lint.DocStringSectionDetails(
                                name="Returns",
                                header="         Returns:",
                                lines=["           some value"],
                                lineno=12,
                            ),
                        ),
                    )
                ),
            ),
        )
        for dc, expected in datasets:
            node = TestNode(doc=dc)
            sections = self.checker._parse_docstring_sections(node, node.lines)
            self.assertEqual(expected, sections)

    def test_check_docstring_section_indent(self):
        """Check docstring diags are as expected."""
        # The offset of the below docstrings, in columns.
        col_offset = 10
        indent_level = self.checker._indent_len
        indent = col_offset * " "

        datasets = (
            # Success.
            (
                """Some docstring

            Args:
              foo: blah
            """,
                [],
            ),
            # `Args:` is indented by one too many spaces.
            (
                """Some docstring

             Args:
              foo: blah
            """,
                [
                    (
                        "C9015",
                        {
                            "curr_indent": col_offset + indent_level + 1,
                            "line": f"{indent}   Args:",
                            "offset": 3,
                            "want_indent": col_offset + indent_level,
                        },
                    ),
                ],
            ),
            # `Args:` is indented by one too few spaces.
            (
                """Some docstring

           Args:
              foo: blah
            """,
                [
                    (
                        "C9015",
                        {
                            "curr_indent": col_offset + 1,
                            "line": f"{indent} Args:",
                            "offset": 3,
                            "want_indent": col_offset + indent_level,
                        },
                    ),
                ],
            ),
            # `foo: blah` is indented by one too many spaces.
            (
                """Some docstring

            Args:
               foo: blah
            """,
                [
                    (
                        "C9015",
                        {
                            "curr_indent": col_offset + indent_level + 3,
                            "line": f"{indent}     foo: blah",
                            "offset": 4,
                            "want_indent": col_offset + indent_level * 2,
                        },
                    ),
                ],
            ),
            # `bar: blah` is indented by one too few spaces.
            (
                """Some docstring

            Args:
              foo: blah
             bar: blah
            """,
                [
                    (
                        "C9015",
                        {
                            "curr_indent": col_offset + indent_level + 1,
                            "line": f"{indent}   bar: blah",
                            "offset": 5,
                            "want_indent": col_offset + indent_level * 2,
                        },
                    ),
                ],
            ),
            # `foo: blah` is indented by one too many spaces.
            (
                """Some docstring

            Args:
               foo: blah
            """,
                [
                    (
                        "C9015",
                        {
                            "curr_indent": col_offset + indent_level * 2 + 1,
                            "line": f"{indent}     foo: blah",
                            "offset": 4,
                            "want_indent": col_offset + indent_level * 2,
                        },
                    ),
                ],
            ),
        )

        for i, (docstring, expected) in enumerate(datasets):
            self.results = []
            node = TestNode(
                display_type=None, col_offset=col_offset, doc=docstring
            )
            sections = self.checker._parse_docstring_sections(node, node.lines)
            self.checker._check_section_lines(
                node, node.lines, sections, self.checker.VALID_FUNC_SECTIONS
            )
            trimmed_results = [
                (warn_id, d) for warn_id, _, _, d, _ in self.results
            ]
            self.assertEqual(trimmed_results, expected, f"On datasets[{i}]")


class SourceCheckerTest(CheckerTestCase):
    """Tests for SourceChecker module"""

    CHECKER = lint.SourceChecker

    def _testShebang(self, shebangs, exp, mode):
        """Helper for shebang tests"""
        for shebang in shebangs:
            self.results = []
            node = TestNode()
            stream = io.BytesIO(shebang)
            st = StatStub(size=len(shebang), mode=mode)
            self.checker._check_shebang(node, stream, st)
            msg = "processing shebang failed: %r" % shebang
            if not exp:
                self.assertLintPassed(msg=msg)
            else:
                self.assertLintFailed(msg=msg, expected=exp)

    def testBadShebang(self):
        """Verify _check_shebang rejects bad shebangs"""
        shebangs = (
            b"#!/usr/bin/python\n",
            b"#! /usr/bin/python2 \n",
            b"#! /usr/bin/env python2 \n",
            b"#!/usr/bin/python2\n",
        )
        self._testShebang(shebangs, ("R9200",), 0o755)

    def testGoodShebangNoExec(self):
        """Verify _check_shebang rejects shebangs on non-exec files"""
        shebangs = (
            b"#!/usr/bin/env python\n",
            b"#!/usr/bin/env python2\n",
            b"#!/usr/bin/env python3\n",
            b"#!/usr/bin/env vpython\n",
            b"#!/usr/bin/env vpython3\n",
        )
        self._testShebang(shebangs, ("R9202",), 0o644)

    def testGoodShebang(self):
        """Verify _check_shebang accepts good shebangs"""
        shebangs = (
            b"#!/usr/bin/env python\n",
            b"#!/usr/bin/env python2\n",
            b"#!/usr/bin/env python3\n",
            b"#!/usr/bin/env python2\t\n",
            b"#!/usr/bin/env vpython\n",
            b"#!/usr/bin/env vpython3\n",
        )
        self._testShebang(shebangs, (), 0o755)

    def testEmptyFileNoEncoding(self):
        """_check_encoding should ignore 0 byte files"""
        self.results = []
        stream = io.BytesIO(b"")
        self.checker._check_encoding(stream)
        self.assertLintPassed()

    def testGoodEncodings(self) -> None:
        """Verify _check_encoding detects unnecessary coding cookies"""
        shebang = b"#!/usr/bin/python\n"
        encoding = b"# -*- coding: utf-8 -*-"
        for first in (b"", shebang):
            data = first + encoding + b"\n"
            stream = io.BytesIO(data)
            self.results = []
            self.checker._check_encoding(stream)
            self.assertLintFailed(expected=("R9205",))

    def testGoodUnittestName(self):
        """Verify _check_module_name accepts good unittest names"""
        module_names = ("lint_unittest",)
        for name in module_names:
            node = TestNode(name=name)
            self.results = []
            self.checker._check_module_name(node)
            self.assertLintPassed()

    def testBadUnittestName(self):
        """Verify _check_module_name rejects bad unittest names"""
        module_names = ("lint_unittests",)
        for name in module_names:
            node = TestNode(name=name)
            self.results = []
            self.checker._check_module_name(node)
            self.assertLintFailed(expected=("R9203",))

    def testAcceptableBackslashes(self):
        """Verify _check_backslashes allows certain backslash usage"""
        snippets = (
            # With context manager.
            b"""with foo() \\
                as bar:""",
            b"""with foo() as bar, \\
                 foo() as barar:""",
            # Leading docstrings.
            b"""'''\\
            long string is long'''""",
            # Comments.
            b"""# Blah blah: \\
            # another point.""",
            # Docstring with split content.
            b"""foo = '''
            blah bl-\\
            ah'''""",
        )
        node = TestNode()
        for snippet in snippets:
            # Make sure there's actually a \ to test against.
            self.assertIn(b"\\", snippet)
            print("Checking snippet", snippet)
            self.results = []
            stream = io.BytesIO(snippet)
            self.checker._check_backslashes(node, stream)
            self.assertLintPassed()

    def testBadBackslashes(self):
        """Verify _check_backslashes rejects bad backslash usage"""
        snippets = (
            # kwarg in a function call.
            b"""foo(bar=\\
                True)""",
            # Variable assignment.
            b"""foo = \\
                bar""",
            # If statements.
            b"""if True and \\
               True:""",
            b"""if True or \\
               True:""",
            # Assert statements.
            b"""assert False, \\
                "blah blah" """,
            # Interpolation.
            b"""foo = BLAH % \\
                {}""",
            # Binary operators.
            b"""foo = 1 + \\
                2""",
            b"""foo = 1 - \\
                2""",
            b"""foo = 1 | \\
                2""",
            b"""foo = 1 * \\
                2""",
            b"""foo = 1 / \\
                2""",
        )
        node = TestNode()
        for snippet in snippets:
            # Make sure there's actually a \ to test against.
            self.assertIn(b"\\", snippet)
            print("Checking snippet", snippet)
            self.results = []
            stream = io.BytesIO(snippet)
            self.checker._check_backslashes(node, stream)
            self.assertLintFailed(expected=("R9206",))


class CommentCheckerTest(CheckerTestCase):
    """Tests for CommentChecker module"""

    CHECKER = lint.CommentChecker

    def testGoodComments(self):
        """Verify we accept good comments."""
        GOOD_COMMENTS = (
            "# Blah.",
            "## Blah.",
            "#",
            "#   Indented Code.",
            "# pylint: disable all the things",
        )
        for comment in GOOD_COMMENTS:
            self.results = []
            self.checker._visit_comment(0, comment)
            self.assertLintPassed()

    def testIgnoreShebangs(self):
        """Verify we ignore shebangs."""
        self.results = []
        self.checker._visit_comment(1, "#!/usr/bin/env python3")
        self.assertLintPassed()

    def testBadCommentsSpace(self):
        """Verify we reject comments missing leading space."""
        BAD_COMMENTS = (
            "#Blah.",
            "##Blah.",
            "#TODO(foo): Bar.",
            "#pylint: nah",
            "#\tNo tabs!",
        )
        for comment in BAD_COMMENTS:
            self.results = []
            self.checker._visit_comment(0, comment)
            self.assertLintFailed(expected=("R9250",))


class ImportCheckerTest(CheckerTestCase):
    """Tests for ModuleOnlyImportsChecker module"""

    CHECKER = lint.ModuleOnlyImportsChecker

    def checkImport(
        self,
        module: str,
        members: List[str],
        member_is_module: Optional[bool] = False,
        fail_lookup: Optional[bool] = False,
        is_submodule: Optional[bool] = False,
    ) -> None:
        """Simulate a lint of an import line.

        E.g., `import $module` or `from $module import $members`.
        """

        class Result(TestNode):
            """Mock result for astroid.nodes.ImportFrom.do_import_module."""

            def lookup(self, member):
                if fail_lookup:
                    return (member, None)
                if member_is_module:
                    item = astroid.nodes.Module(name=member)
                else:
                    item = TestNode(name=member)
                return (member, [item])

            # pylint: disable-next=unused-argument
            def import_module(self, name, relative_only):
                if is_submodule:
                    return
                raise astroid.AstroidImportError()

        class TestImportFromNode(TestNode):
            """TestNode that offers a do_import_module implementation."""

            def do_import_module(self):
                return Result(name=module)

        names = [(member, None) for member in members]
        node = TestImportFromNode(name=module, names=names)
        self.results = []
        self.checker.visit_importfrom(node)

    def testGoodImportNoMembers(self):
        """Verify we accept `import os`."""
        self.checkImport("os", [])
        self.assertLintPassed()

    def testGoodImportMember(self):
        """Verify we accept `from pylint import config`."""
        self.checkImport("pylint", ["config"], member_is_module=True)
        self.assertLintPassed()

    def testExcludedImport(self):
        """Verify we accept `from typing import List`"""
        self.checkImport("typing", ["List"])
        self.assertLintPassed()

    def testMemberLookupFailure(self):
        """Verify a member that fails lookup is treated as a module."""
        self.checkImport("unittest", ["mock"], fail_lookup=True)
        self.assertLintPassed()

    def testSubmodule(self):
        """Verify we accept submodules."""
        self.checkImport("utils.telemetry", ["config"], is_submodule=True)
        self.assertLintPassed()

    def testBadImport(self):
        """Verify we reject `from unittest.mock import patch`"""
        self.checkImport("unittest.mock", ["patch"], member_is_module=False)
        self.assertLintFailed(expected=("R9170",))


class EncodingCheckerTest(CheckerTestCase):
    """Tests for EncodingChecker"""

    CHECKER = lint.EncodingChecker

    @staticmethod
    def _make_pathlib_node(code):
        """Helper to construct a callable node."""
        node = astroid.extract_node(
            "import gzip\n"
            "from pathlib import Path\n"
            "p = Path()\n"
            f"{code} #@"
        )
        node.doc = code
        return node

    def _check_tests(self, tests, passes):
        """Helper to run all the test cases."""
        for test in tests:
            node = self._make_pathlib_node(test)
            self.results = []
            self.checker.visit_call(node)
            if passes:
                self.assertLintPassed()
            else:
                self.assertLintFailed()

    def testNonConst(self):
        """Check we don't crash on non-const inputs.

        We can't detect the errors because pylint doesn't maintain enough state.
        But these are uncommon cases, so don't worry about them as much.
        """
        self._check_tests(
            (
                "mode = 'r'\nopen('f', mode)",
                "mode = 'r'\nopen('f', mode=mode)",
                "open('f', None)",
                "open('f', mode=None)",
                "enc = 'ascii'\nopen('f', 'rb', -1, enc)",
                "enc = 'ascii'\nopen('f', 'rb', encoding=enc)",
                "mode = 'rt'\ngzip.open('f', mode)",
            ),
            True,
        )

    def testOpenGood(self):
        """Verify we accept good open() encoding."""
        self._check_tests(
            (
                # open(file, mode='r', buffering=-1, encoding=None, ...
                "open('f', 'rb')",
                "open('f', mode='rb')",
                "open('f', 'wb')",
                "open('f', 'r', -1, 'utf-8')",
                "open('f', encoding='utf-8')",
                "open('f', mode='r', encoding='utf-8')",
                "open('f', encoding='utf-8', mode='r')",
            ),
            True,
        )

    def testOpenBad(self):
        """Verify we reject bad open() encoding."""
        self._check_tests(
            (
                # open(file, mode='r', buffering=-1, encoding=None, ...
                "open('f')",
                "open('f', 'r')",
                "open('f', 'w')",
                "open('f', mode='r')",
                "open('f', 'r', -1)",
                "open('f', 'r', -1, None)",
                "open('f', 'r', -1, 'ascii')",
                "open('f', 'r', -1, encoding=None)",
                "open('f', 'r', -1, encoding='ascii')",
                "open('f', mode='r', encoding='ascii')",
                "open('f', encoding='ascii', mode='r')",
            ),
            False,
        )

    def testGzipOpenGood(self):
        """Verify we accept good gzip.open() encoding."""
        self._check_tests(
            (
                # gzip.open(file, mode='r', compresslevel=0, encoding=None, ...
                "gzip.open('f')",
                "gzip.open('f', 'r')",
                "gzip.open('f', 'rb')",
                "gzip.open('f', mode='r')",
                "gzip.open('f', mode='rb')",
                "gzip.open('f', 'w')",
                "gzip.open('f', 'wb')",
                "gzip.open('f', 'rt', -1, 'utf-8')",
                "gzip.open('f', mode='rt', encoding='utf-8')",
                "gzip.open('f', encoding='utf-8', mode='rt')",
            ),
            True,
        )

    def testGzipOpenBad(self):
        """Verify we reject bad gzip.open() encoding."""
        self._check_tests(
            (
                # gzip.open(file, mode='r', compresslevel=0, encoding=None, ...
                "gzip.open('f', 'rt')",
                "gzip.open('f', 'wt')",
                "gzip.open('f', mode='rt')",
                "gzip.open('f', 'rt', -1)",
                "gzip.open('f', 'rt', -1, None)",
                "gzip.open('f', 'rt', -1, 'ascii')",
                "gzip.open('f', 'rt', -1, encoding=None)",
                "gzip.open('f', 'rt', -1, encoding='ascii')",
                "gzip.open('f', mode='rt', encoding='ascii')",
                "gzip.open('f', encoding='ascii', mode='rt')",
            ),
            False,
        )

    def testPathlibOpenGood(self):
        """Verify we accept good Pathlib.Path.open() encoding."""
        self._check_tests(
            (
                # Path.open(mode='r', buffering=-1, encoding=None, ...
                "p.open('rb')",
                "p.open(mode='rb')",
                "p.open('wb')",
                "p.open('r', -1, 'utf-8')",
                "p.open(encoding='utf-8')",
                "p.open(mode='r', encoding='utf-8')",
                "p.open(encoding='utf-8', mode='r')",
            ),
            True,
        )

    def testPathlibOpenBad(self):
        """Verify we reject bad Pathlib.Path.open() encoding."""
        self._check_tests(
            (
                # Path.open(mode='r', buffering=-1, encoding=None, ...
                "p.open()",
                "p.open('r')",
                "p.open('w')",
                "p.open(mode='r')",
                "p.open('r', -1)",
                "p.open('r', -1, None)",
                "p.open('r', -1, 'ascii')",
                "p.open('r', -1, encoding=None)",
                "p.open('r', -1, encoding='ascii')",
                "p.open(mode='r', encoding='ascii')",
                "p.open(encoding='ascii', mode='r')",
            ),
            False,
        )

    def testPathlibReadTextGood(self):
        """Verify we accept good Pathlib.Path.read_text() encoding."""
        self._check_tests(
            (
                # Path.read_text(encoding=None, ...
                "p.read_text(encoding='utf-8')",
                "p.read_text('utf-8')",
            ),
            True,
        )

    def testPathlibReadTextBad(self):
        """Verify we reject bad Pathlib.Path.read_text() encoding."""
        self._check_tests(
            (
                # Path.read_text(encoding=None, ...
                "p.read_text()",
                "p.read_text(encoding=None)",
                "p.read_text(encoding='ascii')",
                "p.read_text(None)",
                "p.read_text('ascii')",
            ),
            False,
        )

    def testPathlibWriteTextGood(self):
        """Verify we accept good Pathlib.Path.write_text() encoding."""
        self._check_tests(
            (
                # Path.write_text(data, encoding=None, ...
                "p.write_text('', encoding='utf-8')",
                "p.write_text('', 'utf-8')",
            ),
            True,
        )

    def testPathlibWriteTextBad(self):
        """Verify we reject bad Pathlib.Path.write_text() encoding."""
        self._check_tests(
            (
                # Path.write_text(data, encoding=None, ...
                "p.write_text('')",
                "p.write_text('', encoding=None)",
                "p.write_text('', encoding='ascii')",
                "p.write_text('', None)",
                "p.write_text('', 'ascii')",
            ),
            False,
        )


class MonkeypatchCheckerTest(CheckerTestCase):
    """Tests for MonkeypatchChecker"""

    CHECKER = lint.MonkeypatchChecker

    @staticmethod
    def _make_nodes(code: str) -> Iterable:
        """Helper to construct a callable node."""
        snippets = (
            f"monkeypatch.setattr({code})",
            f"self.monkeypatch.setattr({code})",
        )
        for snippet in snippets:
            node = astroid.extract_node(snippet)
            node.doc = code
            yield node

    def _check_tests(self, tests, passes):
        """Helper to run all the test cases."""
        for test in tests:
            for node in self._make_nodes(test):
                self.results = []
                self.checker.visit_call(node)
                if passes:
                    self.assertLintPassed()
                else:
                    self.assertLintFailed()

    def testBadCalls(self):
        """Don't crash when the API is used incorrectly."""
        self._check_tests(
            (
                "",
                "None",
                "'asdf'",
                "1",
            ),
            True,
        )

    def testCrosBuildLibRun(self):
        """Reject cros_build_lib.run usage."""
        self._check_tests(
            (
                "cros_build_lib, 'run'",
                "cros_build_lib, 'run', lambda *_, **kwargs: 1",
                "'cros_build_lib.run'",
                "'cros_build_lib.run', lambda *_, **kwargs: 1",
            ),
            False,
        )

    def testCrosBuildLibSudoRun(self):
        """Reject cros_build_lib.sudo_run usage."""
        self._check_tests(
            (
                "cros_build_lib, 'sudo_run'",
                "cros_build_lib, 'sudo_run', lambda *_, **kwargs: 1",
                "'cros_build_lib.sudo_run'",
                "'cros_build_lib.sudo_run', lambda *_, **kwargs: 1",
            ),
            False,
        )
