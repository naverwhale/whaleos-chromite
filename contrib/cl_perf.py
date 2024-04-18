# Copyright 2022 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Launch and process led jobs to test the performance of a gerrit CL."""

import datetime
import functools
import json
import logging
import os
from pathlib import Path
import shutil
import statistics
from typing import Dict, List, NamedTuple, Optional, Set

from chromite.lib import cipd
from chromite.lib import commandline
from chromite.lib import constants
from chromite.lib import cros_build_lib
from chromite.lib import path_util
from chromite.utils import pformat


_TESTS_FOLDER = Path(path_util.GetCacheDir()) / "cl-perf"

# _CHECKOUT_CIPD_ROOT_PATH is used to install `swarming`, if it's not in PATH.
_CHECKOUT_CIPD_ROOT_PATH = (
    Path(path_util.GetCacheDir()).absolute() / "cipd" / "packages"
)
_SWARMING_CIPD_PKG_NAME = "infra/tools/luci/swarming/linux-amd64"
_SWARMING_CIPD_PKG_VERSION = "latest"
_SWARMING_BIN_PATH = (
    _CHECKOUT_CIPD_ROOT_PATH / _SWARMING_CIPD_PKG_NAME / "swarming"
)

_FILENAME_TEST_PROPERTIES = "test-properties.json"
_FILENAME_TESTED_JOBS = "tested-jobs.json"
_FILENAME_BASELINE_JOBS = "baseline-jobs.json"


@functools.lru_cache(maxsize=None)
def get_led() -> Path:
    """Returns path to `led` utility."""
    wrong_led = "/usr/bin/led"

    installed_led = shutil.which("led")
    if installed_led is not None:
        if not os.path.isfile(wrong_led) or not os.path.samefile(
            installed_led, wrong_led
        ):
            return installed_led

    checkout_led = constants.DEPOT_TOOLS_DIR / "led"
    if not os.access(str(checkout_led), os.X_OK):
        cros_build_lib.Die("Install led utility and put it in your PATH")

    return checkout_led


def check_led_auth() -> None:
    """Checks that `led` utility is present in $PATH and is authenticated."""
    led = get_led()
    try:
        cmd = [
            led,
            "auth-info",
        ]
        cros_build_lib.dbg_run(cmd, capture_output=True)
    except cros_build_lib.RunCommandError as e:
        logging.fatal(e.stderr.decode("utf-8"))
        cros_build_lib.Die(
            f"""Login with led by running:
 {led} auth-login"""
        )


@functools.lru_cache(maxsize=None)
def get_swarming() -> Path:
    """Returns path to `swarming` utility (installs if necessary)."""
    # Try swarming from PATH.
    installed_swarming = shutil.which("swarming")
    if installed_swarming is not None:
        return installed_swarming

    # See if swarming was installed to chromite CIPD root.
    if _SWARMING_BIN_PATH.exists():
        return _SWARMING_BIN_PATH

    # Install swarming to chromite CIPD root.
    try:
        cipd.InstallPackage(
            cipd.GetCIPDFromCache(),
            _SWARMING_CIPD_PKG_NAME,
            _SWARMING_CIPD_PKG_VERSION,
            _CHECKOUT_CIPD_ROOT_PATH,
        )
    except cros_build_lib.RunCommandError as e:
        cros_build_lib.Die(e)

    if not os.access(str(_SWARMING_BIN_PATH), os.X_OK):
        cros_build_lib.Die(
            r"""Automatic installation of swarming failed.
 Install swarming tool manually and add it to your $PATH.
 To install, cd to your CIPD root (to create a new CIPD root, make a folder and
 run `cipd init` in it). Then, run the following command (as-is with \$ in it):
   cipd install -log-level=debug "infra/tools/luci/swarming/\${platform}"
 To add `swarming` to your $PATH, run the following command in your CIPD root:
   echo "export PATH=\$PATH:$(pwd)" >> ~/.bashrc && source ~/.bashrc"""
        )
    else:
        logging.notice("Installed swarming to %s", _SWARMING_BIN_PATH)
    return _SWARMING_BIN_PATH


def check_swarming_auth() -> None:
    """Checks that `swarming` utility exists and is authenticated."""
    swarming = get_swarming()
    try:
        cmd = [
            swarming,
            "whoami",
        ]
        cros_build_lib.dbg_run(cmd, capture_output=True)
    except cros_build_lib.RunCommandError as e:
        logging.fatal(e.stderr.decode("utf-8"))
        cros_build_lib.Die(
            f"""Login to swarming by running:
  {swarming} login"""
        )


