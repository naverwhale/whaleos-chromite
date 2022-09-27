# Build API Tutorials

These tutorials are meant to be code lab style, bite sized introductions to
different concepts in the Build API.
They are generally meant to be consumed as a whole, so they do all build off a
single endpoint, but each tutorial addresses a different topic.
If you're looking to revisit a specific topic, you can reference the table of
contents below.
If you're new to the Build API, starting from the beginning is recommended
as they cover tools and processes specific to the Build API.

Table of Contents:

* [Part 1](1_hello_world.md)
  * Creating proto and controllers.
  * Registering new services.
  * Generating the protobuf bindings.
  * Call endpoints with `gen_call_scripts`.
* [Part 2](2_hello_target.md)
  * Passing parameters via fields in proto.
  * Custom `gen_call_scripts` input files.
* [Part 3](3_hello_validation.md)
  * Adding validation to the controller with `@validate` decorators.
* [Part 4](4_hello_faux.md)
  * The `@faux` decorators.
  * Making mock calls.
* [Part 5](5_hello_chroot.md)
  * Executing endpoints inside the SDK/chroot.
  * Chroot file and folder injection/extraction.
