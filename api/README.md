# Build API

Welcome to the Build API.

## Getting Started

### Overview

The Build API is a CLI-only, proto based API to execute build steps. It was
created to provide a stable interface for the CI builders. The proto files (in
[chromite/infra/proto](#chromite/infra/proto/)) define the services/RPCs
provided by the API. The modules in [controller/](./controller/) are the entry
points for the RPCs defined in the proto files.

### Manually Calling/Testing an Endpoint

To manually call an endpoint, the
[gen_call_scripts](./contrib/README.md#gen_call_scripts_call_templates_and-call_scripts)
process is strongly recommended, it makes calling a specific endpoint quick and
easy. Please contribute new example input files when you add new endpoints!

Just in case, the general info for invoking the Build API follows, however, if
you do find a use case that the gen call scripts doesn't cover for local uses,
please file a bug for the CrOS Build team with the info.

The Build API is invoked via the `build_api` script, which takes 4 arguments;
the name of the endpoint being called (e.g. chromite.api.SdkService/Create), and
the request, response, and optional config protos, which are provided as paths
to files containing the respective JSON or protobuf-binary encoded messages.
e.g.
```shell
build_api chromite.api.SdkService/Create \
    --input-json /tmp/input.json \
    --output-json /tmp/output.json \
    --config-json /tmp/config.json
```

### Recreating Build API Calls from Builders

It is relatively simple to duplicate calls made on a builder. This does NOT
handle fetching the same version of the source, prerequisites, placing files in
expected locations, etc. However, if you can satisfy the prerequisites, either
by also calling the prerequisite endpoints, or just manually setting it up, you
can locally duplicate the endpoint invocation.

Each endpoint call will be its own step in the Milo UI for the builder. The
endpoint call steps may be top level steps, or nested arbitrarily. The step text
will be something like `1. call chromite.api.SdkService/Update`. All context for
calling the endpoint is nested under that step. Most importantly, the `request`
is the first link listed before the sub-steps.

1. Follow instructions to set up the
   [gen_call_scripts](./contrib/README.md#gen_call_scripts_call_templates_and-call_scripts)
   workflow for your build target.
2. Find the Build API call you want to duplicate.
3. Open the `request`, copy its contents, and paste it into the relevant
   `service__method_input.json`.
4. Make minor edits.
    1. All endpoints
        1. Drop (or fix) the `chroot`'s `path` field, if present.
            * Drop if using the default location, otherwise fix to your custom
              path.
            * If you're not sure, it's in the default location.
    2. SysrootService/InstallPackages endpoint
        1. Unless you've manually set them up locally, drop the:
            1. `chrome_dir` in the chroot message.
            2. `goma` configs in the chroot message, if present.
5. Ensure prerequisites are satisfied.
    * If in doubt, you can run every endpoint the builder ran up through the
      endpoint you want to run, though this may be time-consuming.
6. Run the `method__service` script.
    * It'll use the input you took from the builder to run the endpoint.

### Tutorials and References

See the [Build API Tutorials](./tutorials/0_introduction.md) for code lab style
instructions on how to make an endpoint.

See the [Build API References](./references) for a quick, detailed reference on
specific topics.

## Directory Reference

### chromite/infra/proto/

**Make sure you've consulted the Build and CI teams when considering making
breaking changes that affect the Build API.**

This directory is a separate repo that contains all the raw .proto files. You
will find message, service, and method definitions, and their configurations.
You will need to commit and upload the proto changes separately from the
chromite changes.

* `chromite/api/` contains the Build API services.
    * Except `chromite/api/build_api.proto`, which contains service and method
      option definitions.
    * And `build_api_test.proto` which is used only for testing the Build API
      itself.
* `chromiumos/` generally contains more shareable proto.
    * `chromiumos/common.proto` contains well shared messages.
    * `chromiumos/metrics.proto` contains message declarations related to build
      api event monitoring.
* `test_platform/` contains the APIs of components of the Test Platform recipe.
    * `test_platform/request.proto` and `test_platform/response.proto` contain
      the API of the overall recipe.
* `device/` contains the proto for hardware related configuration.

When making changes to the proto, you must:

1. Change the proto.
    1. Make your changes.
        * `chromite/infra/proto` or `infra/proto` can be used,
          `chromite/infra/proto` is recommended for simplicity.
        * Your changes will need to be in `chromite/infra/proto` to update the
          chromite bindings after your proto changes are committed.
    2. Run `generate.sh`.
    3. Commit those changes as a single CL.
2. Update the chromite proto.
    * Run `chromite/api/compile_build_api_proto`.
    * When no breaking changes are made (should be most changes)
        1. Create a CL with just the generated proto to submit with the raw
           proto CL.
        2. Submit the proto CLs together.
        3. The implementation may be submitted after the proto CLs.
    * When breaking changes are made (should be very rare)
        1. **Make sure you've consulted the Build and CI teams first.**
        2. Submit the proto changes along with the implementation.
        3. May be done as a single CL or as a stack of CLs with `Cq-Depend`.

Use `Cq-Depend:` to declare the CL dependencies between the infra/proto and
chromite changes.

The chromite/infra/proto repo is branched and reflects the Build API for the
branch in question. The infra/proto repo is unbranched, and is what is used by
recipes.

#### Deprecations

When deprecations are made, be sure to leave a comment that has the ToT
milestone to document when the field can be removed, e.g. `Deprecated in M95`.

### gen/ & gen_sdk/

The generated protobuf messages.

**Do not edit files in these folders directly!**

The proto can be compiled using the `compile_build_api_proto` script
in the api directory. For `gen/`, the protoc version is locked and
fetched from CIPD to ensure compatibility with the client library in
`third_party/`. For `gen_sdk/`, the proto is compiled with the version
of protobuf in the SDK, i.e. the one installed via the protobuf ebuild.

### controller/

This directory contains the entry point for all of the implemented services. The
protobuf service module option (defined in build_api.proto) references the
module in this package. The functions in this package should all operate as one
would expect a controller to operate in an MVC application - translating the
request into the internal representation that's passed along to the relevant
service(s), then translates their output to a specified response format.

### contrib/

This directory contains scripts that may not be 100% supported yet. See
[contrib/README.md](./contrib/README.md) for information about the scripts.
