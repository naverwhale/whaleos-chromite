# Build API Endpoint Tutorial Part 5

This README is a continuation of
[Hello World Tutorial Part 4](4_hello_faux.md),
creating a "Hello world!" endpoint from scratch.
This tutorial assumes you have already executed all the steps in Parts 1-4,
and have all the code in place.

## Hello World Part 5: Working in the SDK

In this tutorial, we'll be looking at how to implement API endpoints that
execute inside the SDK (a.k.a. the chroot), and the utilities the Build API
provides to do so.

### When and where?

If your endpoint depends on executing code inside the SDK, then you will need
this functionality.
Generally, we expect most endpoints to run inside the chroot, since the
build itself should be taking place in the chroot.
Existing endpoints in this category include things like building/installing
packages (`SysrootService/InstallPackages`, a.k.a. `build_packages`), and
running the ebuild tests (`TestService/BuildTargetUnitTest`, a.k.a.
`cros_run_unit_tests`).

If the functionality you're adding an endpoint for can be entirely executed
from outside the chroot, then you won't need this functionality.
These types of endpoints are most often setup or teardown operations, since
the build itself should be inside the SDK.
Existing endpoints in this category include scripts that actually execute
outside of the chroot, such as making the chroot itself (`SdkService/Create`,
a.k.a. `cros_sdk`), operations we run as soon as possible to reduce time spent
on irrelevant builds (e.g. `PackagesService/Uprev`), and cleanup steps (e.g.
`SdkService/Clean`).

If you're ever unsure where yours should run, we're happy to help!

### Part 1: Getting Inside

The first step is just getting inside.
In [Part 1](1_hello_world.md) we talked about the service and method options
for configuring the endpoints modules and functions that get executed when
calling the endpoints.
These options also contain fields for configuring whether the endpoint gets
run inside or outside of the chroot.
The `service_options` has the `service_chroot_assert` field, and the
`method_options` the `method_chroot_assert` field.
These fields are enums that direct the API how to execute the endpoint.
The functionality requires no additional imports, the fields just need to be
added and set.

The service option allows setting the default for all endpoints in the service,
but when both are set, the method option will take precedence over the service
option.
A value MUST be set if the endpoint does not execute properly both inside and
outside of the SDK.
If the endpoint is capable of executing in either environment, then the field
does not need to be set.

The other important note is that the API needs to know which chroot to enter.
Every endpoint that enters or uses the chroot MUST include a Chroot message
field in the request.
See the updates below for the new import and an example of the new field in the
request.
However, when you're running the endpoints locally, it will mostly likely work
without populating the chroot field.
When not populated, the Build API will use the default chroot location.
If you're a person for whom the default will not work locally, you probably
already know because you had to manually set it up that way.
If you care to check it out, the Chroot message definition is in
`chromite/infra/proto/src/chromiumos/common.proto`.

With all that in mind, let's update our endpoint to execute inside the SDK.

`chromite/infra/proto/src/chromite/api/hello.proto`:
```protobuf
// Proto config.
syntax = "proto3";
package chromite.api;

option go_package = "go.chromium.org/chromiumos/infra/proto/go/chromite/api";

import "chromite/api/build_api.proto";
// NEW!
import "chromiumos/common.proto";

// HelloService/Hello request and response messages.
message HelloRequest {
  string target = 1;
  // NEW!
  chromiumos.Chroot chroot = 2;
}

message HelloResponse {
  string hello_message = 1;
}

service HelloService {
  option (service_options) = {
    module: "hello",
    // NEW!
    service_chroot_assert: INSIDE,
  };

  rpc Hello(HelloRequest) returns (HelloResponse);
}
```

And now let's regenerate the protobuf bindings.

```shell script
$> cd ~/chromiumos/chromite/infra/proto
$> ./generate.sh
$> cd ~/chromiumos/chromite/api
$> ./compile_build_api_proto
```

That's it!
Our endpoint will now always execute inside the chroot.


### Part 2: Injecting and Extracting Files and Folders

Let's change our endpoint again.
Instead of passing the target as a string, let's pass a file that contains
multiple targets, one per line.
In addition to printing out the messages, let's also write them out, one message
per file, each named after their target.

The Build API has specific messages that are used to support injecting and
extracting files and folders from the SDK.
We'll use some of these here to implement our new functionality.

#### Proto Changes

`chromite/infra/proto/src/chromite/api/hello.proto`:
```protobuf
// Proto config.
syntax = "proto3";
package chromite.api;

option go_package = "go.chromium.org/chromiumos/infra/proto/go/chromite/api";

import "chromite/api/build_api.proto";
import "chromiumos/common.proto";

// HelloService/Hello request and response messages.
message HelloRequest {
  // NEW!
  reserved "target";
  // NEW!
  reserved 1;
  chromiumos.Chroot chroot = 2;
  // NEW!
  chromiumos.Path targets_file = 3;
  // NEW!
  chromiumos.ResultPath output_dir = 4;
}

message HelloResponse {
  // NEW!
  reserved "messages";
  // NEW!
  reserved 1;
  // NEW!
  repeated chromiumos.Path message_files = 2;
}

service HelloService {
  option (service_options) = {
    module: "hello",
    service_chroot_assert: INSIDE,
  };

  rpc Hello(HelloRequest) returns (HelloResponse);
}
```

First thing to note is we deprecated the target and message fields from the
request and response, respectively, by reserving the field name and number.
In the request, we also added `chromiumos.Path` and `chromiumos.ResultPath`
fields, and in the response, a repeated `chromiumos.Path` field.

The `Path` message family are used by the Build API to automatically inject
artifacts (i.e. files and folders) into and extract artifacts from the SDK.
The functionality can handle both files and folders in both directions.
There is also a bidirectional sync with the `SyncedDir`.
For more details, see the [chroot reference](../references/chroot.md).