def get_base_job_template(bucket: str, builder: str, debug: bool) -> str:
    """Returns the build job template for a given bucket + builder."""
    cmd = [
        get_led(),
        "get-builder",
        f"{bucket}:{builder}",
    ]
    try:
        result = cros_build_lib.run(
            cmd, print_cmd=debug, capture_output=True, encoding="utf-8"
        )
    except cros_build_lib.RunCommandError as e:
        cros_build_lib.Die(e)
    return result.stdout


def get_unique_test_name(
    bucket: str,
    builder: str,
    cls_tested: List[str],
    cls_baseline: Optional[List[str]],
) -> str:
    """Get unique name of the test, which will be a valid dir name in Linux."""
    bucket = bucket.replace("/", "-")
    builder = builder.replace("/", "-")
    cls_tested_str = "_".join(
        "-".join(x for x in cl.split("/") if x.isnumeric()) for cl in cls_tested
    )
    cls_baseline_str = "baseline"
    if cls_baseline is not None:
        cls_baseline_str = "_".join(
            "-".join(x for x in cl.split("/") if x.isnumeric())
            for cl in cls_baseline
        )
    test_name_base = (
        f"{bucket}-{builder}_{cls_tested_str}_vs_{cls_baseline_str}"
    )

    # May need to modify test_name_base to avoid collisions with existing tests.
    # Append test_name_id at the end.
    test_name_id = 1
    existing_tests = get_dirs_in_dir(_TESTS_FOLDER)
    test_name = test_name_base
    logging.debug("test_name_base: %s", test_name_base)
    logging.debug("existing_tests: %s", existing_tests)
    while test_name in existing_tests:
        test_name_id += 1
        test_name = f"{test_name_base}__{test_name_id}"
        logging.debug("test_name: %s", test_name)
    return test_name


def add_cls_to_job(job: str, cls: List[str], debug: bool) -> str:
    """Adds provided CL urls |cls| to the provided |job|."""
    for cl in cls:
        cmd = [
            get_led(),
            "edit-cr-cl",
            "-no-implicit-clear",
            cl,
        ]
        try:
            result = cros_build_lib.run(
                cmd,
                input=job,
                print_cmd=debug,
                encoding="utf-8",
                capture_output=True,
            )
            job = result.stdout
        except cros_build_lib.RunCommandError as e:
            cros_build_lib.Die(e)
    return job


def get_swarming_url(task_id: str, host_name: str) -> str:
    """Returns swarming URL for the provided |task_id| and |host_name|."""
    return f"https://ci.chromium.org/swarming/task/{task_id}?server={host_name}"


def get_dirs_in_dir(tests_folder: os.PathLike) -> List[str]:
    """Returns list of directories in provided directory."""
    if not os.path.isdir(tests_folder):
        return []
    return [f.name for f in os.scandir(tests_folder) if f.is_dir()]


def parse_swarming_datetime(ts: str) -> datetime.datetime:
    """Parses swarming-specific timestamp, format of which can vary."""
    ts_split = ts.split(".", 1)
    secs = ts_split[0]

    # datetime.strptime() is unable to handle nanoseconds at the end, thus
    # convert nanoseconds or any other precision to microseconds.
    if len(ts_split) == 1:
        # Timestamp may look like "2022-06-14T14:55:48Z" and does not contain
        # microsecs (i.e. microsecs == 0).
        microsecs = "0"
        if secs[-1].lower() == "z":
            # If there is a trailing 'Z' or 'z', remove it so that the timestamp
            # can be parsed correctly below.
            secs = secs[:-1]
    else:
        # Timestamp may look like "2022-06-14T14:55:48.123456Z" and contains
        # microsecs.
        microsecs = ts_split[1][:6]

    # 'Z' at the end can be either lower or upper case. Make it always upper.
    if microsecs[-1] == "Z":
        pass
    elif microsecs[-1] == "z":
        microsecs[-1] = "Z"
    elif microsecs[-1].isdigit():
        microsecs += "Z"
    else:
        raise ValueError(
            f"unexpected timestamp {ts}: "
            "microsecond part ends with {microsecs[-1]}"
        )
    new_ts = f"{secs}.{microsecs}"

    return datetime.datetime.strptime(new_ts, "%Y-%m-%dT%H:%M:%S.%fZ")


