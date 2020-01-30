"""API to perform base functions of data traversal."""

import structure
import lexers
import parsers


tree = None
registry = {}
command_queue = []  # the list of current commands that needs to be executed
post_commands = []
# commands that will be executed after all of the ones in command_queue have
# finished (used for InCommand)


class ProgramExit(Exception):
    """Raised to quit program."""


class InputError(Exception):
    """Raised when an invalid input is given to CLI."""


class NodeError(Exception):
    """Raised for any error while viewing/modifying data."""


class CommandError(Exception):
    """Raised for any command-related error."""


class Tree:
    """Encapsulate functions to modify a data tree."""

    def __init__(self, source):
        """Initialise a data tree from a source string."""
        import parsers
        import lexers
        self.parser = parsers.InputPatternParser(lexers.InputLexer(source))
        self.root = parsers.construct_tree(self.parser)
        self.current_node = self.root
        self.traversal_numbers = []
        # [int]* : the indexes to get from the root to the current
        # by root.children[t[0]].children[t[1]].children[t[2]] etc.

    @property
    def is_root(self):
        """Return whether the current node is the root of the tree.

        return value: bool
        """
        return isinstance(self.current_node, structure.Root)

    @property
    def has_children(self):
        """Return whether the current node has any child nodes.

        return value: bool
        """
        return bool(len(self.current_node.children))

    @property
    def has_tags(self):
        """Return whether the current node is tagged.

        return value: bool
        """
        return bool(len(self.current_node.tags))

    def enter_node(self, index):
        """Move traversal into one of the children of the current node.

        index: 0 -> len(self.current_node.children)
            NodeError raised if index invalid
        return value: None
        """
        try:
            index = int(index)
        except ValueError:
            raise NodeError('index must be an integer')
        if index < 0:
            raise NodeError('index must be greater than 0')
        if index >= len(self.current_node.children):
            raise NodeError(
                'index must not exceed number of children of current node'
            )
        self.current_node = self.current_node.children[index]
        self.traversal_numbers.append(index)

    def return_from_node(self):
        """Move traversal back to the parent node.

        NodeError raised if current node is Root
        return value: the index of the node in the parent's children
        """
        if not hasattr(self.current_node, 'parent'):
            # the root doesn't have a parent node
            raise NodeError('current node is the root of the tree')
        self.current_node = self.current_node.parent
        return self.traversal_numbers.pop()

    def remove_node(self, index=None):
        """Remove the current node and return to parent."""
        if not hasattr(self.current_node, 'parent') and index is None:
            # the root doesn't have a parent node
            raise NodeError(
                'current node is root of the tree and cannot be removed'
            )
        if index is not None:
            self.enter_node(index)
        index = self.return_from_node()
        self.current_node.children.pop(index)

    def new_node(self, data, parent=None):
        """Create a new node.

        data: the data held by node
        parent: [optional] the parent of the new node
        return value: Node
        """
        import plugins.plugin as plugin
        if parent is None:
            parent = self.current_node
        data = plugin.pre_node_creation_hook(
            data, parent.depth + 1,
            parent.traversal_depth
        )
        node = structure.Node(data, parent.depth + 1, parent)
        plugin.post_node_creation_hook(node)
        return node

    def edit_tag_name(self, tag, new_tag):
        """Edit the name of one of the current node's tags.

        tag: the name of the tag to edit
        new_tag: the new name to replace with
        return value: bool
        """
        import plugins.plugin as plugin
        try:
            value = self.current_node.tags.pop(tag)
            # this will remove the current key-value pair
        except KeyError:
            raise NodeError('tag not found')
        if not plugin.tag_name_input_test(self.current_node, value, new_tag):
            raise NodeError('invalid tag name {}'.format(new_value))
        value = plugin.tag_name_hook(
            self.current_node, tag, value, new_tag
        )
        self.current_node.tags[new_tag] = value

    def edit_tag_value(self, tag, new_value):
        """Edit the value of one of the current node's tags.

        tag: the name of the tag to edit
        new_value: the new value to replace with
        return value: bool
        """
        import plugins.plugin as plugin
        try:
            self.current_node.tags[tag]
        except KeyError:
            raise NodeError('tag not found')
        if not plugin.tag_value_input_test(self.current_node, tag,
            self.current_node.tags[tag], new_value):
            raise NodeError('invalid tag value {}'.format(new_value))
        new_value = plugin.tag_value_hook(
            self.current_node, tag, self.current_node.tags[tag], new_value
        )
        self.current_node.tags[tag] = new_value


