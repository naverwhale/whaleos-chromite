# CLI Guidelines

Define standard options to create a consistent CLI experience across tools.
When developers get used to certain option behavior, having them available
across all tools makes things much easier & smoother.
Conversely, when the same option name is used but with wildly different
meanings, this can be very surprising for developers, and possibly lead them
to do something destructive they didn't intend.

See the [Chromite CLI Framework](/cli/README.md) document for Chromite-specific
APIs.

[TOC]

## Short Options

Short options should be used prudently, after careful thought & consideration.
Do not add them to long options purely for the sake of having a short option.
Not every option needs a short option, plus the set of possible short options
is significantly smaller than the set of possible long options (since a short
option, practically speaking, can only be printable ASCII).

Short options should only be used when a developer is expected to type it often
themselves (not for script usage), ideally should be "obvious" as to what long
option it implies, and should be considered in context of other tools.
See [Required Option Conventions] for more information.

All short options must provide a long option.
See [Long Option Naming Conventions] for more details.

See [Short Long Options] as an alternative to using a short option.

## Boolean Options

Long options that control boolean settings should provide both positive and
negative options, and allow them to be specified multiple times.
The default value should be clearly documented.

### Naming

The negative option prefix is `--no-`.
For example, `--reboot` and `--no-reboot`.

Do not omit the `-` after the `no`.
This makes reading the option at a glance more difficult (e.g. `--noclean`),
or end up making it look like a different word (e.g. is `--nobody` "no body", or
is it the "nobody" user account).

Do not use other prefix words like `skip` or `set` or `disable` or `enable`, nor
use them in conjunction with `no` (e.g. `--skip-reboot` and `--no-skip-reboot`).
This provides consistent naming & style for developers.

### Internal Variables

Even when the default behavior is the negative value, the code should avoid
negative variable names.

