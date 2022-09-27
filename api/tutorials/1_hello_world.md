# Build API Endpoint Tutorial

This README is a tutorial to create a "Hello world!" endpoint from scratch.
If that's not what you're looking for, try the base [README.md](../README.md)
for additional documentation.
This tutorial assumes you have a basic understanding of protobuf.

## Hello World Endpoint Problem Statement

We have the following function in chromite that we want to be able to call
through the API.

`chromite/lib/hello_lib.py`:
````python
def hello():
    print('Hello, World!')
````

### Step 1: Define the endpoint.

First we must define the endpoint itself in protobuf.
The endpoints are each defined as `rpc`s in a `service`.
Each `rpc` must have a request argument message, and a response message it
returns.
The base `service` and `rpc` definitions need names, and in keeping with our
hello names so far, we'll name them `HelloService` and `Hello` respectively.
We have no arguments that need to be passed in, and nothing that needs to be
returned, so we can just have empty messages for each.
Our conventions dictate the names for the request and response messages are
`<rpc-name>Request` and `<rpc-name>Response`, so `HelloRequest` and
`HelloResponse`.

The Build API proto lives in `chromite/infra/proto/src/chromite/api`,
so we'll create `hello.proto` there.
In addition to our messages, we need to add in some boilerplate proto config.

`chromite/infra/proto/src/chromite/api/hello.proto`:
```protobuf
// Proto config.
syntax = "proto3";
package chromite.api;

option go_package = "go.chromium.org/chromiumos/infra/proto/go/chromite/api";

// HelloService/Hello request and response messages.
message HelloRequest {
}

message HelloResponse {
}

service HelloService {
  rpc Hello(HelloRequest) returns (HelloResponse);
}
```

Note: We use proto to define the services and rpcs, but the Build API is CLI
only, gRPC is not used.
We use proto for its ability to define an interface outside of the
implementation language, and its backwards compatibility features.


### Step 2: Create the endpoint.

The Build API endpoints are functions in controller modules in
`chromite/api/controller`.
Let's create a new controller for our new service, `hello.py`, and setup the
endpoint function, and call through to our `hello_lib.hello` function.

`chromite/api/controller/hello.py`:
```python
from chromite.lib import hello_lib

def Hello(input_proto, output_proto, config_proto):
    hello_lib.hello()
```

The input_proto, output_proto, and config_proto arguments are the same arguments
passed to every endpoint function.
As the names suggest, input_proto would be an instance of our `HelloRequest`
message, and output_proto an instance of `HelloResponse`.
The config_proto argument is a special config that's used to execute some
enhanced functionality that we will not cover here.

Now we have our endpoint defined in the proto, the endpoint itself is in place,
but we're not quite ready yet.

### Step 3: Proto service configuration.

We have the foundations, but our existing `hello.proto` is not sufficient for
a Build API endpoint.
Now that we have the controller in place, we need to add configurations to the
proto so the Build API knows to associate the two.
The Build API defines service and method options that tell it how to call
the endpoints.

To add this functionality, we need to import the build_api.proto that defines
the service and method options, then add the required configurations.
The full, new contents of our `hello.proto` shown below, with comments on the
additions.

`chromite/infra/proto/src/chromite/api/hello.proto`:
```protobuf
// Proto config.
syntax = "proto3";
package chromite.api;

option go_package = "go.chromium.org/chromiumos/infra/proto/go/chromite/api";

// NEW: Import build_api.proto.
import "chromite/api/build_api.proto";

// HelloService/Hello request and response messages.
message HelloRequest {
}

message HelloResponse {
}

service HelloService {
  // NEW: Define the service options.
  option (service_options) = {
    module: "hello",
  };

  rpc Hello(HelloRequest) returns (HelloResponse);
}
```

The `module` field is used to tell the Build API which controller module
implements the endpoints in that service.
We called our controller `hello.py`, so we just give it "hello".
The build_api.proto also defines a method_options that we can use to tell
the Build API which function in the module the `rpc` maps to, but by default
it will try the `rpc` name, which is what we used, so we don't need to set it.


### Step 4: Generate proto bindings.

The Build API and our proto definitions are now all correct, but the protobuf
bindings are not generated automatically.

The `generate.sh` script handles the proto generation for the infra/proto repo,
and the `compile_build_api_proto` script handles the proto generation for the
Build API.

Note: `infra/proto` is a completely different repo than chromite, which is why
this has to be done twice.
The details about the repos are beyond the scope of this tutorial.

```shell script
$> cd ~/chromiumos/chromite/infra/proto
$> ./generate.sh
$> cd ~/chromiumos/chromite/api
$> ./compile_build_api_proto
```

### Step 5: Register the service.

New services are not automatically registered, but registering a new service is
a simple two line addition to the Build API router.

#### Import the module.
In `chromite/api/router.py`, there is a large block of imports from
`chromite.api.gen.chromite.api`.
`chromite.api.gen` is the folder containing the generated proto bindings from
the previous step.
We need to add an import for our new proto file, which will have the name
`hello_pb2`.

```python
...
from chromite.api.gen.chromite.api import hello_pb2
...
```

The router module also has a function called `RegisterServices`.
This function is where the services are all registered to the router for a
standard Build API call.
Registering our service is just a matter of adding a new line to the function.

```python
router.Register(hello_pb2)
```

### Step 6: Calling the endpoint.

The Build API endpoints are not made to be called by humans, so testing them
manually is difficult.
To compensate, we have tooling that makes it much simpler, the
`gen_call_scripts` workflow.
The `gen_call_scripts` script itself generates a simple script and input files
for every endpoint defined in the API.
There are a few arguments to access more advanced features of this script that
are outside of the scope of this tutorial.
The scripts are a good way to see how the Build API is actually called, though,
if you are curious.


```shell script
$> cd ~/chromiumos/chromite/api/contrib/
$> ./gen_call_scripts
$> cd call_scripts/
$> ./hello__hello
```

Among other logging, you should see the "Hello, World!" output.

```text
Running chromite.api.HelloService/Hello
14:37:49: DEBUG: Services registered successfully.
Hello, World!
Completed chromite.api.HelloService/Hello
Success!
Return Code: 0
Result:
{}
```

Success!

## Up Next

Continue to [Part 2](2_hello_target.md), where we'll build on the work we've
done here to parameterize the endpoint.
