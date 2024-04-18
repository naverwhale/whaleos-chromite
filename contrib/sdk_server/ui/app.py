# !/usr/bin/env vpython3
# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Flask app main file for frontend."""

import os
from pathlib import Path
import socket
from typing import List, Optional

# pylint: disable=import-error
import flask
from google.protobuf import json_format

from chromite.api.controller import controller_util
from chromite.contrib.sdk_server.grpc_server import client
from chromite.contrib.sdk_server.grpc_server import sdk_server_pb2
from chromite.contrib.sdk_server.grpc_server.chromite.api import image_pb2
from chromite.contrib.sdk_server.grpc_server.chromite.api import sdk_pb2
from chromite.contrib.sdk_server.grpc_server.chromite.api import sysroot_pb2
from chromite.contrib.sdk_server.grpc_server.chromiumos import (
    common_pb2 as common,
)
from chromite.lib.parser import package_info


UI_DIR = Path(__file__).parent
app = flask.Flask(
    "SDK Server",
    template_folder=UI_DIR / "templates",
    static_folder=UI_DIR / "static",
)

index_data = {}

# Code 204 "No content" for endpoints which just execute a function.
NO_RESPONSE_OK = ("", 204)

COMMANDS_TO_IGNORE = (
    "cros_workon_info",
    "current_boards",
    "cros_workon_list",
    "cros_workon_start",
    "cros_workon_stop",
)


def logGenerator(endpoint, req):
    """Utility generator for endpoints with long logs."""

    for response in endpoint(req):
        if response.logging_info:
            yield response.logging_info


@app.route("/get-logs", methods=["GET", "POST"])
def get_logs():
    if flask.request.method != "POST":
        return flask.redirect(flask.url_for("index"))

    logsResponse = client.get_logs(sdk_server_pb2.LogsRequest())
    resp = []
    for log in logsResponse.logs:
        if log.command not in COMMANDS_TO_IGNORE:
            second_line = log.logs.index("\n\n") + 2

            # Internal logger adds a second newline to output which
            # already has them. Remove them to make it more readable.
            log.logs = log.logs[second_line:].replace("\n\n", "\n")

            resp += [json_format.MessageToDict(log)]

    return flask.jsonify(resp[-1::-1])


@app.route("/clear-logs", methods=["GET", "POST"])
def clear_logs():
    """Clears log files."""

    if flask.request.method != "POST":
        return flask.redirect(flask.url_for("index"))

    req = sdk_server_pb2.ClearLogsRequest()
    client.clear_logs(req)

    return NO_RESPONSE_OK


@app.route("/workon-start", methods=["GET", "POST"])
def workon_start():
    if flask.request.method != "POST":
        # Handles user just going to /workon-start, rather than via the button.
        return flask.redirect(flask.url_for("index"))

    board = flask.request.json["board"]
    package = flask.request.json["package"]

    parsed_pkg = package_info.parse(package)
    package = common.PackageInfo()
    controller_util.serialize_package_info(parsed_pkg, package)

    req = sdk_server_pb2.WorkonStartRequest(
        build_target=common.BuildTarget(name=board),
        package_info=package,
    )
    client.cros_workon_start(req)

    return NO_RESPONSE_OK


@app.route("/workon-stop", methods=["GET", "POST"])
def workon_stop():
    if flask.request.method != "POST":
        # Handles user just going to /workon-stop, rather than via the button.
        return flask.redirect(flask.url_for("index"))

    board = flask.request.json["board"]
    package = flask.request.json["package"]

    parsed_pkg = package_info.parse(package)
    package = common.PackageInfo()
    controller_util.serialize_package_info(parsed_pkg, package)

    req = sdk_server_pb2.WorkonStopRequest(
        build_target=common.BuildTarget(name=board),
        package_info=package,
    )

    client.cros_workon_stop(req)

    return NO_RESPONSE_OK


@app.route("/repo-refresh", methods=["GET", "POST"])
def repo_refresh():
    """App route to run gRPC repo status endpoint and parse."""

    if flask.request.method != "POST":
        # GET (user visiting URL) redirects to homepage.
        return flask.redirect(flask.url_for("index"))

    # POST only sent by script.
    response = client.repo_status(sdk_server_pb2.RepoStatusRequest())

    project = ""
    branch = ""
    files = []
    for line in response.info:
        text = line.split()
        if text[0] == "project":
            project = text[1]
            branch = text[3]
        else:
            files += [
                {"file": text[1], "head": text[0][0], "working": text[0][1]}
            ]

    # Returns dict-like format which JS parses into HTML.
    return flask.jsonify(
        {
            "project": project,
            "branch": branch,
            "files": files,
        }
    )


