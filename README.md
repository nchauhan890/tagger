# tagger
Python program to manipulate data: traverse and tag using a customisable command line tool and application programming interface.

### Installation
To install _tagger_, follow the following steps (Windows):
  1. Download the latest _tagger_ release [here](https://github.com/nchauhan890/tagger/archive/master.zip) as a `.zip` file.
  2. Extract the `tagger-master` folder in the `.zip` file and rename to `tagger` (This folder should contain the Python files, not another sub-folder).
  3. Open Command Prompt by typing <kbd>cmd</kbd> into the Start Menu.
  4. Enter the directory which contains the `tagger` folder (by using <kbd>cd \<dir></kbd>).
  5. Now run _tagger_ using <kbd>python -m tagger</kbd> from the command line, passing the necessary arguments.

### Command line arguments
_tagger_ has the following command line options:

Option | Shorthand | Required? | Description
-|-|-|-
`--data FILE` | `-d FILE` | Yes | Data source to parse and from which create a data tree
`--plugins DIR` | `-p DIR` | No | An alternative directory in which to search for plugins
`--warnings` | `-w` | No | A flag indicating whether warnings should be raised as errors

### Example: using the sample data
_tagger_ comes with a sample data file, found in `tagger/sample_data.txt`. To run this file, type <kbd>python -m tagger -d tagger/sample_data.txt</kbd> from the command line.
