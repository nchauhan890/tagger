"""API to perform base functions of data traversal."""

import os
import sys
import importlib
from functools import wraps

from tagger import structure
from tagger import lexers
from tagger import parsers


tree = None
registry = {}
command_queue = []  # the list of current commands that needs to be executed
post_commands = []
# commands that will be executed after all of the ones in command_queue have
# finished (used for InCommand)
_importing_commands = False
_new_hooks = 0
_new_commands = 0
_log = {
    'unsaved_changes': False,
    'plugin_file': None,
    'plugin_loaded': False,
    'warnings_on': False,
    'alternative_plugins_dir': None,
    'data_source': '',
    'is_startup': False
}
_hook_names = [
    'pre_node_creation_hook',
    'post_node_creation_hook',
    'tag_name_hook',
    'tag_name_input_test',
    'tag_value_hook',
    'tag_value_input_test',
    'display_hook',
    'prompt_string',
    'inspect_commands',
    'inspect_post_commands',
    'startup_hook',
]
hooks = dict.fromkeys(_hook_names)
plugin = structure.NameDispatcher(hooks)
log = structure.NameDispatcher(_log, warn='assigned to new log name: ')


def initialise_plugins():
    global _importing_commands
    _success = True
    config_base = log.plugin_file.rsplit('.', 1)[0]
    # the plugin file without the (presumed) .py extension
    if log.plugin_file:
        try:
            importlib.import_module('tagger.plugins.{}'
                                    .format(config_base))
        except ModuleNotFoundError:
            spec = None
            if log.alternative_plugins_dir:
                d = os.path.join(log.alternative_plugins_dir, log.plugin_file)
                spec = importlib.util.spec_from_file_location(
                    log.plugin_file, d
                )
            if spec is None:
                _success = False
            else:
                module = importlib.util.module_from_spec(spec)
                sys.modules[log.plugin_file.rsplit('.', 1)[0]] = module
                spec.loader.exec_module(module)
        if _success:
            print('Registered plugin file \'{}\'\n'.format(log.plugin_file))
            log.plugin_loaded = True
    plugin.startup_hook()  # execute even if failed as fallback is present
    _importing_commands = True
    # import from default plugin directory:
    for entry in os.scandir('tagger/plugins'):
        if entry.is_file():
            name = entry.name.rsplit('.', 1)[0]
            if name != config_base:
                importlib.import_module('tagger.plugins.{}'.format(name))
                print('Registered command file \'{}\'\n'.format(name))
    # import from alternative plugin directory:
    if log.alternative_plugins_dir:
        for entry in os.scandir(log.alternative_plugins_dir):
            if not entry.is_file():
                continue
            name = entry.name.rsplit('.', 1)[0]
            if name != config_base:
                spec = importlib.util.spec_from_file_location(
                    name, entry.path
                )
                module = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                spec.loader.exec_module(module)
                print('Registered command file \'{}\'\n'.format(name))
    _importing_commands = False
    print('{} command{} registered, {} hook{} overridden'.format(
        _new_commands, '' if _new_commands == 1 else 's',
        _new_hooks, '' if _new_hooks == 1 else 's'
    ))
    if not _success:
        warning('could not register plugin file \'{}\''
                .format(log.plugin_file))
                

def import_base_plugins():
    importlib.import_module('tagger.plugin')
    print('Registered default plugin hooks')
    print('Registered default commands\n')


def edits(func):
    @wraps(func)
    def wrapper(*args, **kw):
        r = func(*args, **kw)
        log.unsaved_changes = True
        return r
    return wrapper


class ProgramExit(Exception):
    """Raised to quit program."""


class InputError(Exception):
    """Raised when an invalid input is given to CLI."""


class NodeError(Exception):
    """Raised for any error while viewing/modifying data."""


class CommandError(Exception):
    """Raised for any command-related error."""


class APIWarning(UserWarning):
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


@edits
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


@edits
def new_node(data, parent=None):
    """Create a new node.

    data: the data held by node
    parent: [optional] the parent of the new node
    return value: Node
    """
    if parent is None:
        parent = tree.current_node
    data = plugin.pre_node_creation_hook(
        data, parent.depth + 1,
        parent.traversal_depth
    )
    if not tests.not_whitespace(data):
        raise NodeError('data cannot be empty')
    node = structure.Node(data, parent.depth + 1, parent)
    plugin.post_node_creation_hook(node)
    return node