class TestResult:
    """TestResult holds total runtime and runtime of steps of a single build."""

    swarmingUrl: str
    task_id: str
    build_proto_json: Dict
    total_runtime: int  # seconds
    steps: Dict[str, int]  # (step_name, elasped_seconds)

    def __init__(self, swarmingUrl: str, task_id: str, build_proto_json: Dict):
        self.swarmingUrl = swarmingUrl
        self.task_id = task_id
        self.build_proto_json = build_proto_json
        self.steps = {}
        logging.debug(pformat.json(build_proto_json))
        logging.info("# Processing build %s", swarmingUrl)
        run_start_time = parse_swarming_datetime(
            build_proto_json["create_time"]
        )
        run_end_time = parse_swarming_datetime(build_proto_json["end_time"])
        self.total_runtime = (run_end_time - run_start_time).total_seconds()
        for step in build_proto_json["steps"]:
            step_start_time = parse_swarming_datetime(step["start_time"])
            step_end_time = parse_swarming_datetime(step["end_time"])
            step_name = step["name"]

            if "|" in step_name:
                # '|' appears in sub-steps, and that time is accounted for in
                # the main step. Skip it.
                continue
            status = step["status"]
            if status != "SUCCESS":
                logging.critical(
                    "%s step %s status: %s", swarmingUrl, step_name, status
                )

            elapsed_secs = (step_end_time - step_start_time).total_seconds()
            logging.info("%s took %s seconds", step_name, elapsed_secs)
            if step_name in self.steps:
                logging.critical(
                    "%s step %s is seen twice! overwriting.",
                    swarmingUrl,
                    step_name,
                )
            self.steps[step_name] = elapsed_secs

    def GetStepsNames(self) -> Set[str]:
        """Returns all build steps performed during the Test."""
        step_names = set()
        for step_name in self.steps:
            step_names.add(step_name)
        return step_names


class BuildResults(NamedTuple):
    """Data class for build results."""

    succeeded: List[TestResult]
    failed: List[TestResult]

    def append(self, test_result: TestResult, succeeded: bool = True) -> None:
        """Save a test result to the appropriate list."""
        if succeeded:
            self.succeeded.append(test_result)
        else:
            self.failed.append(test_result)


