# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for the validate module."""

import os

from chromite.api import api_config
from chromite.api import validate
from chromite.api.gen.chromite.api import build_api_test_pb2
from chromite.api.gen.chromiumos import common_pb2
from chromite.lib import cros_build_lib
from chromite.lib import cros_test_lib
from chromite.lib import osutils


# These tests test the validators by defining a local `impl` function that
# has the same parameters as a controller function and the validator being
# tested. The validators don't care that they aren't actually controller
# functions, they just need the function to look like one, so it works
# to pass an arbitrary message; i.e. passing one of the Request messages
# we'd usually expect in a controller is not required. The validator
# just needs to be checking one of the fields on the message being used.
class ExistsTest(cros_test_lib.TempDirTestCase, api_config.ApiConfigMixin):
    """Tests for the exists validator."""

    def test_not_exists(self):
        """Test the validator fails when given a path that doesn't exist."""
        path = os.path.join(self.tempdir, "DOES_NOT_EXIST")

        @validate.exists("path")
        def impl(_input_proto, _output_proto, _config):
            self.fail("Incorrectly allowed method to execute.")

        with self.assertRaises(cros_build_lib.DieSystemExit):
            impl(common_pb2.Chroot(path=path), None, self.api_config)

    def test_exists(self):
        """Test the validator fails when given a path that doesn't exist."""
        path = os.path.join(self.tempdir, "chroot")
        osutils.SafeMakedirs(path)

        @validate.exists("path")
        def impl(_input_proto, _output_proto, _config):
            pass

        impl(common_pb2.Chroot(path=path), None, self.api_config)

    def test_skip_validation(self):
        """Test skipping validation case."""

        @validate.exists("path")
        def impl(_input_proto, _output_proto, _config):
            pass

        # This would otherwise raise an error for an invalid path.
        impl(common_pb2.Chroot(), None, self.no_validate_config)


class EqTest(cros_test_lib.TestCase, api_config.ApiConfigMixin):
    """Tests for the eq validator."""

    def test_eq(self):
        """Test a valid value."""

        @validate.eq("location", common_pb2.Path.Location.OUTSIDE)
        def impl(_input_proto, _output_proto, _config):
            pass

        impl(
            common_pb2.Path(
                path="/", location=common_pb2.Path.Location.OUTSIDE
            ),
            None,
            self.api_config,
        )

    def test_not_eq(self):
        """Test an invalid value."""

        @validate.eq("location", common_pb2.Path.Location.OUTSIDE)
        def impl(_input_proto, _output_proto, _config):
            pass

        # Should be failing on the invalid value.
        with self.assertRaises(cros_build_lib.DieSystemExit):
            impl(
                common_pb2.Path(
                    path="/", location=common_pb2.Path.Location.INSIDE
                ),
                None,
                self.api_config,
            )

    def test_not_set(self):
        """Test an unset value."""

        @validate.eq("location", common_pb2.Path.Location.OUTSIDE)
        def impl(_input_proto, _output_proto, _config):
            pass

        # Should be failing without a value set.
        with self.assertRaises(cros_build_lib.DieSystemExit):
            impl(common_pb2.Path(path="/"), None, self.api_config)

    def test_skip_validation(self):
        """Test skipping validation case."""

        @validate.eq("location", common_pb2.Path.Location.OUTSIDE)
        def impl(_input_proto, _output_proto, _config):
            pass

        # This would otherwise raise an error for an invalid path.
        impl(common_pb2.Path(path="/"), None, self.no_validate_config)


