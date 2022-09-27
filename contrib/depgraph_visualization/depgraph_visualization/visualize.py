# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Helper classes and functions for depgraph visualization.

Here is the pyvis documentation
https://pyvis.readthedocs.io/en/latest/documentation.html
"""

from typing import Dict, Iterator, List, Set, Tuple
import matplotlib.pyplot as plt # pylint: disable=import-error


class PackageNode(object):
  """Helper struct for the DepVisualizer class.

  This struct makes it easier to traverse a directed graph while
  retaining it's properties.
  Variables are yielded to improve runtime and memory usage.
  """

  def __init__(self, pkg_name: str):
    self.name = pkg_name
    # List of child PackageNodes.
    self.dependencies = []
    # List of parent PackageNodes.
    self.rvs_dependencies = []

  def AddDependency(self, dependency: 'PackageNode'):
    self.dependencies.append(dependency)

  def AddRvsDependency(self, rvs_dependency: 'PackageNode'):
    self.rvs_dependencies.append(rvs_dependency)

  def GetDependencies(self):
    yield from self.dependencies

  def GetRvsDependencies(self):
    yield from self.rvs_dependencies


class DepVisualizer(object):
  """Process dependency information into visualizable data.

  Typical usage:
    dep_vis = DepVisualizer(dep_tree)
    dep_vis.VisualizeGraph()
  """

  def __init__(self, dep_tree: Dict[str, List[str]]):
    """Dependency Visualizer init.

    Args:
      dep_tree: A dictionary were package names
                mapped to their runtime dependency list.
    """
    # For purposes of speed and simplicity the dependency nodes are
    # tracked using a dictionary where the key is the name of the
    # package and the value is its PackageNode instance.
    self.pkg_dict = {}
    for pkg, deps in dep_tree.items():
      self.AddNode(pkg, deps)

  def AddNode(self,
              pkg_name: str,
              pkg_dependencies: List[str]):
    """Add a package and its dependencies to the package dictionary.

    Create an instance of PackageNode for both the pkg and its
    dependencies -making sure not to duplicate any- and add
    them to pkg_dict.

    Args:
      pkg_name: the name of a package.
      pkg_dependencies: list of the names of the package's dependency.
    """
    pkg_node = self.pkg_dict.setdefault(pkg_name, PackageNode(pkg_name))
    for dependency in pkg_dependencies:
      dep_node = self.pkg_dict.setdefault(dependency, PackageNode(dependency))
      pkg_node.AddDependency(dep_node)
      dep_node.AddRvsDependency(pkg_node)

  def CalculateRoots(self) -> Iterator[PackageNode]:
    """Determine which nodes are roots and return them in a List.

    In this context a root node is one that no other depends on, in
    other words those nodes with no reverse dependencies.

    Returns:
      A generator of PackageNodes.
    """
    return (x for x in self.pkg_dict.values() if not x.rvs_dependencies)

  def VisualizeGraph(self, output_name='DepGraph', output_dir='.'):
    """Create a HTML file with the visualization of the dependency graph.

    Pyvis helps us create a HTML file with all the packages and their
    relationships in a timely manner; average execution time for this function
    is 2-3 seconds (in a cloud top instance).
    The resulting HTML file by default is named 'DepGraph'
    and is written in the current directory of this file.

    Args:
      output_name: Name of the output HTML file.
      output_dir: Directory of the output HTML file.
    """
    import pyvis # pylint: disable=import-error
    net = pyvis.network.Network(height='720px', width='60%', directed=True,
                                bgcolor='#272727', font_color='#ffffff',
                                heading='')
    roots = self.CalculateRoots()
    # queue is a list of iterators that yield node dependencies.
    queue = []
    # Set of seen packages to avoid getting stuck in cycles.
    seen_pkgs = set()

    # Populate the network with initial root nodes
    # and prepare the queue for the BFS traversal.
    for root in roots:
      seen_pkgs.add(root.name)
      queue.append(root.GetDependencies())
      net.add_node(root.name, shape='star', color='red', mass=1)

    # This function (only) adds the nodes in the graph using a BFS traversal.
    # It also colors nodes in shades of green and blue depending
    # on their depth level.
    _BfsColoring(net, queue, seen_pkgs)

    # We add the edges after adding the nodes because Pyvis is
    # optimized this way.
    for pkg, node in self.pkg_dict.items():
      # In Pyvis you add directed edges by passing a list of lists with the
      # name of the parent and child.
      net.add_edges([pkg, child.name] for child in node.GetDependencies())

    # force_atlas_2based is a mathematical model to calculate
    # particle (nodes in our case) distribution in a 2D plane.
    net.force_atlas_2based(gravity=-200, damping=1)

    # Displays fun physics options to play around.
    # Here is the documentation for this function.
    # https://pyvis.readthedocs.io/en/latest/_modules/pyvis/network.html#Network.show_buttons
    net.show_buttons(filter_=['physics'])
    # Writes an HTML file with the graph on it.
    net.write_html(f'{output_dir}/{output_name}.html')

  def GenerateHistograms(self, build_name: str, path: str):
    """Creates 4 histograms with dependency and rvs dependency distribution.

    The amount of packages with a certain range of dependencies and
    reverse dependencies ranges from 600 to 1 so we split the histograms
    of both into two; giving us four in total.

    Args:
      build_name: Name of the target build
      path: Path to output files.
    """
    # Prepare data to plot.
    dep_count = [len(n.dependencies) for n in self.pkg_dict.values()]
    # There isn't a good explanation for the values of the bins other than
    # they yield a good result.
    dep_bins_low = [0, 1, 3, 5, 9, 13, 17, 20]
    # The bigger bins start from 21 and go on multiples of 50
    # until the highest value of the data points.
    highest_dep = max(dep_count)
    top = (highest_dep // 50)+1
    dep_bins_high = [21] + [i*50 for i in range(1, top)] + [highest_dep]

    # The histogram gets created and saved.
    _SaveHistogram(dep_count,
                   dep_bins_low,
                   f'({build_name}): Dependency_distribution_low',
                   path,
                   '#205973')

    _SaveHistogram(dep_count,
                   dep_bins_high,
                   f'({build_name}): Dependency_distribution_high',
                   path,
                   '#205973')

    # Do the same for the reverse dependencies.
    rvs_count = [len(n.rvs_dependencies) for n in self.pkg_dict.values()]
    rvs_bins_low = [1, 2, 10, 20]
    highest_rvs = max(rvs_count)
    top = (highest_rvs // 50)+1
    rvs_bins_high = [21] + [i*50 for i in range(1, top)] + [highest_rvs]

    _SaveHistogram(rvs_count,
                   rvs_bins_low,
                   f'({build_name}): Reverse_Dependency_distribution_low',
                   path,
                   '#ef7e56')

    _SaveHistogram(rvs_count,
                   rvs_bins_high,
                   f'({build_name}): Reverse_Dependency_distribution_high',
                   path,
                   '#ef7e56')


def _SaveHistogram(data: List[int],
                   bins: List[int],
                   name: str,
                   path: str,
                   color: str):
  """Streamline the process of plotting histograms.

  Plots and saves a histogram as a png file.

  Args:
    data: List with data points.
    bins: List with ranges for the histogram.
    name: Name of the output file.
    path: Path of the output file.
    color: Color in either rgb or hexadecimal format.
  """

  plt.hist(data,
           bins=bins,
           edgecolor='black',
           color=[color])

  # Location for the labels in the x-ticks.
  xplace = [(a+b) // 2 for a, b in zip(bins[:-1], bins[1:])]
  # Create labels accurately portraying bin ranges.
  xlabels = [f'{a}-{b-1}' for a, b in zip(bins[:-2], bins[1:-1])]
  # Last range is inclusive.
  xlabels += [f'{bins[-2]}-{bins[-1]}']
  plt.xticks(xplace, xlabels)

  plt.ylabel('Number of Packages')
  plt.title(name)
  plt.savefig(f'{path}/{name}.png')
  # The plot needs to be cleaned otherwise all the graphs clump together.
  plt.clf()


def _BfsColoring(net,
                 queue: List[Iterator[PackageNode]],
                 seen_pkgs: Set[str]):
  """Coloring the graph in by using BFS.

  This function will populate a pyvis.network.Network object and
  color it by layers to create a contrast between near and deep nodes.
  Correct type hitting to be added for 'net'.

  Args:
    net: pyvis.network.Network instance.
    queue: List of generators that yield PackageNodes.
    seen_pkgs: Name set of all visited packages.
  """
  green = 255
  blue = 0
  color = 'rgb(0,255,0)'
  while queue:
    next_queue = []

    for dep_gen in queue:
      for node in dep_gen:
        if node.name in seen_pkgs:
          continue
        # Setup for next level.
        seen_pkgs.add(node.name)
        next_queue.append(node.GetDependencies())

        # Vertex degree is the number of connections a node has.
        vertex_degree = len(node.rvs_dependencies)+len(node.dependencies)
        # Give nodes custom format based on their vertex degree.
        # The most connected nodes have at most 200+ edges and at least 20.
        # 13% of all nodes have 50% of all dependencies
        # and 3% have 50% of all reverse dependencies.
        mass = 3 if vertex_degree >= 20 else 1
        shade = '#effffb' if vertex_degree >= 20 else color
        shape = 'diamond' if vertex_degree >= 20 else 'dot'
        net.add_node(node.name, color=shade, mass=mass, shape=shape)

    queue = next_queue
    color, green, blue = _RgbColorGrade(green, blue)


def _RgbColorGrade(green: int, blue: int, rate=51) -> Tuple[str, int, int]:
  """Calculate a shade of color in between green and blue.

  In order to make the graph more user-friendly and insightful this simple
  color grading technique makes it clear which nodes are deeper in the graph
  (green being closer and blue deeper).
  The rate of change for the color is 51 because it is a factor of 255 and
  most importantly the average depth of the whole graph and any highly
  connected node is 9-11 where most of the nodes reside in the middle levels
  thus a high rate creates a good contrast between near and deep nodes.

  Args:
    green: int value between [0, 255] for the green component.
    blue: int value between [0, 255] for the blue component.
    rate: rate of change between shades of green and blue.

  Returns:
    A tuple of three values, the first being a RGB formatted string color,
    the second the next value for the green component, and third the next
    value for the blue component.
  """

  if green not in range(0, 256): # pylint: disable=range-builtin-not-iterating
    raise ValueError(f'green({green}) must be in [0, 255]')
  if blue not in range(0, 256): # pylint: disable=range-builtin-not-iterating
    raise ValueError(f'blue({blue}) must be in [0, 255]')

  green = max(green - rate, 0)
  blue = min(blue + rate, 255)
  return f'rgb(0,{green},{blue})', green, blue