class SwarmingOutputProcessor:
    """Holds output from swarming and compares results."""

    baseline: List[TestResult]
    tested: List[TestResult]
    repeats: int
    complete: bool
    failed_jobs: bool
    ignore_failed: bool

    def __init__(
        self,
        complete: bool,
        failed_jobs: bool,
        ignore_failed: bool,
        repeats: int,
        baseline: BuildResults,
        tested: BuildResults,
    ):
        self.baseline = baseline.succeeded
        self.tested = tested.succeeded
        self.repeats = repeats
        self.complete = complete
        self.failed_jobs = failed_jobs
        self.ignore_failed = ignore_failed
        self.shared_steps = []

        if not self.complete:
            return
        if self.failed_jobs and not self.ignore_failed:
            return

        # Process steps of the builds.
        baseline_steps = self.baseline[0].GetStepsNames()
        for baseline_test in self.baseline:
            # Confirm that all baseline builds have the same steps.
            if baseline_test.GetStepsNames() != baseline_steps:
                logging.warning(
                    "Baseline builds have different steps:\n"
                    " Task %s (this set of steps will be used for comparison): "
                    "%s\n"
                    " Task %s: %s",
                    self.baseline[0].task_id,
                    baseline_steps,
                    baseline_test.task_id,
                    baseline_test.GetStepsNames(),
                )

        tested_steps = self.tested[0].GetStepsNames()
        for tested_test in self.tested:
            # Confirm that all tested builds have the same steps.
            if tested_test.GetStepsNames() != tested_steps:
                logging.warning(
                    "Tested builds have different steps:\n"
                    " Task %s (this set of steps will be used for comparison): "
                    "%s\n"
                    " Task %s: %s",
                    self.tested[0].task_id,
                    tested_steps,
                    tested_test.task_id,
                    tested_test.GetStepsNames(),
                )

        # Find and print all steps that are only in baseline or tested builds.
        diff_steps = tested_steps.symmetric_difference(baseline_steps)
        logging.warning("Tested and baseline builds have different steps:")
        for diff_step in diff_steps:
            if diff_step in baseline_steps and diff_step not in tested_steps:
                logging.warning(
                    ' Step "%s" is in baseline builds only.', diff_step
                )
            elif diff_step not in baseline_steps and diff_step in tested_steps:
                logging.warning(
                    ' Step "%s" is in tested builds only.', diff_step
                )
            else:
                raise Exception("presumably impossible state")

        # Find steps that are present in both baseline and tested builds.
        self.shared_steps = tested_steps.intersection(baseline_steps)
        logging.debug(
            "Steps that are shared:\n %s", "\n ".join(self.shared_steps)
        )

    def PrintIndividualBuildsStepsTable(
        self, csv: bool = False, min_seconds: int = 10
    ) -> None:
        """Final processing of performance and print individual step table."""
        if csv:
            separator = ","
        else:
            separator = "|"
        baseline_builds_amount = len(self.baseline)
        baseline_builds_ids = [t.task_id for t in self.baseline]
        tested_builds_amount = len(self.tested)
        tested_builds_ids = [t.task_id for t in self.tested]
        first_line_format_str = (
            "{:^30.30s}"
            + separator
            + separator.join(
                ["{:^16.16s}"] * (baseline_builds_amount + tested_builds_amount)
            )
        )
        first_line = first_line_format_str.format(
            "Step", *baseline_builds_ids, *tested_builds_ids
        )
        logging.notice("Printing results from individual tests (in seconds)")
        print(first_line)

        # Print line of baseline vs test types to help user distinguish.
        if not csv:
            run_types = ["(baseline)"] * self.repeats
            run_types += ["(test)"] * self.repeats
            print(first_line_format_str.format("", *run_types))
            # Vertical separator for readability.
            print("—" * len(first_line))

        result_line_format_str = (
            "{:^30.30s}"
            + separator
            + separator.join(
                ["{:^16.2f}"] * (baseline_builds_amount + tested_builds_amount)
            )
        )
        # Print individual steps results.
        for step in self.shared_steps:
            baseline_builds_times = [t.steps[step] for t in self.baseline]
            tested_builds_times = [t.steps[step] for t in self.tested]
            if all(
                time < min_seconds for time in baseline_builds_times
            ) and all(time < min_seconds for time in tested_builds_times):
                continue
            print(
                result_line_format_str.format(
                    step, *baseline_builds_times, *tested_builds_times
                )
            )
        # Print overall time results.
        total_baseline_builds_times = [t.total_runtime for t in self.baseline]
        total_tested_builds_times = [t.total_runtime for t in self.tested]
        print(
            result_line_format_str.format(
                "TOTAL",
                *total_baseline_builds_times,
                *total_tested_builds_times,
            )
        )
        if not csv:
            print("—" * len(first_line))

    def PrintAverageBuildsStepsTable(
        self, csv: bool = False, min_seconds: int = 10
    ) -> None:
        """Final processing of performance and print median result table."""
        if csv:
            separator = ","
        else:
            separator = "|"

        first_line_format_str = (
            "{:^30.30s}" + separator + separator.join(["{:^17.17s}"] * 5)
        )
        first_line = first_line_format_str.format(
            "Step",
            "Average Baseline",
            "Stdev Baseline",
            "Average Tested",
            "Stdev Tested",
            "Difference",
        )
        logging.notice("Printing average results (in seconds)")
        print(first_line)
        if not csv:
            print("—" * len(first_line))

        result_line_format_str = (
            "{:^30.30s}"
            + separator
            + separator.join(["{:^17.2f}"] * 4)
            + separator
            + "{:^17.17s}"
        )
        for step in self.shared_steps:
            baseline_average_time = statistics.mean(
                t.steps[step] for t in self.baseline
            )
            tested_average_time = statistics.mean(
                t.steps[step] for t in self.tested
            )
            baseline_stdev_time = statistics.pstdev(
                t.steps[step] for t in self.baseline
            )
            tested_stdev_time = statistics.pstdev(
                t.steps[step] for t in self.tested
            )
            if (
                baseline_average_time < min_seconds
                and tested_average_time < min_seconds
            ):
                continue
            print(
                result_line_format_str.format(
                    step,
                    baseline_average_time,
                    baseline_stdev_time,
                    tested_average_time,
                    tested_stdev_time,
                    str(
                        round(
                            tested_average_time * 100 / baseline_average_time, 2
                        )
                    )
                    + "%",
                )
            )
        # Print average time results.
        total_baseline_average_time = statistics.mean(
            t.total_runtime for t in self.baseline
        )
        total_tested_average_time = statistics.mean(
            t.total_runtime for t in self.tested
        )
        total_baseline_stdev_time = statistics.pstdev(
            t.total_runtime for t in self.baseline
        )
        total_tested_stdev_time = statistics.pstdev(
            t.total_runtime for t in self.tested
        )
        print(
            result_line_format_str.format(
                "TOTAL",
                total_baseline_average_time,
                total_baseline_stdev_time,
                total_tested_average_time,
                total_tested_stdev_time,
                str(
                    round(
                        total_tested_average_time
                        * 100
                        / total_baseline_average_time,
                        2,
                    )
                )
                + "%",
            )
        )
        if not csv:
            print("—" * len(first_line))

    def PrintMedianBuildsStepsTable(
        self, csv: bool = False, min_seconds: int = 10
    ) -> None:
        """Final processing of performance and print median result table."""
        if csv:
            separator = ","
        else:
            separator = "|"

        first_line_format_str = (
            "{:^30.30s}" + separator + separator.join(["{:^17.17s}"] * 3)
        )
        first_line = first_line_format_str.format(
            "Step", "Median Baseline", "Median Tested", "Difference"
        )
        logging.notice("Printing median results (in seconds)")
        print(first_line)
        if not csv:
            print("—" * len(first_line))

        result_line_format_str = (
            "{:^30.30s}"
            + separator
            + separator.join(["{:^17.2f}"] * 2)
            + separator
            + "{:^17.17s}"
        )
        for step in self.shared_steps:
            baseline_median_time = statistics.median(
                t.steps[step] for t in self.baseline
            )
            tested_median_time = statistics.median(
                t.steps[step] for t in self.tested
            )
            if (
                baseline_median_time < min_seconds
                and tested_median_time < min_seconds
            ):
                continue
            print(
                result_line_format_str.format(
                    step,
                    baseline_median_time,
                    tested_median_time,
                    str(
                        round(
                            tested_median_time * 100 / baseline_median_time, 2
                        )
                    )
                    + "%",
                )
            )
        # Print median time results.
        total_baseline_median_time = statistics.median(
            t.total_runtime for t in self.baseline
        )
        total_tested_median_time = statistics.median(
            t.total_runtime for t in self.tested
        )
        print(
            result_line_format_str.format(
                "TOTAL",
                total_baseline_median_time,
                total_tested_median_time,
                str(
                    round(
                        total_tested_median_time
                        * 100
                        / total_baseline_median_time,
                        2,
                    )
                )
                + "%",
            )
        )
        if not csv:
            print("—" * len(first_line))


