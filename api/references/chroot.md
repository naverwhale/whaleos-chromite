# SDK/Chroot Interactions Reference

This file contains more in depth information about interacting with the SDK
(a.k.a. chroot) in the Build API.
[The SDK tutorial](../tutorials/5_hello_chroot.md) provides a quick
walk-through of the steps to set up an endpoint that runs inside the SDK,
and is the recommended starting point if you're just getting started.

## Chroot Assert Options

Where an endpoint is run is determined by the Chroot Assert Service and Method
Options.
See the [Build API Proto Reference](./build_api_proto.md) for more information.

## Overview: The "Path" Messages

The "Path" messages generally refers to three different messages that are used
to inject and extract artifacts; `Path`, `ResultPath`, and `SyncedDir`.
All three messages can be found in
[common.proto](chromium.googlesource.com/chromiumos/infra/proto/+/refs/heads/main/src/chromiumos/common.proto).

## The `Path` and `ResultPath` Messages

At its core, `Path` message simply represents a path on the filesystem inside
or outside of the SDK.
The message has a `path` string field for the path itself, which should
generally be an absolute path.
It also has a `location` field to note whether the path is inside or outside
of the SDK.
When constructing a request the `location` will virtually always be outside,
and when constructing a response the `location` will virtually always be inside.
There are plans to make `location` optional in the long term except in very
specific edge cases, but it is currently required.

The `ResultPath` message is simply a named wrapper around a `Path` message to
allow easily identifying it when used.
There may be at most one `ResultPath` message per request.
A `ResultPath` message in a response is essentially meaningless.
A `ResultPath` field never needs to be used directly in an endpoint, it is only
for the Build API itself; instead, the endpoint can produce (or simply locate)
the files however is most convenient and put those paths in the response, and
they will still end up in the final result path.

There are two use cases for these messages.
Files/directories in `Path` messages in a request are automatically injected
into the SDK.
Files/directories in `Path` messages in a response are automatically extracted
from the SDK when there is a `ResultPath` message in the request.


### Artifact Injection

Injection is accomplished by simply setting a `Path` message in a request to
the **file or directory** that is to be injected.
The files/directories are copied into a `/tmp` directory in the SDK.
Each `Path` gets a separate `/tmp` directory to avoid collisions.
When given a directory, the contents will be copied recursively.
This injection process is handled entirely by the Build API itself.
The endpoint itself will only ever see the injected path, and does not need to
worry about the outside path, or cleaning up the file.

#### Injection Examples

The following examples provide the populated request values outside the SDK,
as well as the request values inside the SDK, which is what the endpoint would
actually see.

**Example 1**: Single file.
* Request Outside: Request from outside the SDK used to invoke the Build API.
  * `Path` = ~/input/file.txt
* Request Inside: Generated request inside the SDK the endpoint actually sees.
  * `Path` = /tmp/tmp-abc123/file.txt

**Example 2**: Single directory.
* Request Outside
  * `Path` = ~/input
    * ~/input
      * file.txt
      * subdir/other-file.txt
* Request Inside
  * `Path` = /tmp/tmp-abc123
    * /tmp/tmp-abc123
      * file.txt
      * subdir/other-file.txt

**Example 3**: Multiple paths.
* Request Outside
  * `Path` = ~/input
    * ~/input
      * file.txt
      * subdir/other-file.txt
  * `Path` = ~/file1.txt
  * `Path` = ~/file2.txt
* Request Inside
  * `Path` = /tmp/tmp-abc123
    * /tmp/tmp-abc123
      * file.txt
      * subdir/other-file.txt
  * `Path` = /tmp/tmp-xyz789/file1.txt
  * `Path` = /tmp/tmp-123456/file2.txt

### Artifact Extraction

The two components to extraction are a `ResultPath` field in the request, and
one or more `Path` fields in the response.
The `ResultPath` specifies the path outside the SDK where the artifact(s) should
be extracted to.
The `Path` fields specify one or more files and/or directories inside the SDK
that should be extracted.
The artifacts inside the SDK do not need to be collected prior to extraction,
however, **non-unique names will cause undefined behavior**.

In practice, that currently means files will be overwritten, and directories
will raise an error.
The behavior of non-unique names may change at any time, and in the future
we may define the behavior as something other than what it is today, so until
such a time, ensure you have unique paths to guarantee it works properly.
See examples 5 and 6 for possible collision outputs today.


**Example 1**: Multiple unique files.
* Request
  * `ResultPath` = ~/results
* Response
  * `Path` file1 = /inside/file1
  * `Path` file2 = /other/inside/file2
* Result:
  * ~/results
    * file1
    * file2


**Example 2**: Multiple directories.
* Request
  * `ResultPath` = ~/results
* Response
  * `Path` dir1 = /inside/dir1
    * /inside/dir1
      * file1
      * file2
  * `Path` dir2 = /other/inside/dir2
    * /other/inside/dir2
      * foo
      * bar
* Result:
  * ~/results
    * file1
    * file2
    * foo
    * bar


**Example 3**: Nested directories.
* Request
  * `ResultPath` = ~/results
* Response
  * `Path` dir1 = /inside/dir
    * /inside/dir
      * nested1/
        * file1
      * nested2/
        * file2
  * `Path` dir2 = /other/inside/dir
    * /other/inside/dir
      * nested3/
        * foo
      * bar
* Result:
  * ~/results
    * nested1/
      * file1
    * nested2/
      * file2
    * nested3/
      * foo
    * bar


**Example 4**: File and directory.
* Request
  * `ResultPath` = ~/results
* Response
  * `Path` file = /inside/file
  * `Path` dir = /inside/dir
    * /inside/dir
      * file
      * foo
* Result:
  * ~/results
    * file
    * dir
      * file
      * foo


**Example 5**: (Undefined Behavior) File name collision!
* Request
  * `ResultPath` = ~/results
* Response
  * `Path` file1 = /inside/file = 'File content!'
  * `Path` file2 = /other/inside/file = 'Different content!'
* Result:
  * ~/results
    * file = 'Different content!'
      * Note: 'File content!' is also possible.


**Example 6**: (Undefined Behavior) File collisions in nested directories.
* Request
  * `ResultPath` = ~/results
* Response
  * `Path` dir1 = /inside/dir1
    * /inside/dir1
      * nested/
        * file = "Dir1 File!"
  * `Path` dir2 = /other/inside/dir2
    * /other/inside/dir2
      * nested/
        * file = "Dir2 File!"
* Result:
  * Error: nested exists.
  * Return code: 1


## `SyncedDir` Message

A `SyncedDir` must be in a request to use the functionality.
The `SyncedDir` provides a means of syncing the contents of a directory into
and out of the SDK.
Everything inside the directory in injected into the SDK just like a directory
in a `Path` field would be.
The key difference is that the contents of the directory are also extracted
from the SDK after the endpoint completes.
This is a destructive operation, it will remove files that were in the directory
if they were deleted from the folder inside the SDK.

### Example

* Request Outside
  * `SyncedDir` = ~/synced
    * ~/synced
      * foo.txt
      * subdir/bar.txt
* Request Inside Before Execution
  * `SyncedDir` = /tmp/tmp-abc123
    * /tmp/tmp-abc123
      * foo.txt
      * subdir/bar.txt
* Request Inside After Execution
  * `SyncedDir` = /tmp/tmp-abc123
    * /tmp/tmp-abc123
      * foo.txt
      * new-file.txt
      * subdir/replaced-bar.txt
* Final Directory Contents
  * ~/synced
    * foo.txt
    * new-file.txt
    * subdir/replaced-bar.txt
