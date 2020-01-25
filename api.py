"""API to perform base functions of data traversal."""

import weakref

import structure
import lexers
import parsers

tree = None
registry = weakref.WeakValueDictionary()
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
        if not hasattr(self.current_node, 'parent'):
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
        if parent is None:
            parent = self.current_node
        node = structure.Node(
            data, parent.depth + 1, parent
        )

    def edit_tag_name(self, tag, new_tag):
        """Edit the name of one of the current node's tags.

        tag: the name of the tag to edit
        new_tag: the new name to replace with
        return value: bool
        """
        try:
            value = self.current_node.tags.pop(tag)
            # this will remove the current key-value pair
        except KeyError:
            raise NodeError('tag not found')
        self.current_node.tags[new_tag] = value

    def edit_tag_value(self, tag, new_value):
        """Edit the value of one of the current node's tags.

        tag: the name of the tag to edit
        new_value: the new value to replace with
        return value: bool
        """
        try:
            self.current_node.tags[tag]
        except KeyError:
            raise NodeError('tag not found')
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
    import plugin
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
    for i, (name, value) in enumerate(inputs.items()):
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
        try:
            i = int(i)
        except ValueError:
            raise InputError('input must be a number')
        if i < 1:
            raise NodeError(
                'index of node must be greater than 0'
            )
        num = len(tree.current_node.children)
        if not num:
            raise NodeError(
                'current node does not have any entries'
            )
        if i > num:
            raise NodeError(
                'index of node must not exceed {}'.format(num)
            )
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
        try:
            i = int(i)
        except ValueError:
            raise InputError(
                'number of depths to return must be an integer'
            )
        return i


class RemoveCommand(Command):

    ID = 'remove'
    signature = 'NUMBER?=index'

    def execute(self, index=None):
        if self.number is None and not hasattr(tree.current_node, 'parent'):
            raise NodeError(
                'current node is the root of the tree and cannot be removed'
            )
        if self.number is None:
            tree.remove_node()
            return
        if self.number < 1:
            raise NodeError('index of node must be greater than 0')
        num = len(tree.current_node.children)
        if not num:
            raise NodeError('current node does not have any entries')
        if self.number > num:
            raise NodeError(
                'index of node must not exceed {}'.format(num)
            )
        tree.remove_node(self.number - 1)  # node 1 is index 0


class NewDataCommand(Command):

    ID = 'new_data'
    signature = 'at NUMBER=position [in NUMBER=node] STRING=data'


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
        print('Exiting...')  # add 'do you want to save?'
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


class CustomCommand(Command):
    def __init_subclass__(cls):
        registry[cls.ID] = cls


def resolve(name):
    """Try to find a CustomCommand subclass which has the given name.

    name: the keyword bound to the command [str]
    return value: CustomCommand subclass
    """
    try:
        return registry[name]
    except KeyError:
        raise CommandError('unknown command \'{}\''.format(name))
