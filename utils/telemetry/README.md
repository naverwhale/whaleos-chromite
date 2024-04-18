# Chromite Telemetry Collection

This folder contains shared utilities for initializing telemetry collection in
Chromite code paths, as well as telemetry configuration settings.

## Which chromite apps collect trace data?

The Build team is actively working on instrumenting frequently used code paths
in Chromite. Currently supported code paths include:

- chromite/bin/build_packages
- chromite/cli/cros/cros_build_packages
- emerge-$board
- cros_run_unit_test
- chromite/scripts/cros_workon_make

We intend to expand to the following code paths in 2023:

- `cros` CLI commands
- `chromite/bin/build_image`

If there is an application you want to instrument, you are empowered to do so!

## Can I opt out of trace collection?

Yes! To opt out, or opt in, you can run:

```shell
$ cros telemetry --disable
$ cros telemetry --enable
```

## How do I instrument a chromite application?

In the script you wish to instrument, you will want to add the following lines
of code:

```python
from chromite.utils import telemetry

tracer = telemetry.get_tracer(__name__)

def main(argv: Optional[List[str]] = None) -> Optional[int]:
    commandline.RunInsideChroot()
    parser, opts = parse_args(argv)

    telemetry.initialize()
```

From here, you can trace individual code blocks and method calls as you see fit
under `service/`, `lib/`, or any other relevant chromite code path. Each
instrumented file will need a reference to a `Tracer` object.

```python
from chromite.utils import telemetry

tracer = telemetry.get_tracer(__name__)

@tracer.start_as_current_span("chromite.lib.my_important_method")
def my_important_method():
    do_cool_thing()
```

or

```python
from chromite.utils import telemetry

tracer = telemetry.get_tracer(__name__)

def my_important_method():
    with tracer.start_as_current_span("my_important_method.do_thing") as span:
        do_cool_thing()
        span.add_event("cool thing has been done!")
```

For specific advice about instrumenting code, you can contact
chromeos-build-discuss@.

[OpenTelemetry documentation](https://opentelemetry-python.readthedocs.io/en/latest/)
is also a worthy read.

## How do I view/query telemetry data?

If you are a Googler and have a reasonable need to access the telemetry dataset,
contact chromeos-build-discuss@ to be added to the relevant MDB group.