class IsInTest(cros_test_lib.TestCase, api_config.ApiConfigMixin):
    """Tests for the is_in validator."""

    def test_in(self):
        """Test a valid value."""

        @validate.is_in("path", ["/chroot/path", "/other/chroot/path"])
        def impl(_input_proto, _output_proto, _config):
            pass

        # Make sure all of the values work.
        impl(common_pb2.Chroot(path="/chroot/path"), None, self.api_config)
        impl(
            common_pb2.Chroot(path="/other/chroot/path"), None, self.api_config
        )

    def test_not_in(self):
        """Test an invalid value."""

        @validate.is_in("path", ["/chroot/path", "/other/chroot/path"])
        def impl(_input_proto, _output_proto, _config):
            pass

        # Should be failing on the invalid value.
        with self.assertRaises(cros_build_lib.DieSystemExit):
            impl(common_pb2.Chroot(path="/bad/value"), None, self.api_config)

    def test_not_set(self):
        """Test an unset value."""

        @validate.is_in("path", ["/chroot/path", "/other/chroot/path"])
        def impl(_input_proto, _output_proto, _config):
            pass

        # Should be failing without a value set.
        with self.assertRaises(cros_build_lib.DieSystemExit):
            impl(common_pb2.Chroot(), None, self.api_config)

    def test_skip_validation(self):
        """Test skipping validation case."""

        @validate.is_in("path", ["/chroot/path", "/other/chroot/path"])
        def impl(_input_proto, _output_proto, _config):
            pass

        # This would otherwise raise an error for an invalid path.
        impl(common_pb2.Chroot(), None, self.no_validate_config)


