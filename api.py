"""API to perform base functions of data traversal."""

import os

from tagger import structure
from tagger import lexers
from tagger import parsers


tree = None
data_source = ''
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


class APIWarning(Warning):
    """Raised for API warnings."""


class Tree:
    """Hold the data tree."""
    def __init__(self, source):
        """Initialise a data tree from a source string."""
        self.parser = parsers.InputPatternParser(lexers.InputLexer(source))
        self.root = parsers.construct_tree(self.parser)
        self.current_node = self.root
        self.traversal_numbers = []
        # [int]* : the indexes to get from the root to the current
        # by root.children[t[0]].children[t[1]].children[t[2]] etc.


def enter_node(index):
    """Move traversal into one of the children of the current node.

    index: 0 -> len(tree.current_node.children)
        NodeError raised if index invalid
    return value: None
    """
    try:
        index = int(index)
    except ValueError:
        raise NodeError('index must be an integer')
    if index < 0:
        raise NodeError('index must be greater than 0')
    if index >= len(tree.current_node.children):
        raise NodeError(
            'index must not exceed number of children of current node'
        )
    tree.current_node = tree.current_node.children[index]
    tree.traversal_numbers.append(index)


def return_from_node():
    """Move traversal back to the parent node.

    NodeError raised if current node is Root
    return value: the index of the node in the parent's children
    """
    if not hasattr(tree.current_node, 'parent'):
        # the root doesn't have a parent node
        raise NodeError('current node is the root of the tree')
    tree.current_node = tree.current_node.parent
    return tree.traversal_numbers.pop()


def remove_node(index=None, node=None):
    """Remove the current node and return to parent.

    index: [optional] remove one of the child nodes instead
    node: [optional] the node whose child to remove (requires index)
    return value: the removed node
    """
    if not hasattr(tree.current_node, 'parent') and index is None:
        # the root doesn't have a parent node
        raise NodeError(
            'current node is root of the tree and cannot be removed'
        )
    if node is not None:
        if index is None:
            raise InputError('index required')
        return node.children.pop(index)
    if index is not None:
        enter_node(index)
    index = return_from_node()
    return tree.current_node.children.pop(index)


def new_node(data, parent=None):
    """Create a new node.

    data: the data held by node
    parent: [optional] the parent of the new node
    return value: Node
    """
    from tagger.plugins import plugin
    if parent is None:
        parent = tree.current_node
    data = plugin.pre_node_creation_hook(
        data, parent.depth + 1,
        parent.traversal_depth
    )
    node = structure.Node(data, parent.depth + 1, parent)
    plugin.post_node_creation_hook(node)
    return node


def edit_tag_name(tag, new_tag, node=None):
    """Edit the name of one of the current node's tags.

    tag: the name of the tag to edit
    new_tag: the new name to replace with
    node: [optional] node to use instead
    """
    if node is None:
        node = tree.current_node
    from tagger.plugins import plugin
    try:
        value = tree.current_node.tags.pop(tag)
        # this will remove the current key-value pair
    except KeyError:
        raise NodeError('tag \'{}\' not found'.format(tag))
    if not plugin.tag_name_input_test(node, value, new_tag):
        raise NodeError('invalid tag name {}'.format(new_value))
    value = plugin.tag_name_hook(node, tag, value, new_tag)
    node.tags[new_tag] = value


def edit_tag_value(tag, new_value):
    """Edit the value of one of the current node's tags.

    tag: the name of the tag to edit
    new_value: the new value to replace with
    node: [optional] node to use instead
    """
    from tagger.plugins import plugin
    if node is None:
        node = tree.current_node
    try:
        node.tags[tag]
    except KeyError:
        raise NodeError('tag \'{}\' not found'.format(tag))
    new_tag(tag, new_value)


def new_tag(tag, value=None, node=None):
    """Create a new tag in the current node.

    tag: the name of the tag
    value: [optional] the value to assign
    node: [optional] node to use instead
    """
    from tagger.plugins import plugin
    if node is None:
        node = tree.current_node
    if not plugin.tag_value_input_test(node, tag, None, value):
        raise NodeError('invalid tag value {}'.format(new_value))
    value = plugin.tag_value_hook(
        node, tag, None, value
    )
    node.tags[tag] = value


