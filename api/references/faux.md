# Build API Faux/Mock and Validation Call

The faux module (so named to avoid confusion with the python `mock` library)
provides mock call functionality for the Build API.
The mock calls can feel abstract and even pointless when you're implementing
an endpoint, but have important long term implications.
Any given version of the Build API will be living for **years** in branches,
and ideally we'd like to know very quickly and easily if the ToT implementation
of the Build API consumers have functional implementations for whatever version
of the Build API is in the branch they're building.
The Build API's mock calls fill this role by providing static, valid responses
built into and branched with the API, so even as the ToT API and ToT API
consumers change, branches will always have the mock responses for their
version.
See the [Faux Motivation](#faux-motivation) section at the end for an example
of how it can help.


## Overview

The `faux` decorators service one or both of two cases; mock success and
mock error.
There is a third call type, mock validation failure, but it is handled
automatically for every endpoint.
In both the mock success and error cases, the response should be "shaped"
like a real response, but the data is fake, and things like files do not
need to actually exist.
For example, if a response includes a package, `foo/bar-1.0` (which does
not exist at all), `chromeos-base/chromeos-chrome-1.2.3.4` (which is a real
package with a fake version), and
`chromeos-base/chromeos-chrome-80.0.3987.5_rc-r1` (which is a real package
with a real version, but is old and no longer used) are all potential return
values.
The key point is that the responses are hard coded in the controllers so no
expensive operations ever need to be run.
This will allow mock builds to be executed in a matter of seconds and provide
targeted feedback on what implementations problems may exist without spending
hours on each build.

Mock success responses should look like those you would expect from a normal
execution of the endpoint.
Mock error responses those from an execution that encountered a _significant_
error.
Error responses frequently do not contain any data because an exception and
logs are often the primary means of communicating failures, all of which
exists outside of the response itself.
The `sysroot.install_packages` endpoint is an example that does utilize the
error response -- when a package fails to build, the package gets recorded
and included in the response, which the recipes then uses to populate data on
the builder overview page, so you can see what package failed without digging
through the logs.


## Reference

### `@faux.success` & `@faux.error`

The `success` and `error` decorators are the primary tools for populating
responses.
The decorators each take a function that populates the data for its
respective case.
The function needs to take the same arguments as an endpoint, but only ever
need to use the response.

```python
def _mock_endpoint_success(_input_proto, output_proto, _config_proto):
    output_proto.success = 'Success :)'


def _mock_endpoint_failure(_input_proto, output_proto, _config_proto):
    output_proto.failure = 'Error :('


@faux.success(_mock_endpoint_success)
@faux.error(_mock_endpoint_failure)
def endpoint(input_proto, output_proto, _config_proto):
  try:
    do_thing()
    output_proto.success = 'Success :)'
  except Exception as e:
    output_proto.failure = str(e)
```

### `@faux.empty_success` & `@faux.empty_error`

The `empty_success` and `empty_error` decorators provide empty responses
when the endpoint's response contains no success/error data for their
respective cases.
They take no arguments.

```python
def _mock_endpoint_success(_input_proto, output_proto, _config_proto):
    output_proto.success = 'Success :)'


@faux.success(_mock_endpoint_success)
@faux.empty_error
def endpoint(input_proto, output_proto, _config_proto):
  do_thing()
  output_proto.success = 'Success :)'
```

### `@faux.all_empty`

The `all_empty` decorator is a convenience wrapper for using both
`empty_success` and `empty_error`.
This is typical for endpoints that execute functionality that produce no
new artifacts worth reporting, and do not have detailed error reporting
built into the endpoint.

```python
@faux.all_empty
def endpoint(input_proto, output_proto, config_proto):
    do_thing()
```


## Faux Motivation

Branches are the component of the system that makes the faux module important.
We create branches of the code for every release, e.g. R90, R89, etc., as well
as branches for factory, firmware, and a few other things.
These branches need to function until their end of life.
Release branches generally live ~18 weeks (6 weeks each for dev, beta, stable).
More importantly, factory and firmware branches are for the lifetime of their
device.

Builders always run the consumer code (recipes) from ToT, and we continue to
iterate on the Build API itself to make improvements and changes, which then
also means changes in recipes.
When recipes, at ToT, checks out a branch to build, the Build API on that branch
might be identical to ToT, but as they get older, that is less and less likely.
If every change is backwards compatible, we would never have problems, but
that simply isn't realistic in the long term.
The question for ToT recipes then becomes "Can I build this branch?"

The goal of the faux module is to help answer that question.
Of particular value, answering that question *before* breaking changes land.
Without the faux module, the answer the that question is expensive, requiring
a complete build of every branch.
Additionally, the answer generated by a full build might be incorrect if the
branch has a bug or flake that causes builds to fail in a way unrelated to how
the endpoints are called or their responses handled.
The faux module allows answering that question using static responses that
require no computation to execute, so each branch can be checked on the order
of seconds rather than hours, making comprehensive presubmit checks possible.

Note that faux calls only provide static outputs.
Answering the question "Can I build this branch?" also requires validating
the input sent to the API.
That piece is covered by using `--validate-only` calls, which validate the input
and then do not run the rest of the endpoint.
Those calls are handled by the [validate module](./validation.md).