class Test:
    """Test launches led jobs and extracts results from swarming."""

    def __init__(
        self,
        test_name: str,
        tested_job: str,
        baseline_job: str,
        repeats: int,
        tested_jobs=None,
        baseline_jobs=None,
    ):
        self._properties = {
            "test_name": test_name,
            "tested_job": json.loads(tested_job),
            "baseline_job": json.loads(baseline_job),
            "repeats": repeats,
        }

        self.tested_jobs = tested_jobs
        if self.tested_jobs is None:
            self.tested_jobs = []
        self.baseline_jobs = baseline_jobs
        if self.baseline_jobs is None:
            self.baseline_jobs = []

        self.test_state_dir = _TESTS_FOLDER / test_name

    @classmethod
    def FromTestName(cls, test_name: os.PathLike):
        """Initializes class state from data files stored on disk."""
        test_state_dir = _TESTS_FOLDER / test_name
        properties = json.loads(
            (test_state_dir / _FILENAME_TEST_PROPERTIES).read_bytes()
        )

        tested_jobs = json.loads(
            (test_state_dir / _FILENAME_TESTED_JOBS).read_bytes()
        )

        baseline_jobs = json.loads(
            (test_state_dir / _FILENAME_BASELINE_JOBS).read_bytes()
        )

        return cls(
            properties["test_name"],
            pformat.json(properties["tested_job"]),
            pformat.json(properties["baseline_job"]),
            properties["repeats"],
            tested_jobs,
            baseline_jobs,
        )

    @property
    def test_name(self) -> str:
        return self._properties["test_name"]

    @property
    def tested_job(self) -> str:
        return self._properties["tested_job"]

    @property
    def baseline_job(self) -> str:
        return self._properties["baseline_job"]

    @property
    def repeats(self) -> str:
        return self._properties["repeats"]

    def LedLaunchAllJobs(self) -> None:
        """Launches all requested jobs using `led`."""
        for _ in range(self.repeats):
            tested_job_output = self._LaunchLedJob(self.tested_job)
            tested_job_json = json.loads(tested_job_output)
            logging.debug("Tested job output:")
            logging.debug(pformat.json(tested_job_json))
            self.tested_jobs.append(tested_job_json)

            baseline_job_output = self._LaunchLedJob(self.baseline_job)
            baseline_job_json = json.loads(baseline_job_output)
            logging.debug("Baseline job output:")
            logging.debug(pformat.json(baseline_job_json))
            self.baseline_jobs.append(baseline_job_json)

    @staticmethod
    def _LaunchLedJob(job: dict) -> str:
        """Launches a single |job| using led.

        Returns stdout, which should contain a json like:
        {
          "swarming": {
            "host_name": "chromeos-swarming.appspot.com",
            "task_id": "5afd1135f2c0d110"
          }
        }
        """
        try:
            result = cros_build_lib.run(
                [get_led(), "launch"],
                input=pformat.json(job),
                capture_output=True,
            )
            return result.stdout
        except cros_build_lib.RunCommandError as e:
            cros_build_lib.Die(e)

    def GetSwarmingResults(
        self, ignore_failed: bool
    ) -> SwarmingOutputProcessor:
        """Collects and swarming results(build.proto.json) for each build."""
        complete = True
        failed_jobs = False
        tested_builds = BuildResults(succeeded=[], failed=[])
        baseline_builds = BuildResults(succeeded=[], failed=[])

        for job in self.baseline_jobs:
            host_name = job["swarming"]["host_name"]
            task_id = job["swarming"]["task_id"]
            swarmingUrl = get_swarming_url(task_id, host_name)
            build_proto_json_str = self._SwarmingProcessOne(host_name, task_id)
            if build_proto_json_str is None:
                logging.notice("%s is not finished", swarmingUrl)
                complete = False
            else:
                build_proto_json = json.loads(build_proto_json_str)
                status = build_proto_json.get("status", "UNKNOWN")
                logging.notice("%s is finished: %s", swarmingUrl, status)
                succeeded = True
                if status == "FAILURE":
                    failed_jobs = True
                    succeeded = False
                baseline_builds.append(
                    TestResult(swarmingUrl, task_id, build_proto_json),
                    succeeded=succeeded,
                )

        for job in self.tested_jobs:
            host_name = job["swarming"]["host_name"]
            task_id = job["swarming"]["task_id"]
            swarmingUrl = get_swarming_url(task_id, host_name)
            build_proto_json_str = self._SwarmingProcessOne(host_name, task_id)
            if build_proto_json_str is None:
                logging.notice("%s is not finished", swarmingUrl)
                complete = False
            else:
                build_proto_json = json.loads(build_proto_json_str)
                status = build_proto_json.get("status", "UNKNOWN")
                logging.notice("%s is finished: %s", swarmingUrl, status)
                succeeded = True
                if status == "FAILURE":
                    failed_jobs = True
                    succeeded = False
                tested_builds.append(
                    TestResult(swarmingUrl, task_id, build_proto_json),
                    succeeded=succeeded,
                )

        return SwarmingOutputProcessor(
            complete,
            failed_jobs,
            ignore_failed,
            self.repeats,
            baseline_builds,
            tested_builds,
        )

    def _SwarmingProcessOne(
        self, host_name: str, task_id: str
    ) -> Optional[str]:
        """Returns build.proto.json for a given |host_name| and |task_id|"""

        cmd = [
            get_swarming(),
            "collect",
            "-S",
            host_name,
            "--output-dir",
            self.test_state_dir,
            "-wait=false",
            task_id,
        ]

        try:
            cros_build_lib.run(cmd, capture_output=True)
        except cros_build_lib.RunCommandError as e:
            cros_build_lib.Die(e)

        try:
            build_proto_json_path = (
                self.test_state_dir / task_id / "build.proto.json"
            )
            return build_proto_json_path.read_text(encoding="utf-8").rstrip()
        except FileNotFoundError:
            return None

    def SaveToDisk(self) -> None:
        """Stores Test state to disk.

        Can be read later during processing.
        """
        state_dir = Path(self.test_state_dir)
        state_dir.mkdir(parents=True, exist_ok=True)

        (state_dir / _FILENAME_TEST_PROPERTIES).write_text(
            pformat.json(self._properties), encoding="utf-8"
        )

        (state_dir / _FILENAME_TESTED_JOBS).write_text(
            pformat.json(self.tested_jobs), encoding="utf-8"
        )

        (state_dir / _FILENAME_BASELINE_JOBS).write_text(
            pformat.json(self.baseline_jobs), encoding="utf-8"
        )