Python's argparse module makes it easy to support multiple boolean options that
store the result in a specifically named variable.
See the [Example Code](#bool-example-code) below.

### Chaining

Specifying multiple boolean options should work fine, and should follow the
standard "last option wins" policy.
This makes it easy for developers to copy & paste long commands (e.g. from logs)
and change options slightly by adding another flag to the end without having to
scan the entire command line and edit it in the terminal.

For example:

* `--wipe`: "wipe" is enabled.
* `--no-wipe`: "wipe" is disabled.
* `--wipe --no-wipe`: "wipe" is disabled.
* `--no-wipe --wipe`: "wipe" is enabled.
* `--wipe --wipe --no-wipe --wipe --no-wipe`: "wipe" is disabled.

Python's argparse module already behaves this way by default.

If you need to add more complicated options, such as aliases, you probably want
to define a custom `action` when calling `add_argument()`.
Custom actions are called immediately when processing which allows for updating
the state rather than post-processing at the end.
See the [Example Code](#bool-example-code) below.

### Example Code {#bool-example-code}

```python
# Create a boolean option.  The default is None to indicate the user hasn't made
# a choice.  This can sometimes be useful when processing default behavior.  If
# the default should be explicit, use `default=...` with the --reboot option.
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--reboot', action='store_true')
parser.add_argument('--no-reboot', dest='reboot', action='store_false')
```

```python
# Create boolean options with another option that implies others.  This is
# written so that multiple stacked options are handled correctly.  The custom
# action hooks directly into the option processing state machine.
class _ActionAliasForAB(argparse.Action):
  def __call__(self, parser, namespace, values, option_string=None):
    setattr(namespace, 'A', True)
    setattr(namespace, 'B', True)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--A', action='store_true')
parser.add_argument('--B', action='store_true')
parser.add_argument('--no-B', dest='B', action='store_false')
parser.add_argument('--alias-for-A-B', nargs=0, action=_ActionAliasForAB)
```

## Long Option Separators

Long options use kebab-case, not snake_case, when separating words.
For example, `--a-long-option` is correct while `--a_long_option` is not.

Since the option has to start with two dashes (`--`) and never two underscores
(`__`), using dashes consistently is preferred.

Dashes are easier to type on the most common keyboard layouts our developers
use (US English [QWERTY]) as `_` requires holding the Shift key.

Do not omit separators entirely as it makes it hard for readers at a glance.
Tryreadingthiswithoutseparators.

If backwards compatibility is a factor, both variants can usually be supported.
Document the dashes (e.g. `--an-opt`) as the primary one, and list the
underscores (e.g. `--an_opt`) as a deprecated compatibility form.

## Long Option Naming Conventions

Long option names should use full words when possible and avoid unnecessary
abbreviations or uncommon acronyms.
The point of long options is to aid in clarity & readability (and logs), and
abbreviations can often be inconsistent between tools.

Some examples:

* Use `--description`, not `--desc`.
* Use `--message`, not `--msg`.
* Use `--text`, not `--txt`.

[Long Option Naming Conventions]: #long-option-naming-conventions

### Short Long Options

While long options are great for scripts & automation, they can be painful for
developers, especially for longer multi-word options.
This can lead people to providing nonsensical short options simply so users
don't have to type out the full long option.
This is an anti-pattern and leads to inconsistent short options between tools,
and makes developers have to read help/manuals constantly since they won't be
able to easily remember which option does what for every tool.

One alternative is that Python's argparse, and some other option parsing APIs,
will automatically complete unambiguous partial long options for you.
So if a CLI supports `--description`, but no other long option that starts with
a `--d`, users can already use `--d`, `--de`, `--desc`, etc... for free.
Keep in mind this should never be used in a script as there is no long term
guarantee that these remain unambiguous.
If `--delicious` is added later, then `--d` and `--de` are no longer unambiguous
leading to errors (although `--des`, etc... still work).

Another alternative is to provide a terse short long option.
Again, this is purely for users to type out, not to use in automation.
These should only be provided as secondary aliases to the more formal option,
and never as the only one per the naming conventions outlined above.
This should also only be provided when demand suggests that it's an option that
users will regularly use -- do not provide a terse short long option purely for
the sake of it.

Some examples:

* `--description` & `--desc`
* `--branch` & `--br`

[Short Long Options]: #short-long-options

## Required Option Conventions

Tools should adhere to these conventions whenever possible, and any deviation
should be strongly reconsidered.

| Short | Long          | Description |
|:-----:|---------------|-------------|
|       | [--debug]     | Show debugging information. |
| [-f]  | [--force]     | Force an operation. |
|       | [--format]    | Control output format. |
| [-h]  | [--help]      | Show tool help/usage output. |
| [-j]  | [--jobs]      | Control parallelization. |
| [-n]  | [--dry-run]   | Show what would be done. |
| [-q]  | [--quiet]     | Quiet(er) output. |
| [-v]  | [--verbose]   | Verbose(r) output. |
|       | [--version]   | Show tool version information. |
| [-y]  | [--yes]       | Skip prompts. |

[Required Option Conventions]: #required-option-conventions

### --debug {#debug}

Show internal debugging information that the user would find helpful.
This may be very verbose.

[--debug] may be specified multiple times to make the output even debuggier.

The short option [-d] may be used depending on the tool, but usually enabling
extra debugging is not a common operation.

[-d]: #debug
[--debug]: #debug

### --force {#force}

The user wants to bypass any safety checks.
The help text should provide clear guidance on how this will affect behavior
since it can potentially be very dangerous and lead to data loss.

For example, when imaging a device, do not prompt the user whether they really
meant to erase the non-removable `/dev/sda` hard drive.
Or if there are mismatches in hashes or other integrity checks, attempt to do
the operation anyways (installing files, etc...).

Do not confuse this with the [--yes] option for agreeing to common prompts.

The short option [-f] may be used or omitted depending on how dangerous the
option actually is in practice.
If the tool might delete the user's desktop or source, probably safer to make
them type out the full [--force].
If the tool would only delete some temporary files or something that could be
recreated (even if it requires a bit of effort), then [-f] is OK.

[-f]: #force
[--force]: #force

### --format {#format}

Control the output format of the tool.

Only add a single [--format]`=<format>` option.  Avoid adding any `--<format>`
options at all.  The default should always be `automatic`, even if there aren't
that many choices.  This provides some future proofing as tooling evolves, and
signals to users that they have to pick a specific format when writing scripts
to avoid things breaking in the future.

Tools often handle a variety of formats, in their inputs & outputs, and with
users wanting to explicitly control what is displayed to them.
Providing automatic detection with reasonable default behavior is OK, but
options should be provided for explicit control.

For example, the `gerrit` tool can output in JSON, markdown, and more.
The default is automatic which detects whether to use readable human-centric
summaries or terse raw data which is useful for developers running things
directly, but can be a nightmare when attempting to write scripts on top of it.

Often tools start off with a single output format, and then someone requests a
second one.  It can be tempting to use an option name that matches the format,
but this is inevitably a short term trap.  For example, when adding a new JSON
output format, you might start with `--json`.  But when other formats come up,
adding `--markdown` and such easily get out of hand, both for the user (lots
of options in `--help` output), and for the tool author (who has to register
each option and then handle conflicting `--markdown --json` situations).

While [--format] is most commonly associated with the output of a tool, this is
not a strict requirement.  If a tool never outputs anything and only takes an
input, using [--format] is permissible.  Use your best judgment.

Do not provide `--fmt` as a shorter name.  It really doesn't save that many
bytes compared to [--format].

[--format]: #format

#### Format Names

Some common format names:

*   `automatic` (alias: `auto`): Good for switching between `pretty` and some
    other format (e.g. `raw`) depending on whether stdout is connected to a
    terminal.  Good for sniffing input files and guessing at their format.
*   `json`: JSON output of some format; good for returning structured results.
    Some care should be taken to support backwards compatibility (e.g. always
    return an object with at least a `version` field), but this is not strictly
    required.
*   `raw`: A bare minimum output format useful for extracting the most common
    data that developers would want.  e.g. `gerrit --raw search` only returns CL
    numbers with no metadata.  This should never be structured content.
*   `pretty`: Good for humans to read, and never for machines to parse.

#### Multiple Streams

A single [--format] option is common when a tool only outputs to one place,
and all of its inputs are of a specific format.
When there are multiple inputs or outputs whose format can be controlled, add
dedicated options to control each stream (using the pattern
`--<name>-format=<format>`), with the [--format] option setting a common
default.

For example, if there is a single input and a single output,
`--input-format=<format>` & `--output-format=<format>` is a good choice, in
addition to the common [--format].

The ordering of options should not override each other.  For example, using
`--output-format=foo --format=bar` should behave the same as
`--format=bar --output-format=foo`.  In these cases, [--format] is only for
selecting a default if a stream-specific format has not been specified.

Definitely do not provide separate format-specific options for each stream,
otherwise the set of options really grows out of control.  For example, do
not use options like `--input-json`, `--input-binary`, `--output-json`, and
`--output-binary`.

This has the nice benefit of disambiguating options that control paths and
options that control formats.  For example, is `--input-json` a boolean, or
does it expect a path to a JSON file?  Use `--input <path>` and
`--input-format=<format>` instead.

### --help {#help}

Show the tool usage, examples, and other helpful information.
Since the user has explicitly requested the help output, this does not need to
be terse.
Normal output should only go to stdout, and the tool should exit 0.

When processing unknown or invalid options, it's OK to show a short summary of
the specific option, or of valid options, but it should not be the full detailed
output like [--help].
The user should be able to focus on what they got wrong, not wade throw pages of
output to try and track down the one error line.
This output should only go to stderr, and the tool should exit non-zero (either
`1` or `64`).

Use of the short [-h] option is recommended out of wide convention.
Avoid reusing this for something else like `--human`, and definitely never use
it for something destructive or unrecoverable.

[-h]: #help
[--help]: #help

### --jobs {#jobs}

Limit how much parallelism should be used.
This typically translates to how many threads or CPUs to utilize.

The special value `0` should be used to indicate "use all available CPU cores".

The default does not have to always be `1` thus forcing users to manually pick
a value, nor does it have to always be `0`.
Try to balance how expensive a particular job is (network, servers, I/O, RAM,
etc...) with a reasonable default.
For example, when talking to a network service, high values like 72 will
probably cause many connections to be rejected so it won't be overwhelmed, so
find a default that balances real world improvements (compared to `-j1`) with
the server costs.

The default should rarely be hardcoded to a value above 1 -- run it through a
max function with how many cores are available.
For example, the default could be `max(4, os.cpu_count())`.

To determine how many CPU cores are available:
* Python: `os.cpu_count()`
* Shell: `getconf _NPROCESSORS_CONF 2>/dev/null || echo 1`

Use of the short [-j] option is recommended out of wide convention.

Do not use `--cpus` or `--cores` or `--procs` or `--threads` or similar names
as the options should be user focused, not internal implementation details.
In other words, users want to run multiple tasks in parallel, they don't care
about matching jobs to hardware or OS level concepts.
Especially considering internals change (multiprocessing vs multithreading), and
the distinction between cores & cpus can be easily lost or irrelevant, and they
might run more tasks than corresponding hardware is available.
For example, using `--cores=10` to run 10 slow I/O jobs in parallel on a system
with 2 cpus is confusing.

[-j]: #jobs
[--jobs]: #jobs

### --dry-run {#dryrun}

Show what would be done, but don't actually "do" anything.
Users should be able to add this option anywhere and expect that the tool will
not make any changes anywhere.
Basically this should always be a harmless idempotent operation.

Use of [--dry-run] is, by itself, not an error, thus it should normally exit 0.
This allows the user to quickly detect problems before trying to make changes.
For example, if invalid options were specified, the tool can show fatal errors.
Or if inputs don't exist, or are corrupt, they may be diagnosed.

The tool may talk to network services, or otherwise make expensive computations,
as long as it doesn't make any changes, and may be rerun many times.

The tool should display what it would have done were [--dry-run] not specified.
This will often take the form like `Would have run command: git push ...`.

Bypassing reasonable prompts is permitted as long as no changes are made.
In other words, this may behave like [--yes] or [--force] in some situations.
Use your best judgment as to what constitutes the best user experience.

Use of the short [-n] option is recommended out of wide convention, and because
use of dry-run first is a common user flow.

The [--dryrun] option should be accepted as an alias to [--dry-run], but should
be omitted from documentation (i.e. [--help] output).
This helps users who typo things, and because some tools have adopted that
convention instead of [--dry-run] (although the latter is still more common).

Internally, code should prefer to use `dryrun` as the variable name rather than
`dry_run` for consistency, and because it's easier to type.

[-n]: #dryrun
[--dry-run]: #dryrun
[--dryrun]: #dryrun

### --quiet {#quiet}

Make the output less verbose.
General information should be omitted, and only display warnings or errors.

[--quiet] may be specified multiple times to make the output even quieter.
Some recommended settings:
* *default*: Show important events, warnings, and worse.
* `-q`: Only show warnings and worse.
* `-qq`: Only show (fatal) errors and worse.
* `-qqq`: Don't show any output -- rely on exit status to indicate pass/fail.

Use of the short [-q] option is recommended out of wide convention.

If desired, [--silent] may be used as an alias to `-qqq` behavior; i.e. do not
emit any output, only exit 0/non-zero.

[-q]: #quiet
[--quiet]: #quiet
[--silent]: #quiet

### --verbose

Make the output more verbose.
This may include some helpful info or progress steps.
Important information for the user should not be hidden behind [--verbose];
i.e. users should not be expected to use [--verbose] all the time.

[--verbose] may be specified multiple times to make the output even verboser.

Debugging information should not be included here -- use [--debug] instead.
Use your best judgment as to what is verbose output and what is debug output.

Use of the short [-v] option is recommended out of wide convention, and because
it can be common to type `-vvv` to quickly get more verbose output when trying
to track down problems.

[-v]: #verbose
[--verbose]: #verbose

### --version {#version}

Show version information for the current tool.
Normal output should only go to stdout, and the tool should exit 0.

The default output should be short & to the point, and cheap to produce.
This may include terse authorship information if desired.

If combined with [--verbose], related package/tool information may be included.

If combined with [--quiet], the output should be just the version number.

For example, common output might look like:
```
$ tool --version
CrOS tool v1.2.3
Written by some decent engineers.

$ tool --version --quiet
1.2.3

$ tool --version --verbose
CrOS tool v1.2.3
Current git repo is at add119cea9ebfd7ba89f7606ed04cac7cacaa43d.

Some important library information:
  foo lib v2
  another lib v3.4

Written by some decent engineers.
```

No short option should be provided for [--version].
It's not a common operation, so allocating one of the limited short options
is a waste.

[--version]: #version

### --yes {#yes}

The user wants to "agree" to any standard prompts shown by the tool.
This should not be used by itself to bypass safety checks -- see [--force]
instead, with which this can be combined.

The prompts that would have been shown should still be emitted so it's clear
what the user has agreed to, and include fake input.  For example:
```
$ do-something --yes
Do you want to do something? (Y/n) <yes>
```

Use of the short [-y] option is recommended out of wide convention, and because
skipping the same set of prompts is a common flow to avoid annoying users.

[-y]: #yes
[--yes]: #yes