def append_tag_value(tag, new_value, node=None):
    """Add a value to one of the current node's tags.

    tag: the name of the tag to edit
    new_value: the new value to add
    node: [optional] node to use instead
    """
    from tagger.plugins import plugin
    if node is None:
        node = tree.current_node
    try:
        current = node.tags[tag]
    except KeyError:
        raise NodeError('tag \'{}\' not found'.format(tag))
    if not plugin.tag_value_input_test(node, tag,
        node.tags[tag], new_value):
        raise NodeError('invalid tag value {}'.format(new_value))
    new_value = plugin.tag_value_hook(
        node, tag, node.tags[tag], new_value
    )
    if isinstance(current, list):
        current.append(new_value)
    elif current != None or value != None:
        node.tags[tag] = [current, new_value]
    else:
        raise APIWarning('duplicate None value')


def remove_tag(tag, node=None):
    """Remove a node's tag.

    tag: the name of the tag to remove
    node: [optional] the node whose tags to search in
    return value: the value of the removed tag
    """
    if node is None:
        node = tree.current_node
    try:
        return node.tags.pop(tag)
    except KeyError:
        raise NodeError('tag \'{}\' not found'.format(tag))


def exit():
    raise ProgramExit()


def make_tree(source, overwrite=True):
    global tree
    if tree is not None and not overwrite:
        raise APIWarning(
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
            print('\nError whilst executing command:', e)
        except CommandError as e:
            # raise
            print('\nError whilst processing command:', e)
        except InputError as e:
            print('\nError whilst processing input:', e)
        except SyntaxError as e:
            # raise
            print('\nError whilst parsing command:', e)
        except APIWarning as e:
            print('API Warning:', e)
        except ProgramExit:
            break


def prompt():
    """Read CLI input and execute given command(s)."""
    from tagger.plugins import plugin
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
    print()


def execute_command(command):
    """Check command inputs are valid and then execute given command."""
    try:
        inputs = command.inputs  # may be an empty dict
    except AttributeError:
        raise InputError(
            'no inputs given to command \'{}\''.format(command.ID)
        )
    items = sorted(
        inputs.items(),
        key=lambda x: (getattr(
            getattr(command, 'input_handler_'+x[0], lambda i: None),
            'priority', 0
            )
        ),
        reverse=True
    )
    for name, value in items:
        try:
            was_none, fail = False, False
            if value is None:
                was_none = True
                try:
                    value = getattr(command, 'defaults', {})[name]
                except KeyError:
                    fail = True
                else:
                    fail = False
                    # escape the 'if' condition when the default value
                    # given is itself None
            if fail or not was_none:
                test = getattr(command, 'input_handler_'+name)
                inputs[name] = test(value)
        except (NodeError, InputError) as e:
            raise InputError(str(e))
        except AttributeError:
            if was_none and value is None:
                raise CommandError('no default value given for parameter '
                    '\'{}\''.format(name)
                )
    try:
        return command.execute(**inputs)
    except TypeError as e:
        if str(e).startswith('execute()'):
            # this should only match TypeError arising from the wrong
            # number of inputs given to the command
            raise InputError('not enough or too many inputs given to command '
                '\'{}\''.format(command.ID)
            )

class Command:
    """Produced by CLI parser to represent given traversal commands."""
    def __repr__(self):
        return '{}({})'.format(
            self.__class__.__name__,
            ', '.join('{}={}'.format(
                k, repr(v)) for k, v in self.__dict__.items()
            )
        )

    def execute(self, *args, **kw):
        """Execute the command."""
        raise CommandError('command \'{}\' not implemented'.format(
            self.ID
        ))

    @staticmethod
    def disabled():
        return False

    def __init_subclass__(cls):
        print('Registered \'{}\' command'.format(cls.ID))
        registry[' '.join(cls.ID.split())] = cls

    signature = ''


class EnterCommand(Command):

    ID = 'enter'
    signature = 'NUMBER=index NUMBER=extra*'

    def execute(self, index, extra):
        extra = extra or []
        inputs = [index, *extra]
        for i in inputs:
            enter_node(i - 1)  # node 1 is index 0

    def input_handler_index(self, i):
        num = len(tree.current_node.children)
        test_input(
            i, ['node index must be an integer', 'node index must be greater '
                'than 0', 'index of node must not exceed {}'.format(num)],
            tests.is_valid_child_index(tree.current_node)
        )
        test_input(num, 'current node does not have any entries', bool)
        return int(i)

    def input_handler_extra(self, inputs):
        return [self.input_handler_index(i) for i in inputs]


class ReturnCommand(Command):

    ID = 'return'
    signature = 'NUMBER=depth?'
    defaults = {'depth': 1}

    def execute(self, depth):
        if not hasattr(tree.current_node, 'parent'):
            raise NodeError('current node is the root of the tree')
        for _ in range(depth):
            return_from_node()

    def input_handler_depth(self, i):
        test_input(i, 'number of depths to return must be greater than 0',
                   tests.greater_than(0))
        num = len(tree.traversal_numbers)
        test_input(i, 'number of depths to return must not exceed {}'
                   .format(num), tests.less_equal(num))
        return i


class RemoveCommand(Command):

    ID = 'remove'
    signature = 'NUMBER=index?'
    defaults = {'index': None}

    def execute(self, index):
        if index is None:
            if not hasattr(tree.current_node, 'parent'):
                raise NodeError('current node is the root of the tree '
                                'and cannot be removed')
            remove_node()
            return
        remove_node(index - 1)  # node 1 is index 0

    def input_handler_index(self, i):
        test_input(i, 'index of node must be an integer', tests.integer)
        i = int(i)
        test_input(i, 'index of node must be greater than 0',
                   tests.greater_than(0))
        num = len(tree.current_node.children)
        test_input(num, 'current node does not have any entries', bool)
        test_input(i, 'index of node must not exceed {}'.format(num),
                   tests.less_equal(num))
        return i


class NewDataCommand(Command):

    ID = 'new data'
    signature = 'at NUMBER=position [in NUMBER=node] STRING=data'
    defaults = {'node': None}

    def execute(self, position, data, node):
        if node is not None:
            node = tree.current_node.children[node-1]
        else:
            node = tree.current_node
        node.children.insert(position-1, new_node(data, parent=node))

    def input_handler_position(self, i):
        if self.inputs.get('node', None) is None:
            node = tree.current_node
        else:
            # in the child node (argument 'in')
            node = tree.current_node.children[self.inputs['node']]
        num = len(node.children) + 1
        # +1 because the extra one is the last non-existent index that
        # may be created
        test_input(
            i, ['position must be an integer', 'position must be greater '
                'than 0', 'position must not exceed {}'.format(num)],
            tests.is_valid_child_index(node)
        )
        return int(i)

    def input_handler_node(self, i):
        num = len(tree.current_node.children)
        test_input(
            i, ['node index must be an integer', 'node index must be greater '
                'than 0', 'index of node must not exceed {}'.format(num)],
            tests.is_valid_child_index(tree.current_node)
        )
        return int(i)

    def input_handler_data(self, i):
        test_input(i, 'data cannot be empty', lambda x: not str.isspace(x),
                   bool)
        return i

    input_handler_node.priority = 1
    input_handler_data.priority = 2


class NewTagCommand(Command):

    ID = 'new tag'
    signature = '[in NUMBER=node] STRING=name STRING=value*'
    defaults = {'node': None}

    def execute(self, name, node, value):
        # value will be a list
        if node is not None:
            node = tree.current_node.children[node-1]
        else:
            node = tree.current_node
        new_tag(name, value, node=node)

    def input_handler_name(self, i):
        test_input(i, 'name cannot be empty', tests.not_whitespace, bool)
        return i

    def input_handler_node(self, i):
        num = len(tree.current_node.children)
        test_input(
            i, ['node index must be an integer', 'node index must be greater '
                'than 0', 'index of node must not exceed {}'.format(num)],
            tests.is_valid_child_index(tree.current_node)
        )
        return int(i)


class RemoveTagCommand(Command):

    ID = 'remove tag'
    signature = '[in NUMBER=node] STRING=tag'
    defaults = {'node': None}

    def execute(self, tag, node):
        if node is None:
            node = tree.current_node
        else:
            node = tree.current_node.children[node]
        remove_tag(tag, node=node)

    def input_handler_node(self, i):
        num = len(tree.current_node.children)
        test_input(
            i, ['node index must be an integer', 'node index must be greater '
                'than 0', 'index of node must not exceed {}'.format(num)],
            tests.is_valid_child_index(tree.current_node)
        )
        return int(i)


class EditDataCommand(Command):

    ID = 'edit data'
    signature = '[of NUMBER=node] STRING=data'


class EditTagNameCommand(Command):

    ID = 'edit tag name'
    signature = '[of NUMBER=node] STRING=tag STRING=new'


class EditTagValueCommand(Command):

    ID = 'edit tag value'
    signature = '[of NUMBER=node] STRING=tag STRING=value*'


class AppendTagValueCommand(Command):

    ID = 'append tag value'
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
        c.inputs = fill_missing_args(c, {'index': node})
        command_queue.insert(0, c)  # the next one to be executed
        r = ReturnCommand()
        r.inputs = fill_missing_args(r, {'depth': 1})
        post_commands.append(r)


class SaveCommand(Command):

    ID = 'save'

    def execute(self):
        cwd = os.path.split(data_source)[0]
        file = os.path.join(cwd, 'output.txt')
        self.depth = 0

        self.file = open(file, 'w')
        try:
            self.write_data(tree.root.data)
            author = tree.root.tags.pop('author')
            if author:
                self.write_data(author)
            desc = tree.root.tags.pop('description')
            if desc:
                self.write_data(desc)
            # write these 2 fields as data, not tags
            for i in tree.root.tags.items():
                self.write_line(self.format_tag(*i))
            for child in tree.root.children:
                self.write_line('')
                self.recursive_save(child)
        finally:
            self.file.close()
        print('Saved to {}'.format(file))

    def recursive_save(self, node):
        self.depth += 1
        self.write_data(node.data)
        self.write_tags(node.tags)
        for child in node.children:
            self.recursive_save(child)
        self.depth -= 1

    def write_tags(self, tags, single=False):
        for k, v in tags.items():
            if isinstance(v, list):
                for i in v:
                    self.write_line(self.format_tag(k, i))
                    # separate 'list' tags into multiple
            else:
                self.write_line(self.format_tag(k, v))

    def write_data(self, data):
        self.write_line(self.format_data(data))

    def format_data(self, line):
        line = line.replace('*', '\\*')
        line = line.replace('`', '\\`')
        line = line.replace('\\', '\\\\')
        return '{}{}'.format('*' * self.depth, line)

    def format_tag(self, tag, value=''):
        tag = tag.replace('*', '\\*')
        tag = tag.replace('`', '\\`')
        tag = tag.replace('=','\\=')
        tag = tag.replace('\\', '\\\\')
        if value:
            return '{}`{}={}'.format('*' * self.depth, tag, value)
        return '{}`{}'.format('*' * self.depth, tag)

    def write_line(self, line):
        self.file.write('{}\n'.format(line))


class HelpCommand(Command):

    ID = 'help'

    @staticmethod
    def signature():
        r = '[{}]'.format('|'.join('<{}>'.format(k) for k in registry.keys()))
        return r

    def execute(self, **kw):
        for k, v in kw.items():
            if v:
                command = ' '.join(k.split('_'))
                break
        else:
            command = None
        if command is None:
            print('Registered commands:')
            disabled = []
            for k, v in registry.items():
                if v.disabled():
                    disabled.append(k)
                else:
                    print('-', k)
            if not disabled:
                return
            print('\nCommands disabled in current context:')
            for k in disabled:
                print('-', k)
        else:
            c = resolve(command)
            # don't catch error, it will have the correct message already
            signature = resolve_signature(c)
            print('Help on command \'{}\':\n'.format(c.ID))
            if signature:
                print('- signature:', ' '.join(signature.split()))
                # this removes double
            _lexer = lexers.SignatureLexer(signature)
            _parser = parsers.SignatureParser(_lexer, c.ID)
            _sig_parts = _parser.make_signature()
            print('- syntax:', c.ID, ' '.join([
                self.signature_syntax(s) for s in _sig_parts
            ]))
            if c.disabled():
                print('- disabled in current context')

    def signature_syntax(self, signature):
        if isinstance(signature, structure.OptionalPhrase):
            return '[{}]'.format(' '.join([
                self.signature_syntax(x) for x in signature.parts
            ]))
        if isinstance(signature, structure.Phrase):
            if len(signature.parts) == 1:
                return self.signature_syntax(parts[0])
            return '({})'.format(' '.join([
                self.signature_syntax(x) for x in signature.parts
            ]))
        if isinstance(signature, structure.End):
            return ''
        if isinstance(signature, structure.Optional):
            return '{}?'.format(self.signature_syntax(signature.pattern))
        if isinstance(signature, structure.Variable):
            return '{}*'.format(self.signature_syntax(signature.pattern))
        if isinstance(signature, structure.Keyword):
            return signature.value
        if isinstance(signature, structure.Flag):
            return '<{}>'.format(signature.value)
        if isinstance(signature, structure.Or):
            return '({})'.format(' | '.join([
                self.signature_syntax(x) for x in signature.parts
            ]))
        if isinstance(signature, structure.Input):
            if signature.type == lexers.NUMBER:
                return 'n'
            if signature.type == lexers.STRING:
                return '\'{}\''.format(signature.argument)
        return str(signature.value)


def resolve(name):
    """Try to find a Command subclass which has the given name.

    name: the keyword bound to the command [str]
    return value: Command subclass
    """
    try:
        return registry[name]
    except KeyError:
        raise CommandError('unknown command \'{}\''.format(name))


def resolve_signature(command):
    try:
        return command.signature()
    except TypeError:
        return command.signature


def fill_missing_args(command, args):
    _lex = lexers.SignatureLexer(resolve_signature(command))
    _par = parsers.SignatureParser(_lex, command.ID)
    inputs = (parsers.CLIParser(lexers.CLILexer(''))
             .scan_for_inputs_or_flags(_par.make_signature()))
    inputs.update(args)
    return inputs


def manual_execute(command, args):
    if issubclass(command, Command):
        command = command()
    elif not isinstance(command, Command):  # should be a string
        command = resolve(command)
    command.inputs = fill_missing_args(command, args)
    return execute_command(command)


def test_input(input, message, *tests):
    """Raise an error if the test function fails."""
    try:
        r = 0
        for test in tests:
            r = test(input)
            if r is not True:
                raise InputError
    except (NodeError, InputError, ValueError, TypeError) as e:
        if isinstance(message, list):
            message = message[r]
        raise InputError(message)


def resolve_child(indexes, node=None, offset=False):
    if offest:
        indexes = [i-1 for i in indexes]
    if node is None:
        node = tree.current_node
    for i in indexes:
        if i < 0:
            raise IndexError(str(i))  # don't allow accidental negative index
        node = node.children[i]
    return node


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
        """Test if input contains characters other than whitespace."""
        return not str(input).isspace()

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

    @staticmethod
    def is_valid_child_index(node, true_index=False):
        """Return function to test if x is a valid index of child node."""
        def valid_child_index(x):
            num, zero = len(node.children), 0
            if true_index:
                num -= 1
                zero = -1
            if not tests.integer(x):
                return 0
            if not tests.greater_than(zero)(x):
                return 1
            if not tests.less_equal(num)(x):
                return 2
            return True
        return valid_child_index
