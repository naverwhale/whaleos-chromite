# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Router class for the Build API.

Handles routing requests to the appropriate controller and handles service
registration.
"""

import collections
import contextlib
import importlib
import logging
import os
from types import ModuleType
from typing import Callable, List, TYPE_CHECKING

from chromite.third_party.google.protobuf import symbol_database

from chromite.api import controller
from chromite.api import field_handler
from chromite.api.gen.chromite.api import android_pb2
from chromite.api.gen.chromite.api import api_pb2
from chromite.api.gen.chromite.api import artifacts_pb2
from chromite.api.gen.chromite.api import binhost_pb2
from chromite.api.gen.chromite.api import build_api_pb2
from chromite.api.gen.chromite.api import chrome_lkgm_pb2
from chromite.api.gen.chromite.api import copybot_pb2
from chromite.api.gen.chromite.api import depgraph_pb2
from chromite.api.gen.chromite.api import dlc_pb2
from chromite.api.gen.chromite.api import firmware_pb2
from chromite.api.gen.chromite.api import image_pb2
from chromite.api.gen.chromite.api import metadata_pb2
from chromite.api.gen.chromite.api import observability_pb2
from chromite.api.gen.chromite.api import packages_pb2
from chromite.api.gen.chromite.api import payload_pb2
from chromite.api.gen.chromite.api import portage_explorer_pb2
from chromite.api.gen.chromite.api import sdk_pb2
from chromite.api.gen.chromite.api import sdk_subtools_pb2
from chromite.api.gen.chromite.api import sysroot_pb2
from chromite.api.gen.chromite.api import test_pb2
from chromite.api.gen.chromite.api import toolchain_pb2
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import osutils
from chromite.utils import memoize


if TYPE_CHECKING:
    from chromite.third_party import google

    from chromite.api import api_config
    from chromite.api import message_util

MethodData = collections.namedtuple(
    "MethodData", ("service_descriptor", "module_name", "method_descriptor")
)


class Error(Exception):
    """Base error class for the module."""


class InvalidSdkError(Error):
    """Raised when the SDK is invalid or does not exist."""


class CrosSdkNotRunError(Error):
    """Raised when the cros_sdk command could not be run to enter the chroot."""


# API Service Errors.
class UnknownServiceError(Error):
    """Error raised when the requested service has not been registered."""


class ControllerModuleNotDefinedError(Error):
    """Error class for when no controller has been defined for a service."""


class ServiceControllerNotFoundError(Error):
    """Error raised when the service's controller cannot be imported."""


class TotSdkError(Error):
    """When attempting to run a ToT endpoint inside the SDK."""


# API Method Errors.
class UnknownMethodError(Error):
    """The service has been defined in the proto, but the method has not."""


class MethodNotFoundError(Error):
    """The method's implementation cannot be found in the controller."""


