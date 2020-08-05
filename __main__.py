"""Setup and run API traversal command line interface."""

import sys
import argparse

from tagger import api

sys.setrecursionlimit(250)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Python program to manipulate data: traverse and tag using'
            'a customisable command line tool and application programming '
            'interface',
        prog='tagger',
        usage='python -m tagger [-h] -d FILE [-p DIR] [-w]',
        epilog='See https://github.com/nchauhan890/tagger for more '
            'information'
    )
    parser.add_argument('-d', '--data', help='data source to parse',
                        default=None, metavar='FILE')
    parser.add_argument('-p', '--plugins', metavar='DIR',
                        help='alternative location to look for plugins')
    parser.add_argument('-w', '--warnings', action='store_true',
                        help='cause warnings to be raised as errors')
    args = parser.parse_args()
    api.log.is_startup = True
    api.manual_setup(
        data_source=args.data, warnings=args.warnings,
        alternative_plugins_dir=args.plugins
    )
    try:
        api.make_tree()
    except api.APIWarning as e:
        print('API Warning:', e)
    else:
        api.log.is_startup = False
        api.run()
