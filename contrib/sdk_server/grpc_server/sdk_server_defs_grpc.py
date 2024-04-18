# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Defines classes and functions used in implementation of sdk server."""

import datetime
import glob
import json
import logging
from logging import handlers
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Union

from chromite.third_party.google.protobuf import json_format

from chromite.api import controller
from chromite.contrib.sdk_server.grpc_server import sdk_server_pb2
from chromite.contrib.sdk_server.grpc_server import sdk_server_pb2_grpc
from chromite.contrib.sdk_server.grpc_server.chromite.api import api_pb2
from chromite.contrib.sdk_server.grpc_server.chromite.api import image_pb2
from chromite.contrib.sdk_server.grpc_server.chromite.api import sdk_pb2
from chromite.contrib.sdk_server.grpc_server.chromite.api import sysroot_pb2
from chromite.contrib.sdk_server.grpc_server.chromiumos import common_pb2
from chromite.lib import build_query
from chromite.lib import chroot_lib
from chromite.lib import constants
from chromite.lib import cros_sdk_lib
from chromite.lib import osutils
from chromite.lib import sysroot_lib


STRICT_SUDO = False
ERROR_OCCURRED = "ERROR OCCURRED"
VALID_RETURN_CODES = (
    controller.RETURN_CODE_SUCCESS,
    controller.RETURN_CODE_UNSUCCESSFUL_RESPONSE_AVAILABLE,
)


def IsInsideChroot():
    """Returns True if we are inside chroot.

    See: from cros_build_lib.py
    """
    return os.path.exists("/etc/cros_chroot_version")


def AsyncRun(
    cmd,
    cwd=None,
    env=None,
    shell=False,
    extra_env=None,
    enter_chroot=False,
    chroot_args=None,
    stdout=None,
    stderr=None,
    encoding=None,
    debug_level=logging.INFO,
):
    """Asynchronous implementation of cros_build_lib.run.

    Returns subprocess.Popen instead of CompletedProcess
    """
    # Taken from cros_build_lib.run

    # Quick check the command.  This helps when RunCommand is deep in the call
    # chain, but the command itself was constructed along the way.
    if isinstance(cmd, (str, bytes)):
        if not shell:
            raise ValueError("Cannot run a string command without a shell")
        cmd = ["/bin/bash", "-c", cmd]
        shell = False
    elif shell:
        raise ValueError("Cannot run an array command with a shell")
    elif not cmd:
        raise ValueError("Missing command to run")

    env = env.copy() if env is not None else os.environ.copy()
    env["LC_MESSAGES"] = "C"
    env.update(extra_env if extra_env else {})
    if enter_chroot and not IsInsideChroot():
        wrapper = ["cros_sdk"]
        if cwd:
            # If the current working directory is set, try to find cros_sdk
            # relative to cwd. Generally cwd will be the buildroot therefore we
            # want to use {cwd}/chromite/bin/cros_sdk. For more info PTAL at
            # crbug.com/432620
            path = cwd / constants.CHROMITE_BIN_SUBDIR / "cros_sdk"
            if os.path.exists(path):
                wrapper = [path]

        if chroot_args:
            wrapper += chroot_args

        if extra_env:
            wrapper.extend("%s=%s" % (k, v) for k, v in extra_env.items())

        cmd = wrapper + ["--"] + cmd

    proc = None
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=stdout,
            stderr=stderr,
            shell=False,
            env=env,
            close_fds=True,
            encoding=encoding,
        )
        return proc
    except:
        raise Exception("Popen failed")


class TempMemLogger(logging.Logger):
    """Wrapper for logging.logger and MemoryHandler.

    logger used to buffer messages before adding to log file
    """

    def __init__(self, target, capacity=4000):
        self.file = tempfile.NamedTemporaryFile(mode="a", delete=True)
        super().__init__(self.file.name)
        self.handler = handlers.MemoryHandler(capacity=capacity)
        self.handler.setTarget(target)
        self.addHandler(self.handler)

    def clean_up(self):
        self.handler.close()
        self.file.close()


class SdkImage:
    """Chroot Image class"""

    def __init__(
        self,
        path: Union[str, os.PathLike],
        latest: bool = False,
        image_type=None,
    ):
        self.path = path
        self.latest = latest
        self.name = os.path.split(str(path).rstrip("/"))[1]
        self.last_modified = time.ctime(os.path.getmtime(path))
        self.date_created = time.ctime(os.path.getctime(path))
        self.packages = []
        self.image_type = image_type

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.name


