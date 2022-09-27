# Build API Endpoint Tutorial Part 4

This README is a continuation of
[Hello World Tutorial Part 3](3_hello_validation.md),
creating a "Hello world!" endpoint from scratch.
This tutorial assumes you have already executed all the steps in Parts 1-3,
and have all the code in place.


## Hello World Part 4: Faux Calls

In this tutorial, we'll be adding mock calls in our endpoint using `faux`
decorators.


### Why?

The `faux` module implements the mock call functionality for the Build API.
Our goal is to provide Build API consumers a quick and easy way to validate
their implementations.
By adding simple, static responses that have the correct "shape" (i.e. the data
is all filled in but values like "foo" are fine), Build API consumers can
verify their implementation without running full builds.


### Mock calls

Before we talk about implementing the mock calls, we'll look at how to execute
them.
The config_proto argument to the controllers is what controls the behavior.
In general, endpoints shouldn't need to use it directly, the decorators will
be able to handle any case where it's needed.
We do have to be able to set it to execute the functionality, though.
The `gen_call_scripts` workflow has arguments to set up the configs.

The important ones are `--mock-success`, `--mock-failure`, and
`--validate-only`.
We'll be working with the mock arguments in this tutorial, but if you use the
`--validate-only` argument per the following instructions now and rerun the
endpoint, you will see output identical to our final result in
[Part 3](3_hello_validation.md),
but without the "Hello, moon!" line in the output!

To run one of the special call variants, simply pass the argument to
`gen_call_scripts`.
**You can only have one call variant generated at a time!**
The API can only generate one output at a time, so right now you must choose
which mode you want to apply to all endpoint executions.


### Case 1: Empty responses

Since our current endpoint has no value to return, our work is very easy.

`chromite/api/controller/hello.py`:
```python
from chromite.api import faux
from chromite.api import validate
from chromite.lib import hello_lib

@faux.all_empty
@validate.require('target')
@validate.validation_complete
def Hello(input_proto, output_proto, config_proto):
    hello_lib.hello(target=input_proto.target)
```

The new decorator, `@faux.all_empty`, simply ensures an empty response for both
the success and error mock calls.
Now let's run the mock call and see what we get.

```shell script
$> cd ~/chromiumos/chromite/api/contrib/
$> ./gen_call_scripts --mock-success
$> ./call_scripts/hello__hello
Running chromite.api.HelloService/Hello
13:59:31: DEBUG: Services registered successfully.
Completed chromite.api.HelloService/Hello
Success!
Return Code: 0
Result:
{}
$> ./gen_call_scripts --mock-failure
$> ./call_scripts/hello__hello
Running chromite.api.HelloService/Hello
14:02:56: DEBUG: Services registered successfully.
Completed chromite.api.HelloService/Hello
Return Code: 1
Result:
{}
```

The mock success case looks just like the normal success output, except it is
missing the "Hello, moon!" message we would normally see because we never
actually executed the endpoint itself!
The failure output we haven't seen yet, but the important distinctions to note
are the lack of the "Success!" line and the `Return Code` line having changed
to non-zero.


### Returning the message

Before we go further, let's update our endpoint to not just print our message,
but also return it.
Below is our full, new `hello.proto`, with the added line commented.

`chromite/infra/proto/src/chromite/api/hello.proto`:
```protobuf
// Proto config.
syntax = "proto3";
package chromite.api;

option go_package = "go.chromium.org/chromiumos/infra/proto/go/chromite/api";

import "chromite/api/build_api.proto";

// HelloService/Hello request and response messages.
message HelloRequest {
  string target = 1;
}

message HelloResponse {
  // NEW!
  string hello_message = 1;
}

service HelloService {
  option (service_options) = {
    module: "hello",
  };

  rpc Hello(HelloRequest) returns (HelloResponse);
}
```

Next we need to regenerate the protobuf bindings again.

```shell script
$> cd ~/chromiumos/chromite/infra/proto
$> ./generate.sh
$> cd ~/chromiumos/chromite/api
$> ./compile_build_api_proto
```

We'll then return the message from our `hello_lib.py` function.

`chromite/lib/hello_lib.py`:
```python
def hello(target):
  msg = f'Hello, {target}!'
  print(msg)
  return msg
```

Now we can set the value in the response.

