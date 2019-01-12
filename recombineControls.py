#!/usr/bin/env python3

# Recombine the YAML output files generated by parseCsvControls.py
# and output a Markdown system security plan.
#
# Usage:
# python3 recombineControls.py -c components > ssp.md
# python3 recombineControls.py > ssp.md
# NOTE: default components directory is "components"
#
# (Include control descriptions with each control)
# python3 recombineControls.py -d -c components > ssp.md
#
# Generate different types of docs
# pandoc -t html < ssp.md > ssp.html
# pandoc -t docx ssp.md -o ssp.docx

import collections
import glob
import os
import os.path
import rtyaml
import sys
from argparse import ArgumentParser
import re

# Parse for optionally including control description from standard
parser = ArgumentParser(description="Combine component controls into a simple SSP")
parser.add_argument("-d", "--description", action="store_true", dest="include_descriptions", default=False,
                    help="include control descriptions")
parser.add_argument("-c", "--components", dest="components_dir", default="components",
                    help="set components directory")
parser.add_argument("-f", "--family", dest="family",
                    help="include only controls for the given family (e.g. AC, SI)")
parser.add_argument("-s", "--separate", dest="separate",
                    help="output each control family to separate files in the given directory")
args = parser.parse_args()

# Ensure the passed argument is a directory that exists.
# components_dir = sys.argv[1]
components_dir = args.components_dir
include_descriptions = args.include_descriptions
only_family = args.family
separate_by_family_output_dir = args.separate

if not os.path.isdir(components_dir):
  print("Can't find directory:", components_dir)
  sys.exit()

components_glob = components_dir.rstrip('/') + "/*"

# The map component directory names back to long names. Use an
# OrderedDict to maintain a preferred component order.
component_names = collections.OrderedDict([
  (None, None),
  ("LINCS",        "LINCS specific control or LINCS Responsibility"),
  ("CivicActions", "CivicActions Responsibility"),
  ("Drupal",       "Drupal specific control support"),
  ("AWS",          "Amazon Web Services (AWS) US-East/West control support"),
])
component_order = { component: i for i, component in enumerate(component_names) }

# Store all the controls from NIST 800-53 rev4 standard
# TODO: Shocked, shocked I am to see hardcoding a path and file.
standard_controls_dir = "standards"
standard_file = "nist-sp-800-53-rev4.yaml"

# Read in all the controls
with open(os.path.join(standard_controls_dir, standard_file)) as f:
  standard_controls_data = rtyaml.load(f)

# Store all of the parts of an SSP.
ssp = []

# Read in all of the components' control implementation texts.
for component_dir in glob.glob(components_glob):
  for control_family_fn in glob.glob(os.path.join(component_dir, "*.yaml")):
    with open(control_family_fn) as f:
      component_controlfam_data = rtyaml.load(f)

      # Read out each control and store it in memory as a tuple
      # that holds the information we need to sort all of the
      # items into the right order for the SSP.
      for control in component_controlfam_data["satisfies"]:
        # Skip controls that are in a different family than the one given on the
        # command line.
        control_family = control["control_key"].split("-")[0]
        if only_family and control_family != only_family:
          continue

        # Prepare control description text and fix spacing before parenthesis for subcontrols
        # TODO: clean up this regex, but it works.
        control_id = control["control_key"].replace("-0", "-")
        matchObj = re.match( r'([^ (]*)\s*(\(.*)', control_id )
        if matchObj:
          url_id = matchObj.group(1)
          control_id = url_id + ' ' + matchObj.group(2)
        else:
          url_id = control_id

        if include_descriptions:
          control.setdefault("control_description",
                             standard_controls_data[control_id]["description"] + "\n\n" +
                             "_(<http://800-53.govready.com/control?id=" + url_id + ">)_" + "\n\n" +
                             "Security control type: " + control["security_control_type"])
        else:
          control.setdefault("control_description",
                             "Control description: " +
                             "<http://800-53.govready.com/control?id=" + url_id + ">" + "\n\n" +
                             "Security control type: " + control["security_control_type"])

        ssp.append((
          control_family, # code
          component_controlfam_data["family"], # name
          control["control_key"],
          control["control_name"],
          control["control_key_part"] or "",
          component_order[component_controlfam_data["name"]],
          component_names[component_controlfam_data["name"]],
          control["narrative"],
          control["control_description"],
        ))

# Sort the SSP items.
# We've conveniently put them in as tuples that will sort to
# the right order they should appear in an SSP.
ssp.sort()

# Helpers
def plain_text_to_markdown(s):
  # Paragraphs need two newlines in Markdown.
  s = s.replace("\n", "\n\n")
  s = s.replace("•", "*")
  return s
def blockquote(s):
        return "\n".join(("> " + line) for line in s.strip().split("\n")) + "\n"

def write_ssp(file, ssp):
  current_control_family = None
  current_control = None
  current_part = None
  for control_family, control_family_name, control_key, control_name, part, component_order, component_name, narrative, control_descr in ssp:
    if control_family_name != current_control_family:
      print("# " + control_family_name, file=file)
      print(file=file)
      current_control_family = control_family_name
      current_control = None
      current_part = None
    if control_key != current_control:
      print("## " + control_key + " " + control_name, file=file)
      print(file=file)
      print(blockquote(plain_text_to_markdown(control_descr)), file=file)
      print(file=file)
      current_control = control_key
      current_part = None
    if part != current_part:
      if part: # there are null parts meaning the whole control, not a part
        print("### Part " + part + ")", file=file)
        print(file=file)
      current_part = part

    if component_name:
      print("#### " + component_name, file=file)
      print(file=file)

    # Convert plain text narrative to Markdown as best as we can quickly.
    narrative = plain_text_to_markdown(narrative)

    print(narrative, file=file)
    print(file=file)

if separate_by_family_output_dir is None:
  # Write the SSP to standard output.
  write_ssp(sys.stdout, ssp)
else:
  # Write each family to a separate output file.
  if not os.path.exists(separate_by_family_output_dir):
    os.mkdir(separate_by_family_output_dir)
  control_families = set(control[0] for control in ssp)
  for control_family in control_families:
    with open(os.path.join(separate_by_family_output_dir, control_family + ".md"), "w") as f:
      write_ssp(f, [control for control in ssp if control[0] == control_family])