def SetupLaunchParser(parser) -> None:
    """Sets cl-perf launch parser."""
    parser.add_argument(
        "--builder",
        default="amd64-generic-cq",
        help="Builder to run jobs on. Default: %(default)s.",
    )
    parser.add_argument(
        "--bucket",
        default="chromeos/cq",
        help="CI bucket to run jobs on. Default: %(default)s.",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="""
      Amount of builds to launch for tested and for baseline CLs.
      Individual results will be reported by `%(prog)s process`,
      along with median run and percentage difference.
      Default: %(default)s.
      """,
    )
    parser.add_argument(
        "--cls-baseline",
        default=None,
        help="""
      Comma-separated list of CL URLs to measure baseline performance.
      Default: %(default)s.
      """,
    )
    parser.add_argument(
        "--cls-tested",
        required=True,
        help="Comma-separated list of CL URLs to test. Required.",
    )
    parser.epilog = """
Usage examples:
  1. Test how https://crrev.com/c/345678 affects runtime vs baseline of default
  bucket/builder with no repeats:
    cl-perf launch --cls-tested https://chromium-review.googlesource.com/c/chromiumos/chromite/+/345678
  2. Test how https://crrev.com/c/345678 affects runtime vs baseline of default
  bucket/builder with 3 builds of these CLs and 3 builds of baseline
  (`cl-perf process` will compute median diff for you later):
    cl-perf launch --cls-tested https://chromium-review.googlesource.com/c/chromiumos/chromite/+/345678 --repeats 3
  3. Test how https://crrev.com/c/345678 affects runtime vs baseline of certain
  builder and bucket:
    cl-perf launch --cls-tested https://chromium-review.googlesource.com/c/chromiumos/chromite/+/345678 --builder arm64-generic-cq --bucket chromeos/cq
  4. Test how https://crrev.com/c/234567 and https://crrev.com/c/345678 together
  affect runtime vs baseline:
    cl-perf launch --cls-tested https://chromium-review.googlesource.com/c/chromiumos/chromite/+/234567/,https://chromium-review.googlesource.com/c/chromiumos/third_party/kernel/+/345678/
  5. Test https://crrev.com/c/234567 vs https://crrev.com/c/345678:
    cl-perf launch --cls-tested https://chromium-review.googlesource.com/c/chromiumos/chromite/+/234567/ --cls-baseline https://chromium-review.googlesource.com/c/chromiumos/third_party/kernel/+/345678/
"""


