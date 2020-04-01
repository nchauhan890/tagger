"""Default commands for tagger API."""

import os

from tagger import api
from tagger import structure
from tagger import lexers
from tagger import parsers


class EnterCommand(api.Command):

    ID = 'enter'
    signature = 'NUMBER=index NUMBER=extra*'
    description = 'move traversal into one of the child nodes'

    def execute(self, index, extra):
        extra = extra or []
        inputs = [index, *extra]
        for i in inputs:
            api.enter_node(i - 1)  # node 1 is index 0

    def input_handler_index(self, i):
        num = len(api.tree.current_node.children)
        api.test_input(
            i, ['node index must be an integer', 'node index must be greater '
                'than 0', 'index of node must not exceed {}'.format(num)],
            api.tests.is_valid_child_index(num)
        )
        api.test_input(num, 'current node does not have any entries', bool)
        return int(i)

    def input_handler_extra(self, inputs):
        first = self.inputs['index']
        for i in inputs:
            api.test_input(
                i, 'node index must be an integer', api.tests.integer
            )
            api.test_input(
                i, 'node index must be greater than 0',
                api.tests.greater_than(0)
            )
        try:
            api.resolve_child(
                inputs, api.tree.current_node.children[first-1], offset=True
            )
        except IndexError as e:
            raise api.InputError('invalid index {}'.format(e))
        return inputs

    input_handler_index.priority = 1


class ReturnCommand(api.Command):

    ID = 'return'
    signature = 'NUMBER=depth?'
    defaults = {'depth': 1}
    description = 'return to the parent node'

    def execute(self, depth):
        if not hasattr(api.tree.current_node, 'parent'):
            raise api.NodeError('current node is the root of the tree')
        for _ in range(depth):
            api.return_from_node()

    def input_handler_depth(self, i):
        api.test_input(i, 'number of depths to return must be greater than 0',
                       api.tests.greater_than(0))
        num = len(api.tree.traversal_numbers)
        api.test_input(i, 'number of depths to return must not exceed {}'
                       .format(num), api.tests.less_equal(num))
        return i


class RemoveCommand(api.Command):

    ID = 'remove'
    signature = 'NUMBER=index?'
    defaults = {'index': None}
    description = 'remove the current node or a child node'

    def execute(self, index):
        if index is None:
            if not hasattr(api.tree.current_node, 'parent'):
                raise api.NodeError('current node is the root of the tree '
                                    'and cannot be removed')
            api.remove_node()
            return
        api.remove_node(index - 1)  # node 1 is index 0

    def input_handler_index(self, i):
        api.test_input(i, 'index of node must be an integer',
                       api.tests.integer)
        i = int(i)
        api.test_input(i, 'index of node must be greater than 0',
                   api.tests.greater_than(0))
        num = len(api.tree.current_node.children)
        api.test_input(num, 'current node does not have any entries', bool)
        api.test_input(i, 'index of node must not exceed {}'.format(num),
                   api.tests.less_equal(num))
        return i


class NewDataCommand(api.Command):

    ID = 'new data'
    defaults = {'node': None, 'position': None}
    description = 'create a new node in the current node or in a child node'

    def signature(self):
        if api.tree.current_node.children:
            return '[at NUMBER=position] [in NUMBER=node] STRING=data'
        return '[at NUMBER=position] STRING=data'

    def execute(self, position, data, node):
        if node is not None:
            node = api.tree.current_node.children[node-1]
        else:
            node = api.tree.current_node
        if position is None:
            node.children.append(api.new_node(data, parent=node))
        else:
            node.children.insert(position-1, api.new_node(data, parent=node))

    def input_handler_position(self, i):
        if self.inputs.get('node', None) is None:
            node = api.tree.current_node
        else:
            # in the child node (argument 'in')
            node = api.tree.current_node.children[self.inputs['node']]
        num = len(node.children) + 1
        # +1 because the extra one is the last non-existent index that
        # may be created
        api.test_input(
            i, ['position must be an integer', 'position must be greater '
                'than 0', 'position must not exceed {}'.format(num)],
            api.tests.is_valid_child_index(num)
        )
        return int(i)

    def input_handler_node(self, i):
        num = len(api.tree.current_node.children)
        api.test_input(
            i, ['node index must be an integer', 'node index must be greater '
                'than 0', 'index of node must not exceed {}'.format(num)],
            api.tests.is_valid_child_index(num)
        )
        return int(i)

    def input_handler_data(self, i):
        api.test_input(i, 'data cannot be empty', api.tests.not_whitespace,
                   bool)
        return i

    input_handler_node.priority = 1
    input_handler_data.priority = 2


class NewTagCommand(api.Command):

    ID = 'new tag'
    defaults = {'node': None}
    description = 'create a new tag in the current node or in a child node'

    def signature(self):
        if api.tree.current_node.children:
            return '[in NUMBER=node] STRING=name STRING=value*'
        return 'STRING=name STRING=value*'

    def execute(self, name, node, value):
        # value will be a list
        if node is not None:
            node = api.tree.current_node.children[node-1]
        else:
            node = api.tree.current_node
        if not value:
            value = None
        elif len(value) == 1:
            value = value[0]
        api.new_tag(name, value, node=node)

    def input_handler_name(self, i):
        api.test_input(i, 'name cannot be empty',
                       api.tests.not_whitespace, bool)
        return i

    def input_handler_node(self, i):
        num = len(api.tree.current_node.children)
        api.test_input(
            i, ['node index must be an integer', 'node index must be greater '
                'than 0', 'index of node must not exceed {}'.format(num)],
            api.tests.is_valid_child_index(num)
        )
        return int(i)


