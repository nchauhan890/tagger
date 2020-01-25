"""Command Line Interface to traverse data tree."""

import api


with open('sample_data.txt', 'r') as f:
    content = []
    line = f.readline()
    while not line.startswith('#'):
        # read the sample data until '# comment' lines
        content.append(line)
        line = f.readline()


api.make_tree(''.join(content))
api.run()