def SetupProcessParser(parser) -> None:
    """Sets up cl-perf process parser."""
    parser.add_argument(
        "--csv",
        default=False,
        action="store_true",
        help="Report results as CSV, ready for spreadsheet. "
        "Default: %(default)s.",
    )
    parser.add_argument(
        "--min-seconds",
        type=float,
        default=10,
        help="""Ignore steps that take less than this many seconds.
      Default: %(default)s
      """,
    )
    parser.add_argument(
        "--ignore-failed",
        default=False,
        action="store_true",
        help="Ignore failed builds when processing results."
        "Default: %(default)s.",
    )
    parser.add_argument(
        nargs="?",
        dest="test_name",
        default="",
        help="Name of the test to process.",
    )
    parser.epilog = """
`cl-perf process` gathers the timestamps of previously launched tests to process
them and output 2 tables, that show performance difference:
 - Durations of individual builds and their steps for tested CLs vs baseline.
 - Aggregated median durations of builds and steps for tested cls vs baseline.

To print all test_names, previously started by `cl-perf launch`:
  cl-perf process
To check status/process results of a specific test, specify your test_name:
  cl-perf process test_name
"""


def launch_subcommand(options: commandline.ArgumentNamespace) -> None:
    """Launches the requested builds."""
    check_led_auth()

    baseline_cl_name = "baseline"
    if options.cls_baseline is not None:
        baseline_cl_name = "\n * ".join(options.cls_baseline)
    logging.notice(
        """
Launching %s builds of following CLs:
 * %s
 to compare vs:
 * %s

Bucket: %s
Builder: %s
""",
        options.repeats,
        "\n * ".join(options.cls_tested),
        baseline_cl_name,
        options.bucket,
        options.builder,
    )

    builder_job_template = get_base_job_template(
        options.bucket, options.builder, options.debug
    )
    logging.debug("Base job template:")
    logging.debug(pformat.json(json.loads(builder_job_template)))

    tested_job = add_cls_to_job(
        builder_job_template, options.cls_tested, options.debug
    )
    tested_job = pformat.json(json.loads(tested_job))

    if options.cls_baseline:
        baseline_job = add_cls_to_job(
            builder_job_template, options.cls_baseline, options.debug
        )
        baseline_job = pformat.json(json.loads(baseline_job))
    else:
        # Baseline job does not need any CLs added, but we need to set
        # force_relevant_build=True to prevent pointless build check from
        # stopping the build early.
        baseline_job_json = json.loads(builder_job_template)
        baseline_job_json["buildbucket"]["bbagent_args"]["build"]["input"][
            "properties"
        ]["force_relevant_build"] = True
        baseline_job = pformat.json(baseline_job_json)

    logging.debug("Tested job:")
    logging.debug(tested_job)
    logging.debug("Baseline job:")
    logging.debug(baseline_job)

    test_name = get_unique_test_name(
        options.bucket,
        options.builder,
        options.cls_tested,
        options.cls_baseline,
    )

    t = Test(test_name, tested_job, baseline_job, options.repeats)
    t.LedLaunchAllJobs()
    t.SaveToDisk()

    logging.notice(
        "To check status or process results, run:\n  cl-perf process %s",
        test_name,
    )