class EachInTest(cros_test_lib.TestCase, api_config.ApiConfigMixin):
    """Tests for the each_in validator."""

    # Easier access to the enum values.
    ENUM_FOO = build_api_test_pb2.TEST_ENUM_FOO
    ENUM_BAR = build_api_test_pb2.TEST_ENUM_BAR
    ENUM_BAZ = build_api_test_pb2.TEST_ENUM_BAZ

    # pylint: disable=docstring-misnamed-args
    def _message_request(self, *messages):
        """Build a request instance, filling out the messages field.

        Args:
            messages: Each messages data (id, name, flag, enum) as lists. Only
                requires as many as are set. e.g. _request([1], [2]) will create
                two messages with only ids set. _request([1, 'name']) will
                create one with id and name set, but not flag or enum.
        """
        request = build_api_test_pb2.TestRequestMessage()
        for message in messages or []:
            msg = request.messages.add()
            try:
                msg.id = message[0]
                msg.name = message[1]
                msg.flag = message[2]
            except IndexError:
                pass

        return request

    def _enums_request(self, *enum_values):
        """Build a request instance, setting the test_enums field."""
        request = build_api_test_pb2.TestRequestMessage()
        for value in enum_values:
            request.test_enums.append(value)

        return request

    def _numbers_request(self, *numbers):
        """Build a request instance, setting the numbers field."""
        request = build_api_test_pb2.TestRequestMessage()
        request.numbers.extend(numbers)

        return request

    def test_message_in(self):
        """Test valid values."""

        @validate.each_in("messages", "name", ["foo", "bar"])
        def impl(_input_proto, _output_proto, _config):
            pass

        impl(self._message_request([1, "foo"]), None, self.api_config)
        impl(
            self._message_request([1, "foo"], [2, "bar"]), None, self.api_config
        )

    def test_enum_in(self):
        """Test valid enum values."""

        @validate.each_in("test_enums", None, [self.ENUM_FOO, self.ENUM_BAR])
        def impl(_input_proto, _output_proto, _config):
            pass

        impl(self._enums_request(self.ENUM_FOO), None, self.api_config)
        impl(
            self._enums_request(self.ENUM_FOO, self.ENUM_BAR),
            None,
            self.api_config,
        )

    def test_scalar_in(self):
        """Test valid scalar values."""

        @validate.each_in("numbers", None, [1, 2])
        def impl(_input_proto, _output_proto, _config):
            pass

        impl(self._numbers_request(1), None, self.api_config)
        impl(self._numbers_request(1, 2), None, self.api_config)

    def test_message_not_in(self):
        """Test an invalid value."""

        @validate.each_in("messages", "name", ["foo", "bar"])
        def impl(_input_proto, _output_proto, _config):
            pass

        # Should be failing on the invalid value.
        with self.assertRaises(cros_build_lib.DieSystemExit):
            impl(self._message_request([1, "invalid"]), None, self.api_config)
        with self.assertRaises(cros_build_lib.DieSystemExit):
            impl(
                self._message_request([1, "invalid"], [2, "invalid"]),
                None,
                self.api_config,
            )
        with self.assertRaises(cros_build_lib.DieSystemExit):
            impl(
                self._message_request([1, "foo"], [2, "invalid"]),
                None,
                self.api_config,
            )

    def test_enum_not_in(self):
        """Test an invalid enum value."""

        @validate.each_in("test_enums", None, [self.ENUM_FOO, self.ENUM_BAR])
        def impl(_input_proto, _output_proto, _config):
            pass

        # Only invalid values.
        with self.assertRaises(cros_build_lib.DieSystemExit):
            impl(self._enums_request(self.ENUM_BAZ), None, self.api_config)
        # Mixed valid/invalid values.
        with self.assertRaises(cros_build_lib.DieSystemExit):
            impl(
                self._enums_request(self.ENUM_FOO, self.ENUM_BAZ),
                None,
                self.api_config,
            )

    def test_scalar_not_in(self):
        """Test invalid scalar value."""

        @validate.each_in("numbers", None, [1, 2])
        def impl(_input_proto, _output_proto, _config):
            pass

        # Only invalid values.
        with self.assertRaises(cros_build_lib.DieSystemExit):
            impl(self._numbers_request(3), None, self.api_config)
        # Mixed valid/invalid values.
        with self.assertRaises(cros_build_lib.DieSystemExit):
            impl(self._numbers_request(1, 2, 3), None, self.api_config)

    def test_not_set(self):
        """Test an unset value."""

        @validate.each_in("messages", "name", ["foo", "bar"])
        def impl(_input_proto, _output_proto, _config):
            pass

        # Should be failing without a value set.
        # No entries in the field.
        with self.assertRaises(cros_build_lib.DieSystemExit):
            impl(self._message_request(), None, self.api_config)
        # No value set on lone entry.
        with self.assertRaises(cros_build_lib.DieSystemExit):
            impl(self._message_request([1]), None, self.api_config)
        # No value set on multiple entries.
        with self.assertRaises(cros_build_lib.DieSystemExit):
            impl(self._message_request([1], [2]), None, self.api_config)
        # Some valid and some invalid entries.
        with self.assertRaises(cros_build_lib.DieSystemExit):
            impl(self._message_request([1, "foo"], [2]), None, self.api_config)

    def test_optional(self):
        """Test optional argument."""

        @validate.each_in("messages", "name", ["foo", "bar"], optional=True)
        @validate.each_in(
            "test_enums", None, [self.ENUM_FOO, self.ENUM_BAR], optional=True
        )
        @validate.each_in("numbers", None, [1, 2], optional=True)
        def impl(_input_proto, _output_proto, _config):
            pass

        # No entries in the field succeeds.
        impl(self._message_request(), None, self.api_config)

        # Still fails when entries exist but value unset cases.
        # No value set on lone entry.
        with self.assertRaises(cros_build_lib.DieSystemExit):
            impl(self._message_request([1]), None, self.api_config)
        # No value set on multiple entries.
        with self.assertRaises(cros_build_lib.DieSystemExit):
            impl(self._message_request([1], [2]), None, self.api_config)
        # Some valid and some invalid entries.
        with self.assertRaises(cros_build_lib.DieSystemExit):
            impl(self._message_request([1, "foo"], [2]), None, self.api_config)

    def test_skip_validation(self):
        """Test skipping validation case."""

        @validate.each_in("messages", "name", ["foo", "bar"])
        @validate.each_in("test_enums", None, [self.ENUM_FOO, self.ENUM_BAR])
        @validate.each_in("numbers", None, [1, 2])
        def impl(_input_proto, _output_proto, _config):
            pass

        # This would otherwise raise an error for multiple invalid fields.
        impl(
            self._message_request([1, "invalid"]), None, self.no_validate_config
        )