@app.route("/repo-sync", methods=["GET", "POST"])
def repo_sync():
    """Enacts repo sync and streams logging data."""

    if flask.request.method != "POST":
        return flask.redirect(flask.url_for("index"))

    req = sdk_server_pb2.RepoSyncRequest()

    return flask.Response(logGenerator(client.repo_sync, req))


@app.route("/get-packages", methods=["GET", "POST"])
def get_packages():
    """App route to get packages from gRPC server."""

    if flask.request.method != "POST":
        # GET (user visiting URL) redirects to homepage.
        return flask.redirect(flask.url_for("index"))

    # POST only sent by script.
    packages_json = {}
    boards_to_get = []

    # May request just for a single board (when updating from stop/start),
    # but default should be all boards (for page loading).
    if flask.request.json["board"]:
        boards_to_get = [
            sdk_server_pb2.BoardImages(
                build_target=common.BuildTarget(
                    name=flask.request.json["board"]
                )
            )
        ]
    else:
        boards_to_get = client.current_boards(
            sdk_server_pb2.CurrentBoardsRequest()
        ).board_images

    for board in boards_to_get:
        req = sdk_server_pb2.WorkonListRequest(build_target=board.build_target)
        board_packages = (client.cros_workon_list(req)).package_info
        board_packages_data = []

        for pkg_msg in board_packages:
            req = sdk_server_pb2.WorkonInfoRequest(
                build_target=board.build_target, package_info=pkg_msg
            )

            # Parse info for modals.
            _, repo, source = client.cros_workon_info(req).info.split(" ")
            repo = repo.split(",")
            source = source.split(",")

            pkg = controller_util.deserialize_package_info(pkg_msg)
            board_packages_data += [
                {
                    "name": pkg.atom.strip(),
                    "repo": repo,
                    "source": source,
                }
            ]

        board_images_data = []
        for image in board.images:
            board_images_data += [
                {
                    "path": image.path,
                    "type": common.ImageType.Name(image.type),
                    "latest": (image == board.latest),
                }
            ]

        packages_json[board.build_target.name] = {
            "images": board_images_data,
            "packages": board_packages_data,
        }

    return flask.jsonify(packages_json)


@app.route("/update-chroot", methods=["GET", "POST"])
def update_chroot():
    """App route to call BAPI Update."""

    if flask.request.method != "POST":
        return flask.redirect(flask.url_for("index"))

    flags = sdk_pb2.UpdateRequest.Flags(
        build_source=flask.request.json["buildSource"],
        toolchain_changed=flask.request.json["toolchainChanged"],
    )

    targets = flask.request.json["toolchainTargets"]
    toolchain_targets = [common.BuildTarget(name=b) for b in targets]

    req = sdk_server_pb2.UpdateChrootRequest(
        request=sdk_pb2.UpdateRequest(
            flags=flags, toolchain_targets=toolchain_targets
        )
    )

    return flask.Response(logGenerator(client.update_chroot, req))


@app.route("/replace-chroot", methods=["GET", "POST"])
def replace_chroot():
    """Forwards requests for replace and create chroot endpoints."""
    if flask.request.method != "POST":
        return flask.redirect(flask.url_for("index"))

    flags = sdk_pb2.CreateRequest.Flags(
        no_replace=False,
        bootstrap=flask.request.json["bootstrap"],
        no_use_image=flask.request.json["noUseImage"],
    )

    req = sdk_server_pb2.ReplaceSdkRequest(
        request=sdk_pb2.CreateRequest(
            flags=flags, sdk_version=flask.request.json["version"]
        )
    )

    return flask.Response(logGenerator(client.replace_sdk, req))


@app.route("/delete-chroot", methods=["GET", "POST"])
def delete_sdk():
    """Calls delete SDK endpoint."""

    if flask.request.method != "POST":
        return flask.redirect(flask.url_for("index"))

    req = sdk_server_pb2.DeleteSdkRequest(request=sdk_pb2.DeleteRequest())

    return flask.Response(logGenerator(client.delete_sdk, req))