We will be using the `targets_file` field in the request to inject a file
containing targets, replacing the target field we previously had.
The endpoint will then print the messages as it did before, but also write
each message to a separate file, and return those paths in the `message_files`
field, each named for their target.
Those files will all be collected in the path we specify in the `output_dir`
field.


#### Code Changes

With our proto updated, let's change our lib to write out the message to a
file and return the file path rather than the message itself.

`chromite/lib/hello_lib.py`
```python
import os

from chromite.lib import osutils

def hello(target, output_dir):
  msg = f'Hello, {target}!'
  print(msg)
  file_path = os.path.join(output_dir, target)
  osutils.WriteFile(file_path, msg)
  return file_path
```

Finally, let's update the controller to use the new fields in the request,
and fix the hello_lib call now that it has a new signature.

```python
from chromite.api import faux
from chromite.api import validate
from chromite.api.gen.chromiumos import common_pb2
from chromite.lib import hello_lib
from chromite.lib import osutils

def _hello_success(_input_proto, output_proto, _config_proto):
  file_proto = output_proto.message_files.add()
  file_proto.path = '/tmp/target'
  file_proto.location = common_pb2.Path.OUTSIDE

@faux.success(_hello_success)
@faux.empty_error
@validate.exists('targets_file.path')
@validate.validation_complete
def Hello(input_proto, output_proto, _config_proto):
  # Read targets, one per line.
  targets = osutils.ReadFile(input_proto.targets_file.path).splitlines()
  # Don't delete since we need it to exist afterwords.
  with osutils.TempDir(delete=False) as tmp_dir:
    for target in targets:
      # Print the greeting and get the file it created.
      target_file = hello_lib.hello(target=target, output_dir=tmp_dir)
      # Add it to the response.
      file_proto = output_proto.message_files.add()
      file_proto.path = target_file
      file_proto.location = common_pb2.Path.INSIDE
```

First, we changed the `@validate` decorator to `exists`, which verifies a file
exists.
We then read the targets files, and call the hello_lib for each target, adding
the results to the response as we go.
Finally, the faux success function needs to reflect our new response.


### Part 3: Running it

First, we'll regenerate the compiled proto to pick up our changes.

```shell script
$> cd ~/chromiumos/chromite/infra/proto
$> ./generate.sh
$> cd ~/chromiumos/chromite/api
$> ./compile_build_api_proto
```

Next we need to create the targets file for the request, and our output
directory.

```shell script
$> printf "world\nmoon\neverybody" > /tmp/targets-file
$> mkdir /tmp/hello-results
```

Now we can set up our new input file, pointing to those locations.
The 2 used for the location fields in our input file below is just the enum
value for `Path.Location.OUTSIDE`.

`~/chromiumos/chromite/api/contrib/call_scripts/hello__hello_input.json`
```json
{
  "targets_file": {"path": "/tmp/targets-file", "location": 2},
  "output_dir": {"path": {"path": "/tmp/hello-results", "location": 2}}
}
```

We're all set, now we just run it.

```shell script
$> cd ~/chromiumos/chromite/api/contrib/call_scripts/
$> ./hello__hello
Running chromite.api.HelloService/Hello
15:17:13: DEBUG: Services registered successfully.
15:17:13: INFO: Re-executing the endpoint inside the chroot.
15:17:13: DEBUG: Copying /tmp/targets-file to /usr/local/google/home/saklein/chromiumos/chroot/tmp/tmptdazkiqh/targets-file
15:17:13: INFO: Writing input message to: /usr/local/google/home/saklein/chromiumos/chroot/tmp/tmpx9cumt3j/input_proto
15:17:13: INFO: Writing config message to: /usr/local/google/home/saklein/chromiumos/chroot/tmp/tmpx9cumt3j/config_proto
15:17:13: INFO: run: cros_sdk --chroot /usr/local/google/home/saklein/chromiumos/chroot -- build_api chromite.api.HelloService/Hello --input-json /tmp/tmpx9cumt3j/input_proto --output-binary /tmp/tmpx9cumt3j/output_proto --config-json /tmp/tmpx9cumt3j/config_proto --debug
15:17:15: DEBUG: Services registered successfully.
15:17:15: DEBUG: Validating targets_file.path exists.
Hello, world!
Hello, moon!
Hello, everybody!
15:17:15: INFO: Endpoint execution completed, return code: 0
15:17:15: DEBUG: Copying /usr/local/google/home/saklein/chromiumos/chroot/tmp/tmpxjuwd_lj/world to /tmp/hello-results/world
15:17:15: DEBUG: Copying /usr/local/google/home/saklein/chromiumos/chroot/tmp/tmpxjuwd_lj/moon to /tmp/hello-results/moon
15:17:15: DEBUG: Copying /usr/local/google/home/saklein/chromiumos/chroot/tmp/tmpxjuwd_lj/everybody to /tmp/hello-results/everybody
Completed chromite.api.HelloService/Hello
Success!
Return Code: 0
Result:
{
  "messageFiles": [
    {
      "location": 2,
      "path": "/tmp/hello-results/world"
    },
    {
      "location": 2,
      "path": "/tmp/hello-results/moon"
    },
    {
      "location": 2,
      "path": "/tmp/hello-results/everybody"
    }
  ]
}
```

We can also check our output files to make sure they also have our messages.

```shell script
$> tail /tmp/hello-results/world /tmp/hello-results/moon /tmp/hello-results/everybody
==> /tmp/hello-results/world <==
Hello, world!
==> /tmp/hello-results/moon <==
Hello, moon!
==> /tmp/hello-results/everybody <==
Hello, everybody!
```

Success!