class RequireTest(cros_test_lib.TestCase, api_config.ApiConfigMixin):
    """Tests for the require validator."""

    def test_invalid_field(self):
        """Test validator fails when given an unset value."""

        @validate.require("does.not.exist")
        def impl(_input_proto, _output_proto, _config):
            self.fail("Incorrectly allowed method to execute.")

        with self.assertRaises(cros_build_lib.DieSystemExit):
            impl(common_pb2.Chroot(), None, self.api_config)

    def test_not_set(self):
        """Test validator fails when given an unset value."""

        @validate.require("env.use_flags")
        def impl(_input_proto, _output_proto, _config):
            self.fail("Incorrectly allowed method to execute.")

        with self.assertRaises(cros_build_lib.DieSystemExit):
            impl(common_pb2.Chroot(), None, self.api_config)

    def test_set(self):
        """Test validator passes when given set values."""

        @validate.require("path", "env.use_flags")
        def impl(_input_proto, _output_proto, _config):
            pass

        in_proto = common_pb2.Chroot(
            path="/chroot/path", env={"use_flags": [{"flag": "test"}]}
        )
        impl(in_proto, None, self.api_config)

    def test_mixed(self):
        """Test validator fails when given a set value and an unset value."""

        @validate.require("path", "env.use_flags")
        def impl(_input_proto, _output_proto, _config):
            pass

        with self.assertRaises(cros_build_lib.DieSystemExit):
            impl(common_pb2.Chroot(path="/chroot/path"), None, self.api_config)

    def test_skip_validation(self):
        """Test skipping validation case."""

        @validate.require("path", "env.use_flags")
        def impl(_input_proto, _output_proto, _config):
            pass

        # This would otherwise raise an error for an invalid path.
        impl(common_pb2.Chroot(), None, self.no_validate_config)


class RequireAnyTest(cros_test_lib.TestCase, api_config.ApiConfigMixin):
    """Tests for the require_any validator."""

    def _get_request(
        self, mid: int = None, name: str = None, flag: bool = None
    ):
        """Build a request instance from the given data."""
        request = build_api_test_pb2.MultiFieldMessage()

        if mid:
            request.id = mid
        if name:
            request.name = name
        if flag:
            request.flag = flag

        return request

    def test_invalid_field(self):
        """Test validator fails when given an invalid field."""

        @validate.require_any("does.not.exist", "also.invalid")
        def impl(_input_proto, _output_proto, _config):
            self.fail("Incorrectly allowed method to execute.")

        with self.assertRaises(cros_build_lib.DieSystemExit):
            impl(self._get_request(), None, self.api_config)

    def test_not_set(self):
        """Test validator fails when given unset values."""

        @validate.require_any("id", "name")
        def impl(_input_proto, _output_proto, _config):
            self.fail("Incorrectly allowed method to execute.")

        with self.assertRaises(cros_build_lib.DieSystemExit):
            impl(self._get_request(flag=True), None, self.api_config)

    def test_set(self):
        """Test validator passes when given set values."""

        @validate.require_any("id", "name")
        def impl(_input_proto, _output_proto, _config):
            pass

        impl(self._get_request(1), None, self.api_config)
        impl(self._get_request(name="foo"), None, self.api_config)
        impl(self._get_request(1, name="foo"), None, self.api_config)