@app.route("/build-packages", methods=["GET", "POST"])
def build_packages():
    """Formulates/forwards all 3 requests for build packages endpoint."""
    if flask.request.method != "POST":
        return flask.redirect(flask.url_for("index"))

    package = ""
    if "package" in flask.request.json:
        package = flask.request.json["package"]

        parsed_pkg = package_info.parse(package)
        package = common.PackageInfo()
        controller_util.serialize_package_info(parsed_pkg, package)

    create_sysroot = sysroot_pb2.SysrootCreateRequest(
        flags=sysroot_pb2.SysrootCreateRequest.Flags(
            chroot_current=flask.request.json["chrootCurrent"],
            replace=flask.request.json["replace"],
            toolchain_changed=flask.request.json["toolchainChanged"],
            use_cq_prebuilts=flask.request.json["CQPrebuilts"],
        ),
        build_target=common.BuildTarget(name=flask.request.json["buildTarget"]),
    )

    install_toolchain = sysroot_pb2.InstallToolchainRequest(
        flags=sysroot_pb2.InstallToolchainRequest.Flags(
            compile_source=flask.request.json["compileSource"],
            toolchain_changed=flask.request.json["toolchainChanged"],
        )
    )

    install_packages = sysroot_pb2.InstallPackagesRequest(
        flags=sysroot_pb2.InstallPackagesRequest.Flags(
            compile_source=flask.request.json["compileSource"],
            toolchain_changed=flask.request.json["toolchainChanged"],
            dryrun=flask.request.json["dryrun"],
            workon=flask.request.json["workon"],
        ),
    )
    if package:
        install_packages.packages.append(package)

    req = sdk_server_pb2.BuildPackagesRequest(
        create_req=create_sysroot,
        toolchain_req=install_toolchain,
        packages_req=install_packages,
    )

    return flask.Response(logGenerator(client.build_packages, req))


@app.route("/build-image", methods=["GET", "POST"])
def build_image():
    """Forwards build image request to gRPC server."""

    if flask.request.method != "POST":
        return flask.redirect(flask.url_for("index"))

    # Converts strings to proto enum values.
    toEnum = common.ImageType.Value

    req = sdk_server_pb2.BuildImageRequest(
        request=image_pb2.CreateImageRequest(
            build_target=common.BuildTarget(
                name=flask.request.json["buildTarget"]
            ),
            image_types=[toEnum(im) for im in flask.request.json["imageTypes"]],
            disable_rootfs_verification=flask.request.json[
                "disableRootfsVerification"
            ],
            version=flask.request.json["version"],
            disk_layout=flask.request.json["diskLayout"],
            builder_path=flask.request.json["builderPath"],
            base_is_recovery=flask.request.json["baseIsRecovery"],
        )
    )
    return flask.Response(logGenerator(client.build_image, req))


@app.route("/chroot-info", methods=["GET", "POST"])
def chroot_info():
    """Fetches basic Chroot Info for panel."""

    if flask.request.method != "POST":
        return flask.redirect(flask.url_for("index"))

    return flask.jsonify(
        json_format.MessageToDict(
            client.chroot_info(sdk_server_pb2.ChrootInfoRequest())
        )
    )


@app.route("/custom", methods=["GET", "POST"])
def custom_endpoint():
    """Forwards custom endpoint/JSON request."""

    if flask.request.method != "POST":
        return flask.redirect(flask.url_for("index"))

    req = sdk_server_pb2.CustomRequest(
        endpoint=flask.request.json["endpoint"],
        request=flask.request.json["request"],
    )

    return flask.Response(logGenerator(client.custom_endpoint, req))


@app.route("/all-packages", methods=["GET", "POST"])
def all_packages():
    if flask.request.method != "POST":
        return flask.redirect(flask.url_for("index"))

    req = sdk_server_pb2.AllPackagesRequest(
        build_target=common.BuildTarget(name=flask.request.json["board"])
    )

    resp = client.all_packages(req)
    return flask.jsonify([p.package_name for p in resp.package_info])


@app.route("/", methods=["GET", "POST"])
def index():
    """Home page route. Renders index.html file with templating data."""

    return flask.render_template("index.html", data=index_data)


def setup():
    """Populates initial templating data from gRPC requests."""

    index_data["user"] = os.getlogin()
    index_data["hostname"] = socket.gethostname()

    all_boards = client.query_boards(sdk_server_pb2.QueryBoardsRequest())
    all_boards = sorted([b.name for b in all_boards.build_target])
    index_data["all_boards"] = all_boards

    # List of boards with active sysroots for packages display.
    current_boards = client.current_boards(
        sdk_server_pb2.CurrentBoardsRequest()
    )

    current_boards = sorted(
        [b.build_target.name for b in current_boards.board_images]
    )
    index_data["current_boards"] = current_boards

    all_endpoints = client.get_methods(sdk_server_pb2.MethodsRequest()).response
    all_endpoints = [m.method for m in all_endpoints.methods]
    index_data["all_endpoints"] = all_endpoints


# pylint: disable=unused-argument
def main(argv: Optional[List[str]]) -> Optional[int]:
    """Runs setup and hosts the Flask app."""

    setup()
    app.jinja_env.auto_reload = True
    app.run(debug=True, host="0.0.0.0")
