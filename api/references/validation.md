# Build API Validation

This doc provides quick reference/usage information about the Build API
`validate` decorators.
The [validation tutorial](../tutorials/3_hello_validation.md) provides a
tutorial format, but starting at [the beginning](../tutorials/0_introduction.md)
is recommended if you are new to the Build API.

Validation should be done using the `validate` decorators whenever possible.
In particular, the decorators handle validation only calls for you if all
validation can be done with the decorators.
If you do need to do custom validation in the controller, you will also need to
handle the validation only call by checking the config for the validation only
call type and manually returning early with a success return code after the
validation is complete.


## Addressing Nested Fields

All validation decorators support addressing arbitrarily nested fields for any
field or subfield argument.
This is done by simply adding '.' between field names as one would do if
accessing the fields directly from the message object itself.
As with accessing properties of the object itself, it works for any arbitrary
nesting as long as there are no repeated fields in the specified path.
See the protobuf message below commented with the string used to address each
field.

```protobuf
message Example {
    message Foo {
        message Bar {
            // 'foo.bar.id'.
            int32 id = 1;
            message Baz {
                // 'foo.bar.bazzes.name' will NOT work.
                string name = 1;
            }
            // 'foo.bar.bazzes'.
            repeated Baz bazzes = 2;
        }
        // 'foo.bar'.
        Bar bar = 1;
    }
    // 'foo'.
    Foo foo = 1;
}
```


## each_in

`each_in(field: str, subfield: str, values: Iterable, optional=False)`

`each_in` will check that each value in a repeated field, or each value in a
subfield of a repeated message, is in the given values.
Passing `optional=True` allows only validating the field when it is set to
_some_ value.
This is the equivalent of [`is_in`](#@validate.is_in) for repeated fields.

The following example illustrates the two use cases for `each_in`; a repeated
scalar field, and a repeated message field.

```protobuf
message ExampleRequest {
    repeated string names = 1;

    message SubMessage {
        // Can be validated.
        int32 id = 1;
        // Can't be validated because it's a repeated field in a repeated
        // message.
        repeated int32 cant_be_validated = 2;
    }
    repeated SubMessage submessages = 2;
}
```

```python
# Repeated scalar field, checks every `names` value is either 'foo' or 'bar'.
# Python equivalent:
#   input_proto.names and [x in ['foo', 'bar'] for x in input_proto.names]
@validate.each_in('names', None, ['foo', 'bar'])
# Repeated message field, checks the `id` field of every `submessage` is in
# 1-10, but `submessages` may be empty.
# Python equivalent:
#   all(x.id in range(10) for x in input_proto.submessages)
@validate.each_in('submessages', 'id', range(10), optional=True)
def Example(input_proto, output_proto, config):
    pass
```


## exists

`exists(*fields: str)`

`exists` verifies the file or directory pointed to by the given fields exist.
`exists` can be given as many fields as need to be checked.
This has the side effect of also requiring the field to be set, technically
making `require` decorators for these fields redundant, but even so are not
discouraged.

```python
# Validate input_proto.path1 and input_proto.path2 exist.
# Python equivalent:
#   os.path.exists(x) for x in (input_proto.path1, input_proto.path2)
@validate.exists('path1', 'path2')
def Example(input_proto, output_proto, config):
    pass
```


## is_in

`is_in(field: str, values: Iterable)`

`is_in` verifies the given field has one of the given values.

```python
# Python equivalent:
#   input_proto.id in range(1, 10)
@validate.is_in('id', range(1, 10))
def Example(input_proto, output_proto, config):
    pass
```


## require

`require(*fields: str)`

`require` verifies each field has a value set.
Since protobuf gives back falsey values when not set, this validator is not
capable of distinguishing between an unset field and one that were set with
a falsey value (e.g. 0, empty string, False).

```python
# Require `foo` and `bar` are set.
# Python equivalent:
#   input_proto.foo and input_proto.bar
@validate.require('foo', 'bar')
def Example(input_proto, output_proto, config):
    pass
```


## require_any

`require_any(*fields: str)`

`require_any` verifies that at least one of the given fields has been set.
It has the same semantics as [`require`](#require) for validating values.
This is useful when there are multiple fields that can be used specify an
argument that is required, but any are acceptable.
For example, when transitioning between two fields, it may be easiest to
support using either of them, but the endpoint only needs one of them to be set.

```python
# Require either 'id' or 'identifier' is set.
# Python equivalent:
#   input_proto.id or input_proto.identifier
@validate.require_any('id', 'identifier')
def Example(input_proto, output_proto, config):
    pass
```


## require_each

`require_each(field: str, subfields: Iterable[str], allow_empty=True)`

`require_each` verifies every entry in the repeated `field` has each of the
given `subfields` set.
By default, the validator allows `field` itself to be empty, only verifying
that when it is populated the fields are set.
Setting `allow_empty` to False also requires the field itself is not empty.

```python
# Require any `foos` have `bar` and `baz` set.
# Python equivalent:
#   all(x.bar and x.baz for x in input_proto.foos)
@validate.require('foos', ['bar', 'baz'])
# Require all `points` have `x` and `y` set.
# Python equivalent:
#   input_proto.points and all(p.x and p.y for p in input_proto.points)
@validate.require('points', ['x', 'y'], allow_empty=False)
def Example(input_proto, output_proto, config):
    pass
```


## validation_complete

`validation_complete()`

When all validation can be done with `validate` decorators,
`validation_complete` handles validation only calls.
It should be used in every instance it can be used.
It must be the last `validate` decorator when used.

```python
@validate.require('foo')
@validate.validation_complete
def Example(input_proto, output_proto, config):
    pass
```
