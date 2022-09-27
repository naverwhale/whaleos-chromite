# Build API Endpoint Tutorial Part 2

This README is a continuation of
[Hello World Tutorial Part 1](1_hello_world.md),
creating a "Hello world!" endpoint from scratch.
This tutorial assumes you have already executed all the steps in Part 1, and
have all its code in place.

## Hello World Part 2: "Hello {argument}!"

"World" is great and all, but it'd be nice to be able to say hello to other
things.
This continuation will walk through adding fields to requests, using them in
the endpoints, and manually executing parameterized endpoints.

### Step 1: Parameterizing the library.

First, let's upgrade our lib.

`chromite/lib/hello_lib.py`:
````python
def hello(target):
    print(f'Hello, {target}!')
````

Now we can say hello to whatever we want!

### Step 2: Parameterizing the proto.

Next, we need to add a field to our proto, so we can pass it in through the API.
This time we'll just look at the HelloRequest message, as it's the only
part that needs changes.
We'll add a new string field to pass our target.

`chromite/infra/proto/src/chromite/api/hello.proto`:
```protobuf
// HelloService/Hello request and response messages.
message HelloRequest {
  string target = 1;
}
```

Since we've updated the proto, we'll need to regenerate the protobuf bindings
again.

```shell script
$> cd ~/chromiumos/chromite/infra/proto
$> ./generate.sh
$> cd ~/chromiumos/chromite/api
$> ./compile_build_api_proto
```

### Step 3: Passing arguments.

Finally, we update our controller.
We just need to pull the field out of the proto and pass it through to our
hello_lib.hello call.
The input proto is the instance of the HelloRequest we provide, so we just need
to grab the field from the message.

`chromite/api/controller/hello.py`:
```python
from chromite.lib import hello_lib

def Hello(input_proto, output_proto, config_proto):
    hello_lib.hello(target=input_proto.target)
```

### Step 4: Calling the parameterized endpoint.

We can still use the `gen_call_scripts` workflow we used in Step 6, we just
need to add the values to our request.
As noted earlier, the `gen_call_scripts` workflow generates an input for each
endpoint automatically.
By default, it'll generate an empty input file, so we just need to add to the
file we already have.

```shell script
$> cat chromite/api/contrib/call_scripts/hello__hello_input.json
{}
```

Let's say hello to the moon, instead.

`chromite/api/contrib/call_scripts/hello__hello_input.json`
```json
{"target": "moon"}
```

And that's it!
Now if we run the endpoint, we should see our updated greeting.

```shell script
$> cd ~/chromiumos/chromite/api/contrib/call_scripts/
$> ./hello__hello
Running chromite.api.HelloService/Hello
14:39:27: DEBUG: Services registered successfully.
Hello, moon!
Completed chromite.api.HelloService/Hello
Success!
Return Code: 0
Result:
{}
```

Success!

## Up Next

Continue to [Part 3](3_hello_validation.md), where we'll look at validating the
input.