def exit():
    raise ProgramExit()


def make_tree(source, overwrite=True):
    global tree
    if not overwrite and tree is not None:
        raise NodeError(
            'tree already created; to overwrite, use api.make_tree(source, '
            'overwrite=True)'
        )
    tree = Tree(source)


def run():
    """Run the traversal command line interface."""
    while True:
        try:
            prompt()
        except NodeError as e:
            print('\nerror whilst executing command:', e, end='\n\n')
        except CommandError as e:
            print('\nerror whilst processing command:', e, end='\n\n')
        except InputError as e:
            print('\nerror whilst processing input:', e, end='\n\n')
        except SyntaxError as e:
            print('\nerror whilst parsing command:', e, end='\n\n')
        except ProgramExit:
            break


def prompt():
    """Read CLI input and execute given command(s)."""
    import plugins.plugin as plugin
    if tree is None:
        raise NodeError(
            'no data tree created: use api.make_tree(source)'
        )
    print(plugin.display_hook(tree.current_node))
    print(plugin.prompt_string(tree.current_node), end='')
    lexer = lexers.CLILexer(input())
    parser = parsers.CLIParser(lexer)
    commands = parser.generate_commands()
    print(commands, end='\n\n')
    command_queue.extend(commands)
    while command_queue:
        # use while loop, because commands may add to the queue themselves
        c = command_queue.pop(0)
        execute_command(c)
    while post_commands:
        execute_command(post_commands.pop(0))


def execute_command(command):
    """Check command inputs are valid and then execute given command."""
    try:
        inputs = command.given_inputs
    except AttributeError:
        inputs = command.inputs  # may be an empty dict
    items = sorted(
        inputs.items(),
        key=lambda x: (getattr(
            getattr(command, 'input_handler_'+x[0], lambda i: None),
            'priority', 0
            )
        ),
        reverse=True
    )
    for i, (name, value) in enumerate(items):
        test = getattr(command, 'input_handler_'+name, lambda i: value)
        try:
            inputs[name] = test(value)
        except (NodeError, InputError) as e:
            raise InputError(str(e))
    command.execute(**inputs)


class Command:
    """Produced by CLI parser to represent given traversal commands."""
    def __repr__(self):
        return '{}({})'.format(
            self.__class__.__name__,
            ', '.join('{}={}'.format(
                k, repr(v)) for k, v in self.__dict__.items()
            )
        )

    def execute(self):
        """Execute the command."""
        pass

    def __init_subclass__(cls):
        registry[cls.ID] = cls

    signature = ''


class EnterCommand(Command):

    ID = 'enter'
    signature = 'NUMBER=index NUMBER*=extra'

    def execute(self, index, extra=None):
        extra = extra or []
        inputs = [index, *extra]
        for i in inputs:
            tree.enter_node(i - 1)  # node 1 is index 0

    def input_handler_index(self, i):
        test_input(i, 'index of node must be greater than 0',
                   tests.greater_than(0))
        num = len(tree.current_node.children)
        test_input(num, 'current node does not have any entries', bool)
        test_input(i, 'index of node must not exceed {}'.format(num),
                   tests.less_equal(num))
        return i

    def input_handler_extra(self, inputs):
        return [self.input_handler_index(i) for i in inputs]


class ReturnCommand(Command):

    ID = 'return'
    signature = 'NUMBER?=depth'

    def execute(self, depth=1):
        if not hasattr(tree.current_node, 'parent'):
            raise NodeError('current node is the root of the tree')
        for _ in range(depth):
            tree.return_from_node()

    def input_handler_depth(self, i):
        test_input(i, 'number of depths to return must be greater than 0',
                   tests.greater_than(0))
        num = len(tree.traversal_numbers)
        test_input(i, 'number of depths to return must not exceed {}'
                   .format(num), tests.less_equal(num))
        return i


