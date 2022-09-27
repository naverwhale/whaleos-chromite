# Build API Endpoint Tutorial Part 3

This README is a continuation of
[Hello World Tutorial Part 2](2_hello_target.md),
creating a "Hello world!" endpoint from scratch.
This tutorial assumes you have already executed all the steps in Part 1 and 2,
and have all the code in place.

## Hello World Part 3: Validation

In this tutorial, we'll be looking at argument validation in Build API
endpoints.
This provides a hands-on walkthrough of how to use the validation functionality
in the Build API.
For a full listing of all the validators, and more details about their
functionality see the [validation reference](../references/validation.md).

### "Hello, !"?!?

What happens when you don't pass a value for `target`?
In Part 2, if you tried running `./hello__hello` before updating
`hello__hello_input.json`, you may have already seen this output.
Let's look at it now.

```shell script
$> cd ~/chromiumos/chromite/api/contrib/call_scripts/
$> mv hello__hello_input.json hello__hello_input.json.bak
$> echo "{}" > hello__hello_input.json
$> ./hello__hello
Running chromite.api.HelloService/Hello
15:18:22: DEBUG: Services registered successfully.
Hello, !
Completed chromite.api.HelloService/Hello
Success!
Return Code: 0
Result:
{}
```

Most importantly:

```text
Hello, !
```

#### So what happened?

Since we didn't specify `target`, proto used the default value for the field.
The default value of every field in proto3 is the False-y/empty/0 value for the
type.
Since `target` is a `string`, the default value is an empty string, while the
numeric types and enums default to 0, and bools default to False.

#### How do we fix it?

Validation!
Saying hello to nothing doesn't seem very useful, so we should check in the
endpoint that we do always have a target.
The Build API has a series of validation decorators for checking the contents
of the input proto.
For now, we'll just look at the validation for our new endpoint.

What we want is for `target` to always have a value.
For that, we use the `@validate.require` decorator.
As the name suggests, the require validator requires that the field has a value.
In practice, this means that the field must have a *non-Falsey* value!

**Important:** Because protobuf's default values are the Falsey values, and so
consequently protobuf does not differentiate between passing a Falsey value and
not passing a value at all, neither can we!

`chromite/api/controller/hello.py`:
```python
from chromite.api import validate
from chromite.lib import hello_lib

@validate.require('target')
@validate.validation_complete
def Hello(input_proto, output_proto, config_proto):
    hello_lib.hello(target=input_proto.target)
```

So, what do we have here?

`@validate.require('target')`:
This line is our actual validation, requiring `input_proto.target` to have a
value.

`@validate.validation_complete`:
This line should be added on every function where all validation is completed
by the `@validate` decorators.
As a part of the Build API extended functionality, it allows validation-only
calls to endpoints.
These validation-only calls execute the input validation, and then exit.
The purpose is to allow validation of client implementation on old, branched
versions of the Build API.

#### Validating validation

Let's check that worked.

```shell script
$> cd ~/chromiumos/chromite/api/contrib/call_scripts/
$> ./hello__hello
Running chromite.api.HelloService/Hello
16:23:34: DEBUG: Services registered successfully.
16:23:34: DEBUG: Validating target is set.
16:23:34: ERROR: target is required.
Completed chromite.api.HelloService/Hello
Return Code: 1
Result:
```

Instead of "Hello, !", we got an error!
Now let's check our old "moon" target to make sure it still works.

```shell script
$> mv ./hello__hello_input.json.bak ./hello__hello_input.json
$> ./hello__hello
Running chromite.api.HelloService/Hello
16:29:47: DEBUG: Services registered successfully.
16:29:47: DEBUG: Validating target is set.
Hello, moon!
Completed chromite.api.HelloService/Hello
Success!
Return Code: 0
Result:
{}
```

Success!


## Up Next

Continue to [Part 4](4_hello_faux.md), where we'll look at mock calls and
the faux decorators.