class RemoveTagCommand(api.Command):

    ID = 'remove tag'
    defaults = {'node': None}
    description = 'remove a tag of the current node or of a child node'

    def signature(self):
        if api.tree.current_node.children:
            return '[of NUMBER=node] STRING=tag'
        return 'STRING=tag'

    def execute(self, tag, node):
        if node is None:
            node = api.tree.current_node
        else:
            node = api.tree.current_node.children[node]
        api.remove_tag(tag, node=node)

    def input_handler_node(self, i):
        num = len(api.tree.current_node.children)
        api.test_input(
            i, ['node index must be an integer', 'node index must be greater '
                'than 0', 'index of node must not exceed {}'.format(num)],
            api.tests.is_valid_child_index(num)
        )
        return int(i)


class EditDataCommand(api.Command):

    ID = 'edit data'
    defaults = {'node': None}
    description = 'edit the data of the current node or of a child node'

    def signature(self):
        if api.tree.current_node.children:
            return '[of NUMBER=node] STRING=data'
        return 'STRING=data'


class EditTagNameCommand(api.Command):

    ID = 'edit tag name'
    defaults = {'node': None}
    description = ('edit the name of a tag of the current node or of a '
                   'child node')

    def signature(self):
        if api.tree.current_node.children:
            return '[of NUMBER=node] STRING=tag STRING=new'
        return 'STRING=tag STRING=new'


class EditTagValueCommand(api.Command):

    ID = 'edit tag value'
    defaults = {'node': None}
    description = ('edit the value of a tag of the current node or of a '
                   'child node')

    def signature(self):
        if api.tree.current_node.children:
            return '[of NUMBER=node] STRING=tag STRING=value*'
        return 'STRING=tag STRING=value*'


class AppendTagValueCommand(api.Command):

    ID = 'append tag value'
    defaults = {'node': None}
    description = ('add another item to the value of a tag of the current node'
                   ' or of a child node')

    def signature(self):
        if api.tree.current_node.children:
            return '[of NUMBER=node] STRING=tag STRING=value'
        return 'STRING=tag STRING=value'

    def execute(self, tag, value, node):
        if node is None:
            node = api.tree.current_node
        else:
            node = api.tree.current_node.children[node]
        api.append_tag_value(tag, value, node)

    def input_handler_node(self, i):
        num = len(api.tree.current_node.children)
        api.test_input(
            i, ['node index must be an integer', 'node index must be greater '
                'than 0', 'index of node must not exceed {}'.format(num)],
            api.tests.is_valid_child_index(num)
        )
        return int(i)

    def input_handler_tag(self, i):
       api.test_input(i, 'tag cannot be empty', api.tests.not_whitespace, bool)
       return i


class InCommand(api.Command):

    ID = 'in'
    signature = 'NUMBER=node NUMBER=extra*'
    description = 'execute the subsequent commands in a child node'

    def execute(self, node, extra):
        c = EnterCommand()
        c.inputs = api.fill_missing_args(c, {'index': node, 'extra': extra})
        api.command_queue.insert(0, c)  # the next one to be executed
        r = ReturnCommand()
        r.inputs = api.fill_missing_args(r, {'depth': 1})
        api.post_commands.append(r)

    def input_handler_node(self, i):
        num = len(api.tree.current_node.children)
        api.test_input(
            i, ['node index must be an integer', 'node index must be greater '
                'than 0', 'index of node must not exceed {}'.format(num)],
            api.tests.is_valid_child_index(num)
        )
        api.test_input(num, 'current node does not have any entries', bool)
        return int(i)

    def input_handler_extra(self, inputs):
        for i in inputs:
            api.test_input(
                i, 'node index must be an integer', api.tests.integer
            )
            api.test_input(
                i, 'node index must be greater than 0',
                api.tests.greater_than(0)
            )
        first = self.inputs['node']
        try:
            api.resolve_child(
                inputs, api.tree.current_node.children[first-1], offset=True
            )
        except IndexError as e:
            raise api.InputError('invalid index {}'.format(e))
        return inputs

    input_handler_node.priority = 1


class WhatCommand(api.Command):

    ID = 'what'
    signature = '<depth>|<title>|<position>|<plugin>|<commands>|<saved>'
    description = ('retrieve certain pieces of information about the '
                   'program\'s configuration or about the data tree')

    def execute(self, depth, title, position, plugin, commands, saved):
        if depth:
            n = api.tree.current_node.depth
            print('The current node is {} level{} deep'.format(
                n, 's' if n != 1 else ''
            ))
        elif title:
            print('The title of the data tree is \'{}\''.format(
                api.tree.root.data
            ))
        elif position:
            if not hasattr(api.tree.current_node, 'parent'):
                print('The current node is the root of the tree')
                return
            for i, n in enumerate(api.tree.current_node.parent.children):
                if n == api.tree.current_node:
                    print('The current node is child {} of its parent'.format(
                        i + 1
                    ))
                    break
        elif plugin:
            if api._config:
                print('The plugin file is called \'{}\''.format(api._config))
            else:
                print('There is no plugin file loaded')
        elif commands:
            print('Registered commands:')
            for i, name in enumerate(api.registry.keys()):
                print()
                if i % 4 == 3:
                    input('press enter to continue')
                kw = {'_'.join(name.split()): True}
                api.manual_execute(HelpCommand, kw)
        elif saved:
            print('There are {}unsaved changes'.format(
                'no ' if not api.unsaved_changes else ''
            ))
        else:
            raise api.InputError('no argument given')