class RemoveCommand(Command):

    ID = 'remove'
    signature = 'NUMBER?=index'

    def execute(self, index=None):
        print(repr(index))
        if index is None:
            if not hasattr(tree.current_node, 'parent'):
                raise NodeError('current node is the root of the tree '
                                'and cannot be removed')
            tree.remove_node()
            return
        tree.remove_node(index - 1)  # node 1 is index 0

    def input_handler_index(self, i):
        test_input(i, 'index of node must be greater than 0',
                   tests.greater_than(0))
        num = len(tree.current_node.children)
        test_input(num, 'current node does not have any entries', bool)
        test_input(i, 'index of node must not exceed {}'.format(num),
                   tests.less_equal(num))
        return i


class NewDataCommand(Command):

    ID = 'new_data'
    signature = 'at NUMBER=position [in NUMBER=node] STRING=data'

    def execute(self, position, data, node=None):
        if node is not None:
            node = tree.current_node.children[node-1]
        else:
            node = tree.current_node
        node.children.insert(position-1, tree.new_node(data, parent=node))

    def input_handler_position(self, i):
        test_input(i, 'position must be greater than index 0',
                   tests.greater_than(0))
        if self.inputs.get('node', None) is None:
            node = tree.current_node
        else:
            # in the child node (argument 'in')
            node = tree.current_node.children[self.inputs['node']]
        num = len(node.children) + 1
        # +1 because the extra one is the last non-existent index that
        # may be created
        test_input(i, 'position must not exceed index {}'.format(num),
                   tests.less_equal(num))
        return i

    def input_handler_node(self, i):
        test_input(i, 'node index must be greater than 0',
                   tests.greater_than(0))
        num = len(tree.current_node.children)
        test_input(i, 'node index must not exceed {}'.format(num),
                   tests.less_equal(num))
        return i

    def input_handler_data(self, i):
        test_input(i, 'data cannot be empty', lambda x: not str.isspace(x),
                   bool)
        return i

    input_handler_node.priority = 1
    input_handler_data.priority = 2


class NewTagCommand(Command):

    ID = 'new_tag'
    signature = '[in NUMBER=node] STRING=name STRING=value'


class EditDataCommand(Command):

    ID = 'edit_data'
    signature = '[of NUMBER=node] STRING=data'


class EditTagNameCommand(Command):

    ID = 'edit_tag_name'
    signature = '[of NUMBER=node] STRING=tag STRING=new'


class EditTagValueCommand(Command):

    ID = 'edit_tag_value'
    signature = '[of NUMBER=node] STRING=tag STRING=value'


class ExitCommand(Command):

    ID = 'exit'

    def execute(self):
        print('Exiting...')
        exit()


class InCommand(Command):

    ID = 'in'
    signature = 'NUMBER=node'

    def execute(self, node):
        c = EnterCommand()
        c.given_inputs = {'index': node}
        command_queue.insert(0, c)  # the next one to be executed
        r = ReturnCommand()
        r.given_inputs = {'depth': 1}
        post_commands.append(r)


def resolve(name):
    """Try to find a CustomCommand subclass which has the given name.

    name: the keyword bound to the command [str]
    return value: CustomCommand subclass
    """
    try:
        return registry[name]
    except KeyError:
        raise CommandError('unknown command \'{}\''.format(name))


def test_input(input, message, *tests):
    """Raise an error if the test function fails."""
    try:
        if not all(test(input) for test in tests):
            raise InputError
    except (NodeError, InputError, ValueError, TypeError):
        raise InputError(message)


class tests:
    """A collection of tests for input handlers."""

    @staticmethod
    def not_empty(input):
        """Test if input is not empty (any data type)."""
        return bool(input)

    @staticmethod
    def integer(input):
        try:
            int(input)
        except ValueError:
            return False
        return True

    @staticmethod
    def numerical(input):
        try:
            float(input)
        except ValueError:
            return False
        return True

    @staticmethod
    def not_whitespace(input):
        """Test if input contains only whitespace."""
        return str(input).isspace()

    @staticmethod
    def in_range(x, y):
        """Return function to test x <= input <= y."""
        def within_range(input):
            return x <= input <= y
        return within_range

    @staticmethod
    def greater_than(x):
        """Return function to test input > x."""
        def greater(input):
            return input > x
        return greater

    @staticmethod
    def less_than(x):
        """Return function to test input < x."""
        def less(input):
            return input < x
        return less

    @staticmethod
    def greater_equal(x):
        """Return function to test input >= x."""
        def greater_eq(input):
            return input >= x
        return greater_eq

    @staticmethod
    def less_equal(x):
        """Return function to test input <= x."""
        def less_eq(input):
            return input <= x
        return less_eq
