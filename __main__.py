"""Setup and run API traversal command line interface."""

import sys
import os
import argparse

from tagger import api

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Python program to manipulate data: traverse and tag using'
            'a customisable command line tool and application programming '
            'interface',
        prog='tagger'
    )
    parser.add_argument('-d', '--data', help='data source to parse',
                        required=True)
    parser.add_argument('-p', '--plugins',
                        help='alternative location to look for plugins')
    parser.add_argument('-w', '--warnings', action='store_true',
                        help='cause warnings to be raised as errors')
    args = parser.parse_args()
    api.log.warnings_on = args.warnings
    api.log.is_startup = True
    api.log.data_source = os.path.abspath(args.data)
    if args.plugins:
        api.log.alternative_plugins_dir = os.path.abspath(args.plugins)

    with open(args.data, 'r') as f:
        content = []
        for line in f:
            if line.startswith('#'):
                break
            content.append(line)

    api.import_base_plugins()
    api._new_hooks = 0  # the previous import will change this value
    try:
        api.make_tree(''.join(content))
    except api.APIWarning as e:
        print('API Warning:', e)
    else:
        api.log.is_startup = False
        api.run()