class SdkSysroot(sysroot_lib.Sysroot):
    """Wrapper for sysroot_lib.Sysroot class."""

    def __init__(self, path: Union[str, os.PathLike], name):
        super().__init__(path)
        self.name = name
        self.images = []
        self.packages = []
        self.get_images()

    def get_images(self):
        path = constants.SOURCE_ROOT / "src" / "build" / "images" / self.name
        self.images = []
        latest_target = None

        if not path.exists():
            return

        latest_path = path / "latest"
        if latest_path.exists():
            latest_target = latest_path.resolve()

            type_name = glob.glob("chromiumos*.bin", root_dir=latest_target)[0]
            image_type = constants.IMAGE_NAME_TO_TYPE[type_name]
            image_obj = SdkImage(
                latest_target, latest=True, image_type=image_type
            )
            self.images.append(image_obj)

        for image in path.iterdir():
            if image not in (latest_target, latest_path):
                type_name = glob.glob("chromiumos*.bin", root_dir=image)[0]
                image_type = constants.IMAGE_NAME_TO_TYPE[type_name]
                image_obj = SdkImage(image, latest=True, image_type=image_type)
                self.images.append(image_obj)

        return self.images


class SdkChroot(
    chroot_lib.Chroot, sdk_server_pb2_grpc.sdk_server_serviceServicer
):
    """Wrapper for chroot_lib Chroot class."""

    def __init__(self, path: Union[str, os.PathLike] = None):
        chroot_lib.Chroot.__init__(self, path)
        self.date_created = None
        self.version = None
        self.valid_version = None
        self._update_chroot_info()
        self.sysroots = []

        self.logs_folder = Path.cwd() / "logs"
        self.log_path = self.logs_folder / "log"
        if not Path(self.logs_folder).exists():
            osutils.Touch(self.log_path, makedirs=True)
        osutils.WriteFile(self.log_path, "")

        self.handler = logging.FileHandler(filename=self.log_path)
        self.all_possible_boards = []
        self.handler.setLevel(logging.DEBUG)

    def custom_endpoint(self, request, context):
        """Runs a chosen BAPI endpoint."""
        logger = TempMemLogger(target=self.handler)
        req_time = datetime.datetime.now(datetime.timezone.utc).timestamp()
        logger.info("REQUEST: %s %s", req_time, request.endpoint)
        with tempfile.NamedTemporaryFile(mode="w+") as tempinput:
            with tempfile.NamedTemporaryFile(mode="w+") as tempoutput:
                input_content = request.request
                osutils.WriteFile(tempinput.name, input_content)
                process = self._run_endpoint(
                    request.endpoint, tempinput.name, tempoutput.name
                )

                for line in iter(lambda: process.stdout.readline(), ""):
                    logger.info(line)
                    response = sdk_server_pb2.CustomResponse(logging_info=line)
                    yield response

                process.communicate()
                contents = osutils.ReadFile(tempoutput.name)
                response = sdk_server_pb2.CustomResponse()
                self._update_chroot_info()
                if process.returncode in VALID_RETURN_CODES:
                    response.response = contents
                    process.stdout.close()
                    yield response
                else:
                    logger.info(ERROR_OCCURRED)
                    response.logging_info = ERROR_OCCURRED
                    process.stdout.close()
                    yield response

                logger.clean_up()

    def get_methods(self, request, context):
        """Calls MethodGet BAPI endpoint."""
        with tempfile.NamedTemporaryFile(mode="w+") as tempinput:
            with tempfile.NamedTemporaryFile(mode="w+") as tempoutput:
                tempinput.write("{}")
                tempinput.seek(0)

                process = self._run_endpoint(
                    "chromite.api.MethodService/Get",
                    tempinput.name,
                    tempoutput.name,
                )
                process.communicate()
                contents = osutils.ReadFile(tempoutput.name)
                response = sdk_server_pb2.MethodsResponse()
                internal_resp = api_pb2.MethodGetResponse()
                json_format.Parse(contents, internal_resp)
                response.response.CopyFrom(internal_resp)
                process.stdout.close()
                return response

    def clear_logs(self, request, context):
        """Clears current log file."""
        prev_size = self.log_path.stat().st_size
        osutils.WriteFile(self.log_path, "")
        new_size = self.log_path.stat().st_size
        response = sdk_server_pb2.ClearLogsResponse(
            bytes_cleared=prev_size,
            new_size=new_size,
        )
        return response

    def _update_chroot_info(self):
        """Collects general information about the chroot."""
        if Path(self.path).exists():
            self.date_created = time.ctime(os.path.getctime(self.path))
            self.version = cros_sdk_lib.GetChrootVersion(self.path)
            self.valid_version = cros_sdk_lib.IsChrootVersionValid(self.path)

    def chroot_info(self, request, context):
        """Sends general information about the chroot via grpc."""
        path_exists = Path(self.path).exists()
        is_ready = cros_sdk_lib.IsChrootReady(self.path)
        ready = path_exists and is_ready
        self._update_chroot_info()
        response = None
        if not path_exists:
            response = sdk_server_pb2.ChrootInfoResponse(ready=ready)
        else:
            response = sdk_server_pb2.ChrootInfoResponse(
                ready=ready,
                date_created=self.date_created,
                valid_version=self.valid_version,
                path=common_pb2.Path(path=self.path),
                version=sdk_pb2.ChrootVersion(version=self.version),
            )
        return response

    def get_logs(self, request, context):
        """Sends a formated copy of current log file"""
        logfile = self.handler.baseFilename
        logs = []
        with open(logfile, "r+") as f:
            log_splits = f.read().split("REQUEST: ")[1:]
            for log in log_splits:
                splits = log.split()
                log_time = splits[0]
                command = splits[1]
                message = sdk_server_pb2.LogMessage(
                    command=command, time=log_time, logs=log
                )
                logs.append(message)
        response = sdk_server_pb2.LogsResponse(logs=logs)
        return response

    def current_boards(self, request, context):
        logger = TempMemLogger(target=self.handler)
        req_time = datetime.datetime.now(datetime.timezone.utc).timestamp()
        logger.info("REQUEST: %s current_boards", req_time)
        boards = []
        if self.has_path("/build"):
            path = Path(self.full_path("/build/"))
            self.sysroots = []
            for sysroot in path.iterdir():
                sysroot_path = self.full_path(f"/build/{sysroot}")
                sysroot_obj = SdkSysroot(sysroot_path, sysroot.name)
                self.sysroots.append(sysroot_obj)

                build_target = common_pb2.BuildTarget(name=sysroot.name)
                latest = None
                images = []
                for image in sysroot_obj.images:
                    type_str = "IMAGE_TYPE_UNDEFINED"
                    if image.image_type == constants.IMAGE_TYPE_FACTORY_SHIM:
                        type_str = constants.IMAGE_TYPE_FACTORY
                    elif image.image_type:
                        type_str = f"IMAGE_TYPE_{image.image_type.upper()}"

                    image_type = common_pb2.ImageType.Value(type_str)
                    image_msg = image_pb2.Image(
                        path=str(image.path),
                        build_target=build_target,
                        type=image_type,
                    )
                    if image.latest:
                        latest = image_msg
                    images.append(image_msg)

                board_images = sdk_server_pb2.BoardImages(
                    build_target=build_target, images=images, latest=latest
                )
                boards.append(board_images)

            response = sdk_server_pb2.CurrentBoardsResponse(board_images=boards)
            logger.clean_up()
            return response

        # "/build" does not exist i.e. chroot has no boards
        return sdk_server_pb2.CurrentBoardsResponse()

    def query_boards(self, request, context):
        """Runs `cros query boards`."""
        logger = TempMemLogger(target=self.handler)
        req_time = datetime.datetime.now(datetime.timezone.utc).timestamp()
        logger.info("REQUEST: %s query_boards", req_time)

        query = build_query.Query(build_query.Board)
        boards = [common_pb2.BuildTarget(name=board.name) for board in query]
        self.all_possible_boards = boards
        response = sdk_server_pb2.QueryBoardsResponse(build_target=boards)
        return response

    def repo_sync(self, request, context):
        """Runs `repo sync`."""
        logger = TempMemLogger(target=self.handler)
        req_time = datetime.datetime.now(datetime.timezone.utc).timestamp()
        logger.info("REQUEST: %s repo_sync", req_time)
        script = ["repo", "sync"]
        process = AsyncRun(
            script,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
        )

        for line in iter(lambda: process.stdout.readline(), ""):
            logger.info(line)
            response = sdk_server_pb2.RepoSyncResponse(logging_info=line)
            yield response

    def repo_status(self, request, context):
        """Runs `repo status`."""
        logger = TempMemLogger(target=self.handler)
        req_time = datetime.datetime.now(datetime.timezone.utc).timestamp()
        logger.info("REQUEST: %s repo_status", req_time)
        script = ["repo", "status"]
        process = AsyncRun(script, stdout=subprocess.PIPE, encoding="utf-8")
        output = []
        for line in iter(lambda: process.stdout.readline(), ""):
            output.append(line)
        response = sdk_server_pb2.RepoStatusResponse(info=output)
        return response

    def update_chroot(self, request, context):
        """Runs the update chroot BAPI endpoint."""
        logger = TempMemLogger(target=self.handler)
        req_time = datetime.datetime.now(datetime.timezone.utc).timestamp()
        logger.info("REQUEST: %s update_chroot", req_time)
        with tempfile.NamedTemporaryFile(mode="w+") as tempinput:
            with tempfile.NamedTemporaryFile(mode="w+") as tempoutput:
                input_content = json_format.MessageToDict(request.request)
                json.dump(input_content, tempinput)
                tempinput.seek(0)

                endpoint = "chromite.api.SdkService/Update"

                process = self._run_endpoint(
                    endpoint, tempinput.name, tempoutput.name
                )

                for line in iter(lambda: process.stdout.readline(), ""):
                    logger.info(line)
                    response = sdk_server_pb2.UpdateChrootResponse(
                        logging_info=line
                    )
                    yield response

                contents = osutils.ReadFile(tempoutput.name)
                response = sdk_server_pb2.UpdateChrootResponse()
                internal_resp = sdk_pb2.UpdateResponse()
                process.communicate()
                self._update_chroot_info()
                if process.returncode in VALID_RETURN_CODES:
                    json_format.Parse(contents, internal_resp)
                    self.version = internal_resp.version.version
                    response.response.CopyFrom(internal_resp)
                    process.stdout.close()
                    yield response
                else:
                    logger.info(ERROR_OCCURRED)
                    response.logging_info = ERROR_OCCURRED
                    process.stdout.close()
                    yield response

                logger.clean_up()

    def cros_workon_info(self, request, context):
        """Runs `cros workon info` for a given package.

        if build_target not specified will run with --host enabled
        """
        package = request.package_info.package_name

        target = (
            f"--board={request.build_target.name}"
            if request.build_target
            else "--host"
        )

        script = ["cros", "workon", target, "info", package]
        process = AsyncRun(
            script,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
        )
        output = []
        for line in iter(lambda: process.stdout.readline(), ""):
            output.append(line)

        output = "".join(output)

        response = sdk_server_pb2.WorkonInfoResponse(info=output)
        return response

    def cros_workon_start(self, request, context):
        """Runs `cros workon start` for a given package.

        if build_target not specified will run with --host enabled
        """
        package = request.package_info.package_name
        target = (
            f"--board={request.build_target.name}"
            if request.build_target
            else "--host"
        )

        script = ["cros", "workon", target, "start", package]
        process = AsyncRun(
            script,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
        )
        output = []
        for line in iter(lambda: process.stdout.readline(), ""):
            output.append(line)

        output = "".join(output)

        response = sdk_server_pb2.WorkonStartResponse(info=output)
        return response

    def cros_workon_stop(self, request, context):
        """Runs `cros workon stop` for a given package.

        if build_target not specified will run with --host enabled
        """
        package = request.package_info.package_name
        target = (
            f"--board={request.build_target.name}"
            if request.build_target
            else "--host"
        )

        script = ["cros", "workon", target, "stop", package]
        process = AsyncRun(
            script,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
        )
        output = []
        for line in iter(lambda: process.stdout.readline(), ""):
            output.append(line)

        output = "".join(output)

        response = sdk_server_pb2.WorkonStopResponse(info=output)
        return response

    def cros_workon_list(self, request, context):
        """Runs `cros workon list`.

        if build_target not specified will run with --host enabled
        """
        target = (
            f"--board={request.build_target.name}"
            if request.build_target
            else "--host"
        )

        script = ["cros", "workon", "list", target]
        process = AsyncRun(script, stdout=subprocess.PIPE, encoding="utf-8")
        output = []
        for line in iter(lambda: process.stdout.readline(), ""):
            output.append(line)

        packages = [
            common_pb2.PackageInfo(package_name=package) for package in output
        ]
        response = sdk_server_pb2.WorkonListResponse(package_info=packages)
        return response

    def all_packages(self, request, context):
        """Runs `cros workon --all list`."""
        target = (
            f"--board={request.build_target.name}"
            if request.build_target
            else "--host"
        )

        script = ["cros", "workon", target, "--all", "list"]

        process = AsyncRun(script, stdout=subprocess.PIPE, encoding="utf-8")
        output = []
        for line in iter(lambda: process.stdout.readline(), ""):
            output.append(line)
        packages = [
            common_pb2.PackageInfo(package_name=package) for package in output
        ]
        response = sdk_server_pb2.AllPackagesResponse(package_info=packages)
        return response

    def _run_endpoint(self, endpoint, inputfile, outputfile):
        """calls a BAPI endpoint."""
        script = [
            constants.CHROMITE_BIN_DIR / "build_api",
            endpoint,
            "--input-json",
            inputfile,
            "--output-json",
            outputfile,
            "--debug",
        ]

        process = AsyncRun(
            script,
            stderr=subprocess.STDOUT,
            stdout=subprocess.PIPE,
            encoding="utf-8",
        )
        return process

    def create_sdk(self, request, context):
        """Runs create sdk BAPI endpoint."""
        logger = TempMemLogger(target=self.handler)
        req_time = datetime.datetime.now(datetime.timezone.utc).timestamp()
        logger.info("REQUEST: %s create_sdk", req_time)
        with tempfile.NamedTemporaryFile(mode="w+") as tempinput:
            with tempfile.NamedTemporaryFile(mode="w+") as tempoutput:
                input_content = json_format.MessageToDict(request.request)
                json.dump(input_content, tempinput)
                tempinput.seek(0)

                endpoint = "chromite.api.SdkService/Create"
                process = self._run_endpoint(
                    endpoint, tempinput.name, tempoutput.name
                )

                for line in iter(lambda: process.stdout.readline(), ""):
                    logger.info(line)
                    response = sdk_server_pb2.CreateSdkResponse(
                        logging_info=line
                    )
                    yield response

                contents = osutils.ReadFile(tempoutput.name)
                response = sdk_server_pb2.CreateSdkResponse()
                internal_resp = sdk_pb2.CreateResponse()
                self._update_chroot_info()
                process.communicate()
                if process.returncode in VALID_RETURN_CODES:
                    json_format.Parse(contents, internal_resp)
                    self.version = internal_resp.version.version
                    response.response.CopyFrom(internal_resp)
                    process.stdout.close()
                    yield response
                else:
                    logger.info(ERROR_OCCURRED)
                    response.logging_info = ERROR_OCCURRED
                    process.stdout.close()
                    yield response

                logger.clean_up()

    def replace_sdk(self, request, context):
        """Runs create sdk BAPI endpoint with `no_repalce = False`."""
        logger = TempMemLogger(target=self.handler)
        req_time = datetime.datetime.now(datetime.timezone.utc).timestamp()
        logger.info("REQUEST: %s replace_sdk", req_time)

        with tempfile.NamedTemporaryFile(mode="w+") as tempinput:
            with tempfile.NamedTemporaryFile(mode="w+") as tempoutput:
                input_content = json_format.MessageToDict(request.request)
                json.dump(input_content, tempinput)
                tempinput.seek(0)

                endpoint = "chromite.api.SdkService/Create"

                process = self._run_endpoint(
                    endpoint, tempinput.name, tempoutput.name
                )

                for line in iter(lambda: process.stdout.readline(), ""):
                    logger.info(line)
                    response = sdk_server_pb2.ReplaceSdkResponse(
                        logging_info=line
                    )
                    yield response

                contents = osutils.ReadFile(tempoutput.name)
                response = sdk_server_pb2.ReplaceSdkResponse()
                internal_resp = sdk_pb2.CreateResponse()

                process.communicate()
                if process.returncode in VALID_RETURN_CODES:
                    json_format.Parse(contents, internal_resp)
                    response.response.CopyFrom(internal_resp)
                    process.stdout.close()
                    yield response
                else:
                    logger.info(ERROR_OCCURRED)
                    response.logging_info = ERROR_OCCURRED
                    process.stdout.close()
                    yield response

                logger.clean_up()

    def delete_sdk(self, request, context):
        """Runs delete sdk BAPI endpoint."""
        logger = TempMemLogger(target=self.handler)
        req_time = datetime.datetime.now(datetime.timezone.utc).timestamp()
        logger.info("REQUEST: %s delete_sdk", req_time)

        with tempfile.NamedTemporaryFile(mode="w+") as tempinput:
            with tempfile.NamedTemporaryFile(mode="w+") as tempoutput:
                input_content = json_format.MessageToDict(request.request)
                json.dump(input_content, tempinput)
                tempinput.seek(0)

                endpoint = "chromite.api.SdkService/Delete"

                process = self._run_endpoint(
                    endpoint, tempinput.name, tempoutput.name
                )

                for line in iter(lambda: process.stdout.readline(), ""):
                    logger.info(line)
                    response = sdk_server_pb2.DeleteSdkResponse(
                        logging_info=line
                    )
                    yield response

                contents = osutils.ReadFile(tempoutput.name)
                response = sdk_server_pb2.DeleteSdkResponse()
                internal_resp = sdk_pb2.DeleteResponse()

                process.communicate()
                if process.returncode in VALID_RETURN_CODES:
                    json_format.Parse(contents, internal_resp)
                    response.response.CopyFrom(internal_resp)
                    process.stdout.close()
                    yield response
                else:
                    logger.info(ERROR_OCCURRED)
                    response.logging_info = ERROR_OCCURRED
                    process.stdout.close()
                    yield response

                logger.clean_up()

    def build_packages(self, request, context):
        """Runs runs build packages BAPI endpoint.

        Calls the following endpoints:
            Sysroot create
            install toolcahin
            build packages
        """
        logger = TempMemLogger(target=self.handler)
        req_time = datetime.datetime.now(datetime.timezone.utc).timestamp()
        logger.info("REQUEST: %s build_packages", req_time)
        create_req = request.create_req
        toolchain_req = request.toolchain_req
        packages_req = request.packages_req
        error = False
        logger.info("Calling Sysroot_create")

        # TODO: ask about best way to handle bapi errors
        create_resp = None
        for response in self._sysroot_create(create_req, logger):
            if response.logging_info == ERROR_OCCURRED:
                error = True
            create_resp = response
            yield response
        sysroot = create_resp.create_resp.sysroot

        toolchain_req.sysroot.CopyFrom(sysroot)
        logger.info("Calling Sysroot_install_toolchain")
        if not error:
            for response in self._install_toolchain(toolchain_req, logger):
                if response.logging_info == ERROR_OCCURRED:
                    error = True
                yield response

        packages_req.sysroot.CopyFrom(sysroot)
        logger.info("Calling Sysroot_install_packages")
        if not error:
            for response in self._install_packages(packages_req, logger):
                yield response

        logger.clean_up()

    def _sysroot_create(self, request, logger):
        """Calls BAPI sysroot_create endpoint."""

        with tempfile.NamedTemporaryFile(mode="w+") as tempinput:
            with tempfile.NamedTemporaryFile(mode="w+") as tempoutput:
                input_content = json_format.MessageToDict(request)
                json.dump(input_content, tempinput)
                tempinput.seek(0)

                endpoint = "chromite.api.SysrootService/Create"

                process = self._run_endpoint(
                    endpoint, tempinput.name, tempoutput.name
                )

                for line in iter(lambda: process.stdout.readline(), ""):
                    logger.info(line)
                    response = sdk_server_pb2.BuildPackagesResponse(
                        logging_info=line
                    )
                    yield response

                contents = osutils.ReadFile(tempoutput.name)
                response = sdk_server_pb2.BuildPackagesResponse()
                internal_resp = sysroot_pb2.SysrootCreateResponse()
                process.communicate()
                if process.returncode in VALID_RETURN_CODES:
                    json_format.Parse(contents, internal_resp)
                    response.create_resp.CopyFrom(internal_resp)
                    process.stdout.close()
                    yield response
                else:
                    logger.info(ERROR_OCCURRED)
                    response.logging_info = ERROR_OCCURRED
                    process.stdout.close()
                    yield response

    def _install_toolchain(self, request, logger):
        """Calls BAPI install_toolchain endpoint."""

        with tempfile.NamedTemporaryFile(mode="w+") as tempinput:
            with tempfile.NamedTemporaryFile(mode="w+") as tempoutput:
                input_content = json_format.MessageToDict(request)
                json.dump(input_content, tempinput)
                tempinput.seek(0)

                endpoint = "chromite.api.SysrootService/InstallToolchain"

                process = self._run_endpoint(
                    endpoint, tempinput.name, tempoutput.name
                )

                for line in iter(lambda: process.stdout.readline(), ""):
                    logger.info(line)
                    response = sdk_server_pb2.BuildPackagesResponse(
                        logging_info=line
                    )
                    yield response

                contents = osutils.ReadFile(tempoutput.name)
                response = sdk_server_pb2.BuildPackagesResponse()
                internal_resp = sysroot_pb2.InstallToolchainResponse()
                process.communicate()
                if process.returncode in VALID_RETURN_CODES:
                    json_format.Parse(contents, internal_resp)
                    response.toolchain_resp.CopyFrom(internal_resp)
                    process.stdout.close()
                    yield response
                else:
                    logger.info(ERROR_OCCURRED)
                    response.logging_info = ERROR_OCCURRED
                    process.stdout.close()
                    yield response

    def _install_packages(self, request, logger):
        """Calls BAPI install_toolchain endpoint."""

        with tempfile.NamedTemporaryFile(mode="w+") as tempinput:
            with tempfile.NamedTemporaryFile(mode="w+") as tempoutput:
                input_content = json_format.MessageToDict(request)
                json.dump(input_content, tempinput)
                tempinput.seek(0)

                endpoint = "chromite.api.SysrootService/InstallPackages"

                process = self._run_endpoint(
                    endpoint, tempinput.name, tempoutput.name
                )

                for line in iter(lambda: process.stdout.readline(), ""):
                    logger.info(line)
                    response = sdk_server_pb2.BuildPackagesResponse(
                        logging_info=line
                    )
                    yield response

                contents = osutils.ReadFile(tempoutput.name)
                response = sdk_server_pb2.BuildPackagesResponse()
                internal_resp = sysroot_pb2.InstallPackagesResponse()
                process.communicate()
                if process.returncode in VALID_RETURN_CODES:
                    json_format.Parse(contents, internal_resp)
                    response.packages_resp.CopyFrom(internal_resp)
                    process.stdout.close()
                    yield response
                else:
                    logger.info(ERROR_OCCURRED)
                    response.logging_info = ERROR_OCCURRED
                    process.stdout.close()
                    yield response

    def build_image(self, request, context):
        """Calls BAPI create image endpoint."""
        logger = TempMemLogger(target=self.handler)
        req_time = datetime.datetime.now(datetime.timezone.utc).timestamp()
        logger.info("REQUEST: %s build_image", req_time)

        with tempfile.NamedTemporaryFile(mode="w+") as tempinput:
            with tempfile.NamedTemporaryFile(mode="w+") as tempoutput:
                input_content = json_format.MessageToDict(request.request)
                json.dump(input_content, tempinput)
                tempinput.seek(0)

                endpoint = "chromite.api.ImageService/Create"

                process = self._run_endpoint(
                    endpoint, tempinput.name, tempoutput.name
                )

                for line in iter(lambda: process.stdout.readline(), ""):
                    logger.info(line)
                    response = sdk_server_pb2.BuildImageResponse(
                        logging_info=line
                    )
                    yield response

                contents = osutils.ReadFile(tempoutput.name)
                response = sdk_server_pb2.BuildImageResponse()
                internal_resp = image_pb2.CreateImageResult()

                process.communicate()
                if process.returncode in VALID_RETURN_CODES:
                    json_format.Parse(contents, internal_resp)
                    response.response.CopyFrom(internal_resp)
                    process.stdout.close()
                    yield response
                else:
                    logger.info(ERROR_OCCURRED)
                    response.logging_info = ERROR_OCCURRED
                    process.stdout.close()
                    yield response

                logger.clean_up()