@edits
def edit_data(new, node=None):
    """Change the data held by the current node.

    new: the new data to overwrite
    node: [optional] the node to use instead of current

    return value: None
    """
    if node is None:
        node = tree.current_node
    node.data = new
    


@edits
def edit_tag_name(tag, new_tag, node=None, create=False):
    """Edit the name of one of the current node's tags.

    tag: the name of the tag to edit
    new_tag: the new name to replace with
    node: [optional] node to use instead
    create: [optional] create a new tag if the tag doesn't exist
    """
    if node is None:
        node = tree.current_node
    try:
        value = tree.current_node.tags.pop(tag)
        # this will remove the current key-value pair
    except KeyError:
        if create:
            new_tag(new_tag, None, node)
            return
        raise NodeError('tag \'{}\' not found'.format(tag))
    if not plugin.tag_name_input_test(node, tag, new_tag):
        raise NodeError('invalid tag name {}'.format(new_tag))
    new_tag = plugin.tag_name_hook(node, tag, new_tag)
    if not tests.not_whitespace(new_tag):
        raise NodeError('tag name cannot be empty')
    node.tags[new_tag] = value


@edits
def edit_tag_value(tag, new_value, node=None, create=False):
    """Edit the value of one of the current node's tags.

    tag: the name of the tag to edit
    new_value: the new value to replace with
    node: [optional] node to use instead
    create: [optional] create a new tag if the tag doesn't exist
    """
    if node is None:
        node = tree.current_node
    try:
        node.tags[tag]
    except KeyError:
        if not create:
            raise NodeError('tag \'{}\' not found'.format(tag))
    new_tag(tag, new_value, node)


@edits
def new_tag(tag, value=None, node=None):
    """Create a new tag in the current node.

    tag: the name of the tag
    value: [optional] the value to assign
    node: [optional] node to use instead
    """
    if node is None:
        node = tree.current_node
    if not plugin.tag_name_input_test(node, None, tag):
        raise NodeError('invalid tag name {}'.format(value))
    tag = plugin.tag_name_hook(node, tag, tag)
    if not plugin.tag_value_input_test(node, tag, None, value):
        raise NodeError('invalid tag value {}'.format(value))
    value = plugin.tag_value_hook(
        node, tag, None, value
    )
    if not tests.not_whitespace(tag):
        raise NodeError('tag name cannot be empty')
    if tag in node.tags:
        warning('tag already exists')
    node.tags[tag] = value


@edits
def append_tag_value(tag, new_value, node=None, create=False):
    """Add a value to one of the current node's tags.

    tag: the name of the tag to edit
    new_value: the new value to add
    node: [optional] node to use instead
    create: [optional] create a new tag if the tag doesn't exist
    """
    if node is None:
        node = tree.current_node
    try:
        current = node.tags[tag]
    except KeyError:
        if create:
            new_tag(tag, new_value, node)
            return
        raise NodeError('tag \'{}\' not found'.format(tag))
    if not plugin.tag_value_input_test(node, tag,
        node.tags[tag], new_value):
        raise NodeError('invalid tag value {}'.format(new_value))
    new_value = plugin.tag_value_hook(
        node, tag, node.tags[tag], new_value
    )
    if new_value == None:
        warning('cannot append None value')
    elif isinstance(current, list) and new_value != None:
        current.append(new_value)
    elif current != None and new_value != None:
        node.tags[tag] = [current, new_value]
    elif current == None and new_value != None:
        node.tags[tag] = new_value
    else:
        raise NodeError('cannot append tag value')


@edits
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
        warning(
            'tree already created; use api.make_tree(source, overwrite=True) '
            'to overwrite and stop warning'
        )
    tree = Tree(source)
    log.unsaved_changes = False
    # the construction will call API functions so this must be reset to False


