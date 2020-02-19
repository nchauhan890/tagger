"""Setup and run API traversal command line interface."""

import sys
import os

from tagger import api

if __name__ == '__main__':
    if not sys.argv[1:]:
        raise TypeError('no data source: use \'python -m tagger <file>\'')
    with open(sys.argv[1], 'r') as f:
        content = []
        for line in f:
            if line.startswith('#'):
                break
            content.append(line)

    api.data_source = os.path.abspath(sys.argv[1])
    api.make_tree(''.join(content))
    api.run()