def process_subcommand(options: commandline.ArgumentNamespace) -> None:
    """Processes previously launched builds."""
    check_swarming_auth()

    if not options.test_name:
        logging.notice(
            "Provide one of the test names to `cl-perf process`\n %s",
            "\n ".join(get_dirs_in_dir(_TESTS_FOLDER)),
        )
    else:
        t = Test.FromTestName(options.test_name)
        logging.debug(
            "Tested jobs:\n%s",
            "\n".join(
                [pformat.json(tested_job) for tested_job in t.tested_jobs]
            ),
        )
        logging.debug(
            "Baseline jobs:\n%s",
            "\n".join(
                [pformat.json(baseline_job) for baseline_job in t.baseline_jobs]
            ),
        )
        swarming_results = t.GetSwarmingResults(options.ignore_failed)
        if swarming_results.failed_jobs and not options.ignore_failed:
            cros_build_lib.Die(
                "Some tests have failed, skipping processing. "
                "Use --ignore-failed to process the results anyway."
            )
        if not swarming_results.complete:
            cros_build_lib.Die("Test is not finished, skipping processing.")

        swarming_results.PrintIndividualBuildsStepsTable(
            options.csv, options.min_seconds
        )
        if t.repeats > 2:
            swarming_results.PrintMedianBuildsStepsTable(
                options.csv, options.min_seconds
            )
            swarming_results.PrintAverageBuildsStepsTable(
                options.csv, options.min_seconds
            )
        if not options.csv:
            logging.notice(
                "To get comma-separated values for a spreadsheet"
                " (check go/cl-perf-template), rerun the script with --csv"
            )
        if options.min_seconds > 0:
            logging.notice(
                "Steps that take less than %s seconds were ignored."
                " You can change this with --min-seconds parameter.",
                options.min_seconds,
            )


def get_parser() -> commandline.ArgumentParser:
    """Build the parser for command line arguments."""
    parser = commandline.ArgumentParser(
        description=__doc__, default_log_level="notice"
    )
    subparsers = parser.add_subparsers(dest="subcommand")
    subparsers.required = True

    launch_parser = subparsers.add_parser("launch")
    SetupLaunchParser(launch_parser)

    process_parser = subparsers.add_parser("process")
    SetupProcessParser(process_parser)
    return parser


def main(argv: Optional[List[str]] = None) -> Optional[int]:
    parser = get_parser()
    options = parser.parse_args(argv)

    if options.subcommand == "launch":
        options.cls_tested = options.cls_tested.split(",")
        if options.cls_baseline is not None:
            options.cls_baseline = options.cls_baseline.split(",")
        options.Freeze()
        launch_subcommand(options)
    elif options.subcommand == "process":
        options.Freeze()
        process_subcommand(options)
    else:
        assert options.subcommand in (
            "launch",
            "process",
        ), "parser.parse_args(argv) should have exited on wrong subcommand"
