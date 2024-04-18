# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The build API Metrics Emit entry point."""

from chromite.lib import commandline
from chromite.lib import metrics_lib


def main(argv):
    """Emit a metric event."""
    parser = commandline.ArgumentParser(description=__doc__)
    parser.add_argument(
        "op",
        choices=sorted(metrics_lib.VALID_OPS),
        help="Which metric event operator to emit.",
    )
    parser.add_argument(
        "name",
        help="The name of the metric event as you would like it "
        "to appear downstream in data stores.",
    )
    parser.add_argument(
        "arg", nargs="?", help='An accessory argument dependent upon the "op".'
    )
    opts = parser.parse_args(argv)

    if opts.arg and not metrics_lib.OP_EXPECTS_ARG[opts.op]:
        # We do not expect to get an |arg| for this |op|.
        parser.error(
            'Unexpected arg "%s" given for op "%s"' % (opts.arg, opts.op)
        )

    timestamp = metrics_lib.current_milli_time()
    metrics_lib.append_metrics_log(timestamp, opts.name, opts.op, arg=opts.arg)