def run():
    """Run the traversal command line interface."""
    if tree is None:
        raise NodeError('no data tree created; use api.make_tree(source)')
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
    if tree is None:
        raise NodeError(
            'no data tree created; use api.make_tree(source)'
        )
    print(plugin.display_hook(tree.current_node))
    print(plugin.prompt_string(tree.current_node), end='')
    lexer = lexers.CLILexer(input())
    parser = parsers.CLIParser(lexer)
    commands = parser.generate_commands()
    commands = plugin.inspect_commands(commands)
    print(commands, end='\n\n')
    command_queue.extend(commands)
    while command_queue:
        # use while loop, because commands may add to the queue themselves
        c = command_queue.pop(0)
        execute_command(c)
    plugin.inspect_post_commands(post_commands)
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
    inputs = fill_missing_args(command, inputs)
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
                    value = command.defaults[name]
                except KeyError:
                    fail = True
                else:
                    fail = False
                    # escape the 'if' condition when the default value
                    # given is itself None
            if fail or not was_none:
                test = getattr(command, 'input_handler_'+name)
                value = test(value)
                if value is None:
                    print('input handler for parameter', name, 'returned None')
            inputs[name] = value
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
        raise
        if str(e).startswith('execute()'):
            # this should only match TypeError arising from the wrong
            # number of inputs given to the command
            raise InputError('not enough or too many inputs given to command '
                '\'{}\''.format(command.ID)
            )
        raise

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

    def disabled(self):
        return False

    def __init_subclass__(cls):
        global _new_commands
        if not cls.__doc__ and not cls.description:
            cls.description = ''
        elif not cls.description and cls.__doc__:
            cls.description = cls.__doc__
        registry[' '.join(cls.ID.split())] = cls
        _new_commands += 1
        print('Registered command \'{}\''.format(cls.ID))

    signature = ''
    description = ''
    defaults = {}


def resolve_command(name):
    """Try to find a Command subclass which has the given name.

    name: the keyword bound to the command [str]
    return value: Command subclass
    """
    try:
        return registry[name]()
    except KeyError:
        raise CommandError('unknown command \'{}\''.format(name))


def is_disabled(command):
    if isinstance(command, type):
        command = command()  # instantiate if subclass passed
    return command.disabled()


def resolve_signature(command):
    if isinstance(command, type):
        command = command()  # instantiate if subclass passed
    try:
        return command.signature()
    except TypeError:
        return command.signature


def fill_missing_args(command, args):
    inputs = command.defaults.copy()
    _lex = lexers.SignatureLexer(resolve_signature(command))
    _par = parsers.SignatureParser(_lex, command.ID)
    inputs.update(parsers.CLIParser(lexers.CLILexer(''))
             .scan_for_inputs_or_flags(_par.make_signature()))
    inputs.update(args)
    return inputs


def manual_execute(command, args):
    if isinstance(command, type):
        command = command()
    elif not isinstance(command, Command):  # should be a string
        command = resolve_command(command)
    command.inputs = fill_missing_args(command, args)
    return execute_command(command)


def test_input(input, message, *tests):
    """Raise an error if the test function fails."""
    try:
        r = 0
        for i, test in enumerate(tests):
            r = test(input)
            if r is not True:
                raise InputError
    except (NodeError, InputError, ValueError, TypeError) as e:
        if isinstance(message, list):
            message = message[i]
        raise InputError(message)


def resolve_child(indexes, node=None, offset=False):
    if offset:  # starting from 1
        indexes = [i-1 for i in indexes]
    if node is None:
        node = tree.current_node
    for i in indexes:
        try:
            if i < 0:  # don't allow accidental negative index
                raise IndexError()
            node = node.children[i]
        except IndexError:
            if offset:
                i += 1
            raise IndexError(str(i))
    return node


def warning(message):
    if log.warnings_on:
        raise APIWarning(message)
    else:
        print('API Warning:', message)


def is_node(node):
    return isinstance(node, (structure.Node, structure.Root))


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
        if not isinstance(input, str):
            return False
        return not input.isspace()

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
    def is_valid_child_index(num, true_index=False):
        """Return function to test if 0 < x <= num.

        num: number of children OR node whose children to use [int/Node]
        true_index: use indexes starting from 0, not 1

        return value: list of 3 tests to use (unpack) in test_input
        """
        if is_node(num):
            num = len(num.children)
        zero = 0
        if true_index:
            num -= 1
            zero = -1
        return [tests.integer, tests.greater_than(zero), tests.less_equal(num)]


class Hooks:
    def __init_subclass__(cls):
        if not _importing_commands:
            # don't import hooks except from plugin
            global _new_hooks
            for h in _hook_names:
                if hasattr(cls, h):
                    _new_hooks += 1
                    hooks[h] = getattr(cls, h)
                    # updating hooks will work with hookdispatcher as they're
                    # the same dict object
                    print('Registered hook \'{}\''.format(h))
