# Build API Proto Reference

This doc answers questions you may have about the Build API proto.
It does not cover the proto for specific endpoints, just more general topics,
and the overall structure.

## Service and Method Options

The service and method options extensions in
[`chromite/api/build_api.proto`](https://chromium.googlesource.com/chromiumos/infra/proto/+/refs/heads/main/src/chromite/api/build_api.proto)
define some key information about the implementation of the endpoint.

### Implementation Routing

The service option `module` is required for all services.
This option defines the python module in `chromite/api/controller` where
all the service's methods are implemented.
Generally, the protos contain a single service, and that service will map to a
controller module of the same name, but that is not required, and this option is
how that is managed.

The methods are each implemented as a function in the service's controller
module.
By default, the method's name is used to determine what function to call.
This default behavior can be optionally overridden by setting the method's
`implementation_name` option to the name of the function.

### Chroot Assertions

The `service_chroot_assert` and `method_chroot_assert` options define where the
endpoint should run.
The `service_chroot_assert` option defines the default for all methods in the
service, and the `method_chroot_assert` option allows overriding the service
default for the method.

When left undefined, the endpoint will be allowed to run inside or outside the
SDK, but in practice means the builders will always run it outside.
`OUTSIDE` will cause the Build API to raise an error if it is being run inside
the SDK.
`INSIDE` will cause the Build API to automatically re-execute the endpoint
inside the SDK when it is outside.
There are some built-in utilities that help make working inside the chroot as
easy as possible, see the [chroot reference](./chroot.md) for more information.

### List Visibility

The `service_visibility` and `method_visibility` options allow showing (default)
or hiding whole services and specific methods in the `MethodService/Get` list.
This is intended for cases like hiding an endpoint that's being actively
developed.


## Proto Structure

For the most part, the proto lives in the
[infra/proto repo](https://chromium.googlesource.com/chromiumos/infra/proto/).
The [Build API README](../README.md) has some information about specific
directories used by the Build API.

### infra/proto vs chromite/infra/proto

The `infra/proto` repo itself appears twice in the chromiumos checkout;
`infra/proto/` and `chromite/infra/proto`.
The `infra/proto` checkout is always at ToT.
The `chromite/infra/proto` checkout is branched along with chromite.

These two checkouts reflect the two versions of proto that would be used for the
checkout.
The CI recipes code will always be using ToT, while chromite has to use branched
proto to ensure the implementation and proto match.
Chromite also currently commits its compiled proto to ensure it has a version of
the proto that works with its vendored protobuf library, so while it doesn't
need the branched `chromite/infra/proto` to compile its proto, the checkout
ensures we have a human readable version of the proto being used by chromite in
the repository.
