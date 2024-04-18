<!-- This file is auto-generated!  Do not edit by hand. -->
<!-- To update, run chromite/scripts/generate_query_docs. -->

# `cros query` Target Types

## Board

**Attributes:**

* `arch` (`Optional[str]`): The machine architecture of this board.
* `is_variant` (`bool`): True if this board has another board's top level overlay in its
        overlays parents.

* `top_level_overlay` (`Optional[Overlay]`): The top-level overlay for this board.
* `top_level_profile` (`Optional[Profile]`): The top-level profile for this board.
* `use_flags` (`Set[str]`): The fully-evaluated USE flags for this board.

## Ebuild

**Attributes:**

* `eapi` (`int`): The EAPI for the package.
* `eclasses` (`List[str]`): A list of the eclasses inherited by this package and its eclasses.
* `get_stability(arch: str) -> Stability`: Get the stability of this package on a given architecture.

        Args:
            arch: The architecture to consider for stability.

        Returns:
            The stability on this architecture.

* `iuse` (`Set[str]`): A set of the flags in IUSE.
* `iuse_default` (`Set[str]`): A set of the flags enabled by default in IUSE.
* `keywords` (`List[str]`): The KEYWORDS of this package.
* `md5_cache_file` (`Path`): The path to the md5-cache file for this ebuild.
* `package_info` (`PackageInfo`): The PackageInfo for this ebuild.
* `vars` (`Dict[str, str]`): The raw variables from the md5-cache file.

## Profile

**Attributes:**

* `arch` (`str`): The machine architecture of this profile.
* `forced_use_flags` (`Set[str]`): The resolved set of forced USE flags for this profile.
* `make_defaults_vars` (`Dict[str, str]`): A dictionary of the raw make.defaults variables.
* `masked_use_flags` (`Set[str]`): The resolved set of masked USE flags for this profile.
* `parents` (`List[Profile]`): A list of the immediate parent profiles of this profile.
* `resolve_var(var: str, default: Optional[str]) -> Any`: Resolve a variable for this profile, similar to how Portage would.

        Note: this function resolves variables non-incrementally.  For
        incremental variables (e.g., USE, USE_EXPAND, etc), use
        resolve_var_incremental.

        Args:
            var: The variable to resolve.
            default: What to return if the variable is not set.

        Returns:
            The resolved variable.

* `resolve_var_incremental(var: str) -> Set[str]`: Resolve a variable incrementally, similar to how Portage would.

        This will traverse the profiles depth-first, adding tokens which are not
        prefixed with a dash, and removing those which are.

        Args:
            var: The variable to resolve.

        Returns:
            The resolved variable, as a set of the tokens.

* `use_flags` (`Set[str]`): A set of the fully-resolved USE flags for this profile.
* `use_flags_set` (`Set[str]`): A set of what USE flags this profile enables.
* `use_flags_unset` (`Set[str]`): A set of what USE flags this profile disables.

## Overlay

**Attributes:**

* `board_name` (`Optional[str]`): If this overlay is a top-level overlay for a board, the name of that
        board.  Otherwise, this is None.

* `ebuilds` (`List[Ebuild]`): A list of all ebuilds in this overlay.
* `get_profile(name: Union[Path, str]) -> Optional[Profile]`: Get a specific profile by name.

        Args:
            name: The name of the profile (e.g., "base").

        Returns:
            The Profile object with this name, or None if this profile does not
            exist.

* `is_private` (`bool`): True if the overlay appears to be private, false otherwise.
* `layout_conf` (`Dict[str, str]`): The layout.conf variables.
* `make_conf_vars` (`Dict[str, str]`): The variables defined in make.conf.
* `md5_cache_dir` (`Path`): The md5-cache directory for this overlay.
* `metadata_dir` (`Path`): The metadata directory for this overlay.
* `name` (`str`): The repo-name in metadata/layout.conf.
* `parents` (`List[Overlay]`): The Portage masters of this overlay.  Note the COIL rename.
* `profiles` (`List[Profile]`): A list of all profiles defined in this overlay.
* `profiles_dir` (`Path`): The profiles directory for this overlay.
