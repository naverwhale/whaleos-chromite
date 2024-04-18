#### api/gen_sdk

Generated protobuf messages for use with the protobuf library installed in
the SDK. These bindings are **not** compatible with the protobuf library in
`chromite/third_party`, all code using chromite's vendored protobuf library
should be using `api/gen` instead.

**Do not edit any files in this package directly.**

Edit the protos in `~/chromiumos/chromite/infra/proto/src/chromite/api` and
then regenerate the python files by running the
`~/chromiumos/chromite/api/compile_build_api_proto` script.