`chromite/api/controller/hello.py`:
```python
@faux.all_empty
@validate.require('target')
@validate.validation_complete
def Hello(input_proto, output_proto, config_proto):
  hello_message = hello_lib.hello(target=input_proto.target)
  output_proto.hello_message = hello_message
```

Let's run the endpoint to make sure it works.

```shell script
$> cd ~/chromiumos/chromite/api/contrib/
$> ./gen_call_scripts
$> cd ./call_scripts/
$> echo '{"target": "moon"}' > hello__hello_input.json
$> ./hello__hello
Running chromite.api.HelloService/Hello
13:32:04: DEBUG: Services registered successfully.
13:32:04: DEBUG: Validating target is set.
Hello, moon!
Completed chromite.api.HelloService/Hello
Success!
Return Code: 0
Result:
{
  "helloMessage": "Hello, moon!"
}
```

The output json file is automatically printed in the `call_scripts` output
(the `Result:` section), so we can see the output now includes our message!


### Case 2: Success message

As we just saw, our successful execution cases now include data in the output
message, so let's update the mock success case to also return a message.

`chromite/api/controller/hello.py`:
```python
from chromite.api import faux
from chromite.api import validate
from chromite.lib import hello_lib

def _hello_success(_input_proto, output_proto, _config_proto):
  output_proto.hello_message = 'Hello, world!'

@faux.success(_hello_success)
@faux.empty_error
@validate.require('target')
@validate.validation_complete
def Hello(input_proto, output_proto, _config_proto):
  hello_message = hello_lib.hello(target=input_proto.target)
  output_proto.hello_message = hello_message
```

You will notice the endpoint itself is untouched, except that have prefixed
the config_proto argument with an underscore.
This convention is used throughout chromite to denote unused arguments, and is
added now for reasons discussed below.

First, we replaced the `@faux.all_empty` decorator with two new ones.
As one might expect, the second (`@faux.empty_error`) is the same failure case
behavior as the `@faux.all_empty` decorator.
The success case, `@faux.success`, and the new function, `_hello_success`, are
the bulk of our change.

The `@faux.success` decorator (and each of its error counterparts) takes a
function to execute when the mock call is executed.
For our success case, we need to populate `output_proto.hello_message`, just
like we did when we added the output.
You'll notice these success and error functions always have underscores
prefixing their input and config arguments.
This is because we don't care what the input is for our mock calls, and we
never need to concern ourselves with the config values at the point where
we're generating a mock response.
For our mock success, our goal is just to fill out a static, valid output.
So we just choose a message that looks sort of like something we might return
normally, and hard code it in.
For more information about the `faux` decorators, see the
[faux reference](../references/faux.md).

Now let's try running it.

```shell script
$> cd ~/chromiumos/chromite/api/contrib/
$> echo '{"target": "moon"}' > ./call_scripts/hello__hello_input.json
$> ./gen_call_scripts
$> echo "Regular execution to compare."
$> ./call_scripts/hello__hello
Running chromite.api.HelloService/Hello
14:35:27: DEBUG: Services registered successfully.
14:35:27: DEBUG: Validating target is set.
Hello, moon!
Completed chromite.api.HelloService/Hello
Success!
Return Code: 0
Result:
{
"helloMessage": "Hello, moon!"
}
$> ./gen_call_scripts --mock-success
$> echo "Mock success execution."
$> ./call_scripts/hello__hello
Running chromite.api.HelloService/Hello
14:37:31: DEBUG: Services registered successfully.
Completed chromite.api.HelloService/Hello
Success!
Return Code: 0
Result:
{
 "helloMessage": "Hello, world!"
}
```

We use the same input file in both calls, but as you can see by the output it
is only used in the normal call.
As we saw in the first example using `@faux.all_empty`, we are also missing
the printed message since we are not executing the endpoint itself, instead
we're only executing our `_hello_success` function, that only populates the
output value with our static "Hello, world!" message.

Success!


### Case 3: Error responses.

We will not go through the exercise of adding error responses here as it is
an identical process to the success case, except using different decorators.
To do the exercise yourself, use the `@faux.error` decorator instead of the
`@faux.empty_error` we used above, passing through your new error function
like we did with the `@faux.success` decorator.
In practice, it is unlikely a success and error case would fill out the
same output field, but for the purposes of a tutorial, it's just fine!