class RequireEachTest(cros_test_lib.TestCase, api_config.ApiConfigMixin):
    """Tests for the require_each validator."""

    def _multi_field_message(self, msg_id=None, name=None, flag=None):
        msg = build_api_test_pb2.MultiFieldMessage()
        if msg_id is not None:
            msg.id = int(msg_id)
        if name is not None:
            msg.name = str(name)
        if flag is not None:
            msg.flag = bool(flag)
        return msg

    def _request(self, messages=None, count=0):
        """Build the request."""
        if messages is None:
            messages = [self._multi_field_message() for _ in range(count)]

        request = build_api_test_pb2.TestRequestMessage()
        for message in messages:
            msg = request.messages.add()
            msg.CopyFrom(message)

        return request

    def test_invalid_field(self):
        """Test validator fails when given an invalid field."""

        @validate.require_each("does.not", ["exist"])
        def impl(_input_proto, _output_proto, _config):
            self.fail("Incorrectly allowed method to execute.")

        with self.assertRaises(cros_build_lib.DieSystemExit):
            impl(self._request(), None, self.api_config)

    def test_invalid_call_no_subfields(self):
        """Test validator fails when given no subfields."""

        with self.assertRaises(AssertionError):

            @validate.require_each("does.not", [])
            def _(_input_proto, _output_proto, _config):
                pass

    def test_invalid_call_invalid_subfields(self):
        """Test validator fails when given subfields incorrectly."""

        with self.assertRaises(AssertionError):

            @validate.require_each("does.not", "exist")
            def _(_input_proto, _output_proto, _config):
                pass

    def test_not_set(self):
        """Test validator fails when given an unset value."""

        @validate.require_each("messages", ["id"])
        def impl(_input_proto, _output_proto, _config):
            self.fail("Incorrectly allowed method to execute.")

        with self.assertRaises(cros_build_lib.DieSystemExit):
            impl(self._request(count=2), None, self.api_config)

    def test_no_elements_success(self):
        """Test validator fails when given no messages in the repeated field."""

        @validate.require_each("messages", ["id"])
        def impl(_input_proto, _output_proto, _config):
            pass

        impl(self._request(), None, self.api_config)

    def test_no_elements_failure(self):
        """Test validator fails when given no messages in the repeated field."""

        @validate.require_each("messages", ["id"], allow_empty=False)
        def impl(_input_proto, _output_proto, _config):
            self.fail("Incorrectly allowed method to execute.")

        with self.assertRaises(cros_build_lib.DieSystemExit):
            impl(self._request(), None, self.api_config)

    def test_set(self):
        """Test validator passes when given set values."""

        @validate.require_each("messages", ["id"])
        def impl(_input_proto, _output_proto, _config):
            pass

        messages = [self._multi_field_message(msg_id=i) for i in range(1, 5)]
        impl(self._request(messages=messages), None, self.api_config)

    def test_one_set_fails(self):
        """Test validator passes when given set values."""

        @validate.require_each("messages", ["id", "name"])
        def impl(_input_proto, _output_proto, _config):
            pass

        messages = [self._multi_field_message(msg_id=i) for i in range(1, 5)]
        with self.assertRaises(cros_build_lib.DieSystemExit):
            impl(self._request(messages=messages), None, self.api_config)

    def test_multi_set(self):
        """Test validator passes when all values set."""

        @validate.require_each("messages", ["id", "name"])
        def impl(_input_proto, _output_proto, _config):
            pass

        messages = [
            self._multi_field_message(msg_id=i, name=i) for i in range(1, 5)
        ]
        impl(self._request(messages=messages), None, self.api_config)

    def test_skip_validation(self):
        """Test skipping validation case."""

        @validate.require_each("messages", ["id"], allow_empty=False)
        def impl(_input_proto, _output_proto, _config):
            pass

        impl(self._request(), None, self.no_validate_config)


class ValidateOnlyTest(cros_test_lib.TestCase, api_config.ApiConfigMixin):
    """validate_only decorator tests."""

    def test_validate_only(self):
        """Test validate only."""

        @validate.require("path")
        @validate.validation_complete
        def impl(_input_proto, _output_proto, _config):
            self.fail("Implementation was called.")
            return 1

        # Just using arbitrary messages, we just need the
        # (request, response, config) arguments so it can check the config.
        rc = impl(
            common_pb2.Chroot(path="/chroot/path"),
            common_pb2.Chroot(),
            self.validate_only_config,
        )

        self.assertEqual(0, rc)

    def test_no_validate_only(self):
        """Test no use of validate only."""

        @validate.validation_complete
        def impl(_input_proto, _output_proto, _config):
            self.fail("Incorrectly allowed method to execute.")

        # We will get an assertion error unless validate_only prevents the
        # function from being called.
        with self.assertRaises(AssertionError):
            impl(common_pb2.Chroot(), common_pb2.Chroot(), self.api_config)