class Router:
    """Encapsulates the request dispatching logic."""

    REEXEC_INPUT_FILE = "input_proto"
    REEXEC_OUTPUT_FILE = "output_proto"
    REEXEC_CONFIG_FILE = "config_proto"

    def __init__(self):
        self._services = {}
        self._aliases = {}
        # All imported generated messages get added to this symbol db.
        self._sym_db = symbol_database.Default()

        # Save the service and method extension info for looking up
        # configured extension data.
        extensions = build_api_pb2.DESCRIPTOR.extensions_by_name
        self._svc_options_ext = extensions["service_options"]
        self._method_options_ext = extensions["method_options"]

    @memoize.Memoize
    def _get_method_data(self, service_name, method_name):
        """Get the descriptors and module name for the given Service/Method."""
        try:
            svc, module_name = self._services[service_name]
        except KeyError:
            raise UnknownServiceError(
                "The %s service has not been registered." % service_name
            )

        try:
            method_desc = svc.methods_by_name[method_name]
        except KeyError:
            raise UnknownMethodError(
                "The %s method has not been defined in the %s "
                "service." % (method_name, service_name)
            )

        return MethodData(
            service_descriptor=svc,
            module_name=module_name,
            method_descriptor=method_desc,
        )

    def get_input_message_instance(self, service_name, method_name):
        """Get an empty input message instance for the specified method."""
        method_data = self._get_method_data(service_name, method_name)
        return self._sym_db.GetPrototype(
            method_data.method_descriptor.input_type
        )()

    def _get_output_message_instance(self, service_name, method_name):
        """Get an empty output message instance for the specified method."""
        method_data = self._get_method_data(service_name, method_name)
        return self._sym_db.GetPrototype(
            method_data.method_descriptor.output_type
        )()

    def _get_module_name(self, service_name, method_name):
        """Get the name of the module containing the endpoint implementation."""
        return self._get_method_data(service_name, method_name).module_name

    def _get_service_options(self, service_name, method_name):
        """Get the configured service options for the endpoint."""
        method_data = self._get_method_data(service_name, method_name)
        svc_extensions = method_data.service_descriptor.GetOptions().Extensions
        return svc_extensions[self._svc_options_ext]

    def _get_method_options(self, service_name, method_name):
        """Get the configured method options for the endpoint."""
        method_data = self._get_method_data(service_name, method_name)
        method_extensions = (
            method_data.method_descriptor.GetOptions().Extensions
        )
        return method_extensions[self._method_options_ext]

    def Register(self, proto_module: ModuleType):
        """Register the services from a generated proto module.

        Args:
            proto_module: The generated proto module to register.

        Raises:
            ServiceModuleNotDefinedError when the service cannot be found in the
                provided module.
        """
        services = proto_module.DESCRIPTOR.services_by_name
        for service_name, svc in services.items():
            module_name = (
                svc.GetOptions().Extensions[self._svc_options_ext].module
            )

            if not module_name:
                raise ControllerModuleNotDefinedError(
                    "The module must be defined in the service definition: "
                    f"{proto_module}.{service_name}"
                )

            self._services[svc.full_name] = (svc, module_name)

    def ListMethods(self):
        """List all methods registered with the router."""
        services = []
        for service_name, (svc, _module) in self._services.items():
            svc_visibility = getattr(
                svc.GetOptions().Extensions[self._svc_options_ext],
                "service_visibility",
                build_api_pb2.LV_VISIBLE,
            )
            if svc_visibility == build_api_pb2.LV_HIDDEN:
                continue

            for method_name in svc.methods_by_name.keys():
                method_options = self._get_method_options(
                    service_name, method_name
                )
                method_visibility = getattr(
                    method_options,
                    "method_visibility",
                    build_api_pb2.LV_VISIBLE,
                )
                if method_visibility == build_api_pb2.LV_HIDDEN:
                    continue

                services.append("%s/%s" % (service_name, method_name))

        return sorted(services)

    def Route(
        self,
        service_name: str,
        method_name: str,
        config: "api_config.ApiConfig",
        input_handler: "message_util.MessageHandler",
        output_handlers: List["message_util.MessageHandler"],
        config_handler: "message_util.MessageHandler",
    ) -> int:
        """Dispatch the request.

        Args:
            service_name: The fully qualified service name.
            method_name: The name of the method being called.
            config: The call configs.
            input_handler: The request message handler.
            output_handlers: The response message handlers.
            config_handler: The config message handler.

        Returns:
            The return code.

        Raises:
            InvalidInputFileError when the input file cannot be read.
            InvalidOutputFileError when the output file cannot be written.
            ServiceModuleNotFoundError when the service module cannot be
                imported.
            MethodNotFoundError when the method cannot be retrieved from the
                module.
        """
        # Fetch the method options for chroot and method name overrides.
        method_options = self._get_method_options(service_name, method_name)

        # Check the chroot settings before running.
        service_options = self._get_service_options(service_name, method_name)

        if self._needs_branch_reexecution(
            service_options, method_options, config
        ):
            logging.info("Re-executing the endpoint on the branched BAPI.")
            return self._reexecute_branched(
                input_handler,
                output_handlers,
                config_handler,
                service_name,
                method_name,
            )

        input_msg = self.get_input_message_instance(service_name, method_name)
        input_handler.read_into(input_msg)

        # Get an empty output message instance.
        output_msg = self._get_output_message_instance(
            service_name, method_name
        )

        chroot_reexec = self._needs_chroot_reexecution(
            service_options, method_options, config
        )

        if chroot_reexec and not constants.IS_BRANCHED_CHROMITE:
            # Can't run inside the SDK with ToT chromite.
            raise TotSdkError(
                f"Cannot run ToT {service_name}/{method_name} inside the SDK."
            )
        elif chroot_reexec:
            logging.info("Re-executing the endpoint inside the chroot.")
            return self._reexecute_inside(
                input_msg,
                output_msg,
                config,
                input_handler,
                output_handlers,
                config_handler,
                service_name,
                method_name,
            )

        # Allow proto-based method name override.
        if method_options.HasField("implementation_name"):
            implementation_name = method_options.implementation_name
        else:
            implementation_name = method_name

        # Import the module and get the method.
        module_name = self._get_module_name(service_name, method_name)
        method_impl = self._GetMethod(module_name, implementation_name)

        # Successfully located; call and return.
        return_code = method_impl(input_msg, output_msg, config)
        if return_code is None:
            return_code = controller.RETURN_CODE_SUCCESS

        for h in output_handlers:
            h.write_from(output_msg)

        return return_code

    def _needs_branch_reexecution(
        self,
        service_options: "google.protobuf.Message",
        method_options: "google.protobuf.Message",
        config: "api_config.ApiConfig",
    ) -> bool:
        """Check if the call needs to be re-executed on the branched BAPI."""
        if not config.run_endpoint:
            # Do not re-exec for validate only and mock calls.
            return False

        if method_options.HasField("method_branched_execution"):
            # Prefer the method option when set.
            branched_exec = method_options.method_branched_execution
        elif service_options.HasField("service_branched_execution"):
            # Fall back to the service option.
            branched_exec = service_options.service_branched_execution
        else:
            branched_exec = build_api_pb2.EXECUTE_BRANCHED

        if branched_exec in (
            build_api_pb2.EXECUTE_NOT_SPECIFIED,
            build_api_pb2.EXECUTE_BRANCHED,
        ):
            return not constants.IS_BRANCHED_CHROMITE

        return False

    def _needs_chroot_reexecution(
        self,
        service_options: "google.protobuf.Message",
        method_options: "google.protobuf.Message",
        config: "api_config.ApiConfig",
    ) -> bool:
        """Check the chroot options; execute assertion or note reexec as needed.

        Args:
            service_options: The service options.
            method_options: The method options.
            config: The Build API call config instance.

        Returns:
            True iff it needs to be reexeced inside the chroot.

        Raises:
            cros_build_lib.DieSystemExit when the chroot setting cannot be
                satisfied.
        """
        if not config.run_endpoint:
            # Do not enter the chroot for validate only and mock calls.
            return False

        chroot_assert = build_api_pb2.NO_ASSERTION
        if method_options.HasField("method_chroot_assert"):
            # Prefer the method option when set.
            chroot_assert = method_options.method_chroot_assert
        elif service_options.HasField("service_chroot_assert"):
            # Fall back to the service option.
            chroot_assert = service_options.service_chroot_assert

        if chroot_assert == build_api_pb2.INSIDE:
            return not cros_build_lib.IsInsideChroot()
        elif chroot_assert == build_api_pb2.OUTSIDE:
            # If it must be run outside we have to already be outside.
            cros_build_lib.AssertOutsideChroot()

        return False

    def _reexecute_branched(
        self,
        input_handler: "message_util.MessageHandler",
        output_handlers: List["message_util.MessageHandler"],
        config_handler: "message_util.MessageHandler",
        service_name: str,
        method_name: str,
    ):
        """Re-execute the call on the branched BAPI.

        Args:
            input_handler: Input message handler.
            output_handlers: Output message handlers.
            config_handler: Config message handler.
            service_name: The name of the service to run.
            method_name: The name of the method to run.
        """
        cmd = [
            constants.BRANCHED_CHROMITE_DIR / "bin" / "build_api",
            f"{service_name}/{method_name}",
            input_handler.input_arg,
            input_handler.path,
            "--debug",
        ]

        for output_handler in output_handlers:
            cmd += [
                output_handler.output_arg,
                output_handler.path,
            ]

        # Config is optional, check it was actually used before adding.
        if config_handler.path:
            cmd += [
                config_handler.config_arg,
                config_handler.path,
            ]

        try:
            result = cros_build_lib.run(
                cmd,
                check=False,
            )
        except cros_build_lib.RunCommandError:
            # A non-zero return code will not result in an error, but one
            # is still thrown when the command cannot be run in the first
            # place. This is known to happen at least when the PATH does
            # not include the chromite bin dir.
            raise CrosSdkNotRunError("Unable to execute the branched BAPI.")

        logging.info(
            "Endpoint execution completed, return code: %d",
            result.returncode,
        )

        return result.returncode

    def _reexecute_inside(
        self,
        input_msg: "google.protobuf.Message",
        output_msg: "google.protobuf.Message",
        config: "api_config.ApiConfig",
        input_handler: "message_util.MessageHandler",
        output_handlers: List["message_util.MessageHandler"],
        config_handler: "message_util.MessageHandler",
        service_name: str,
        method_name: str,
    ):
        """Re-execute the service inside the chroot.

        Args:
            input_msg: The parsed input message.
            output_msg: The empty output message instance.
            config: The call configs.
            input_handler: Input message handler.
            output_handlers: Output message handlers.
            config_handler: Config message handler.
            service_name: The name of the service to run.
            method_name: The name of the method to run.
        """
        # Parse the chroot and clear the chroot field in the input message.
        chroot = field_handler.handle_chroot(input_msg)

        if not chroot.exists():
            raise InvalidSdkError("Chroot does not exist.")

        # This may be redundant with other SDK setup flows, but we need this
        # tmp directory to exist (including across chromite updates, where the
        # path may move) before we can write our proto messages (e.g., for
        # SdkService/Update) to it below.
        osutils.SafeMakedirsNonRoot(chroot.tmp, mode=0o777)

        # Use a ExitStack to avoid the deep nesting this many context managers
        # introduces.
        with contextlib.ExitStack() as stack:
            # TempDirs setup.
            tempdir = stack.enter_context(chroot.tempdir())
            sync_tempdir = stack.enter_context(chroot.tempdir())
            # The copy-paths-in context manager to handle Path messages.
            stack.enter_context(
                field_handler.copy_paths_in(
                    input_msg,
                    chroot.tmp,
                    chroot=chroot,
                )
            )
            # The sync-directories context manager to handle SyncedDir messages.
            stack.enter_context(
                field_handler.sync_dirs(
                    input_msg,
                    sync_tempdir,
                    chroot=chroot,
                )
            )

            # Parse goma.
            chroot.goma = field_handler.handle_goma(
                input_msg, chroot.path, chroot.out_path
            )

            # Parse remoteexec.
            chroot.remoteexec = field_handler.handle_remoteexec(input_msg)

            # Build inside-chroot paths for the input, output, and config
            # messages.
            new_input = os.path.join(tempdir, self.REEXEC_INPUT_FILE)
            chroot_input = chroot.chroot_path(new_input)
            new_output = os.path.join(tempdir, self.REEXEC_OUTPUT_FILE)
            chroot_output = chroot.chroot_path(new_output)
            new_config = os.path.join(tempdir, self.REEXEC_CONFIG_FILE)
            chroot_config = chroot.chroot_path(new_config)

            # Setup the inside-chroot message files.
            logging.info("Writing input message to: %s", new_input)
            input_handler.write_from(input_msg, path=new_input)
            osutils.Touch(new_output)
            logging.info("Writing config message to: %s", new_config)
            config_handler.write_from(config.get_proto(), path=new_config)

            # We can use a single output to write the rest of them. Use the
            # first one as the reexec output and just translate its output in
            # the rest of the handlers after.
            output_handler = output_handlers[0]

            cmd = [
                "build_api",
                "%s/%s" % (service_name, method_name),
                input_handler.input_arg,
                chroot_input,
                output_handler.output_arg,
                chroot_output,
                config_handler.config_arg,
                chroot_config,
                "--debug",
            ]

            try:
                result = chroot.run(
                    cmd,
                    cwd=constants.SOURCE_ROOT,
                    check=False,
                )
            except cros_build_lib.RunCommandError:
                # A non-zero return code will not result in an error, but one
                # is still thrown when the command cannot be run in the first
                # place. This is known to happen at least when the PATH does
                # not include the chromite bin dir.
                raise CrosSdkNotRunError("Unable to enter the chroot.")

            logging.info(
                "Endpoint execution completed, return code: %d",
                result.returncode,
            )

            # Transfer result files out of the chroot.
            output_handler.read_into(output_msg, path=new_output)
            field_handler.extract_results(input_msg, output_msg, chroot)

            # Write out all the response formats.
            for handler in output_handlers:
                handler.write_from(output_msg)

            return result.returncode

    def _GetMethod(self, module_name: str, method_name: str) -> Callable:
        """Get the implementation of the method for the service module.

        Args:
            module_name: The name of the service module.
            method_name: The name of the method.

        Returns:
            The method.

        Raises:
            MethodNotFoundError when the method cannot be found in the module.
            ServiceModuleNotFoundError when the service module cannot be
                imported.
        """
        try:
            module = importlib.import_module(
                controller.IMPORT_PATTERN % module_name
            )
        except ImportError as e:
            raise ServiceControllerNotFoundError(str(e))
        try:
            return getattr(module, method_name)
        except AttributeError as e:
            raise MethodNotFoundError(str(e))


def RegisterServices(router: Router):
    """Register all the services.

    Args:
        router: The router.
    """
    router.Register(android_pb2)
    router.Register(api_pb2)
    router.Register(artifacts_pb2)
    router.Register(binhost_pb2)
    router.Register(chrome_lkgm_pb2)
    router.Register(copybot_pb2)
    router.Register(depgraph_pb2)
    router.Register(dlc_pb2)
    router.Register(firmware_pb2)
    router.Register(image_pb2)
    router.Register(metadata_pb2)
    router.Register(observability_pb2)
    router.Register(packages_pb2)
    router.Register(payload_pb2)
    router.Register(portage_explorer_pb2)
    router.Register(sdk_pb2)
    router.Register(sdk_subtools_pb2)
    router.Register(sysroot_pb2)
    router.Register(test_pb2)
    router.Register(toolchain_pb2)
    logging.debug("Services registered successfully.")


def GetRouter():
    """Get a router that has had all the services registered."""
    router = Router()
    RegisterServices(router)

    return router
