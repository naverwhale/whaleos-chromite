# Depgraph Visualizer

## Installation
Enter your SDK, go to this modules location,
then run install.sh to create a virtualenv and install all
requirements and this module itself. Then just activate your virtualenv.

```bash
cros_sdk --enter
cd ~/trunk/chromite/contrib/depgraph_visualization
./install.sh
source my_visualizations/bin/activate
cd my_visualizations
```

This will put a script called `visualize_depgraph` on your PATH. From there you
can run `visualize_depgraph --help` to see the available options.

## Usage
To use  `visualize_depgraph` you only need to specify the
`-b`/`--build-target` argument with the target build of your choosing.
This will create an HTML with the whole dependency graph on it.
Just click it to view it in your default browser.

```bash
visualize_depgraph  -b=amd64-generic
visualize_depgraph  --build-target=amd64-generic
```

You can also create a dependency graph for one or more packages by
passing them as arguments; just be sure that these packages have
plenty of dependencies otherwise the resulting graph might not be so useful.

```bash
visualize_depgraph chromeos-base/crosvm -b=amd64-generic
visualize_depgraph chromeos-base/crosvm chromeos-base/tast-build-deps -b=amd64-generic
```
The default name and location of the output file is "DepGraph" and "./"
respectively. To change them you can use the options `--output-name`
and `--output-path`.

```bash
visualize_depgraph net-fs/samba -b=amd64-generic --output-path=bar/foo --output-name=SambaGraph
```
## Secondary usage
With the argument `--include-histograms` you can also generate four png files
with histograms for dependency and reverse dependency distribution.
These plots are partition in two because the number of packages Y with a range
X of (reverse)dependencies goes from 600 to 1.
```bash
visualize_depgraph --include-Histograms=True --output-path=foo/bar -b=arm64-generic
```
These files are saved in the same directory as the main output file.

## Important notes

If you were to use a package with no dependencies
you would just see the package itself. Like in this example.
```bash
visualize_depgraph virtual/rust -b=amd64-generic
```

If one of the packages you list is part of the dependency tree
of another one it won't be marked as a root node. Such is the case
in this example.
```bash
visualize_depgraph chromeos-base/crosvm chromeos-base/libbrillo -b=amd64-generic
```
