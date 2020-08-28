"""API to perform base functions of data traversal."""

import os
import os.path
import sys
import copy
import importlib
import importlib.util
from functools import wraps
from string import ascii_letters

from tagger import structure
from tagger import lexers
from tagger import parsers

tree = None
_saved_trees = []
registry = {}
loaders = {}
command_queue = []  # the list of current commands that needs to be executed
post_commands = []  # commands that will be executed after all of the ones
                    # in command_queue have finished (used for InCommand)
_log = {
    'unsaved_changes': False,         # the log holds information that is
    'plugin_file': None,              # meant to be accessible to plugins
    'plugin_loaded': False,           # through api.log
    'commands_loaded': False,
    'warnings_on': False,
    'alternative_plugins_dir': None,  # it will ease certain checks
    'data_source': None,
    'is_startup': False,
    'new_hooks': 0,
    'new_commands': 0,
    'new_loaders': 0,
    'importing_main_plugin': False,
    'disable_exemptions': [],
    'disabled': [],
    'disable_all': False,
    'currently_importing': None,
}
_hook_names = {
    'pre_node_creation_hook': None,  # hooks won't be registered if not in
    'post_node_creation_hook': [],   # this list
    'tag_name_hook': None,
    'tag_name_input_test': [],       # a None value means only 1 hook can be
    'tag_value_hook': None,          # registered (the main plugin file)
    'tag_value_input_test': [],
    'display_hook': None,            # an empty list means multiple plugins can
    'prompt_string': None,           # register this hook
    'inspect_commands': [],
    'inspect_post_commands': [],     # return values of multiple-function
    'capture_return': [],            # hooks will be discarded
    'startup_hook': [],
}


def _initialise_plugin():
    return structure.PluginHookDispatcher(
        copy.deepcopy(_hook_names),
        setter_hook=structure.warn_if_new('assigned to new hook name: '),
        getter_hook=structure.error_if_test(
            lambda x: x is None,
            'default hook may not have been registered as fallback: '
        )
    )


plugin = _initialise_plugin()
log = structure.NameDispatcher(
    _log, setter_hook=structure.warn_if_new('assigned to new log name: ')
)


def initialise_plugins(*, reload=False):
    """Try to load a plugin file and register command files."""
    _success = True
    config_base = None
    Hooks.pending_hooks = {}
    if log.plugin_file:
        log.importing_main_plugin = True
        _success, config_base = _import_plugin_file(_success, config_base,
                                                    reload=True)
    log.importing_main_plugin = False
    _import_other_plugins(config_base, reload=True)
    # import from default plugin directory
    if log.alternative_plugins_dir:
        _import_alt_dir_plugins(config_base)
    log.commands_loaded = True
    log.currently_importing = None
    _append_floating_hooks()
    startup_message(
        '{} command{} registered, {} loader{} registered, {} hook{} registered'
        .format(
            log.new_commands, '' if log.new_commands == 1 else 's',
            log.new_loaders, '' if log.new_loaders == 1 else 's',
            log.new_hooks, '' if log.new_hooks == 1 else 's'
        )
    )
    if not _success:
        warning(f'could not register main plugin file \'{log.plugin_file}\'')


def _import_plugin_file(_success, config_base, *, reload=False):
    """Import the plugin file from the default or alternative directory."""
    config_base = log.plugin_file.rsplit('.', 1)[0]
    log.currently_importing = os.path.basename(log.plugin_file)
    # the plugin file without the (presumed) .py extension
    try:
        name = f'tagger.plugins.{config_base}'
        if (reload and importlib.util.find_spec(name) is not None
              and name in sys.modules):
            del sys.modules[name]  # delete current version to allow reload
        importlib.import_module(name)

    except ModuleNotFoundError:
        spec = None
        if log.alternative_plugins_dir:
            try:
                d = os.path.join(log.alternative_plugins_dir,
                                 log.plugin_file)
                spec = importlib.util.spec_from_file_location(
                    config_base, d
                )
                if spec is None:
                    _success = False
                else:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[config_base] = module
                    spec.loader.exec_module(module)
            except FileNotFoundError:
                _success = False
        else:
            _success = False
    if _success:
        startup_message(f'Registered main plugin file \'{config_base}\'\n')
        log.plugin_loaded = True
    return _success, config_base


def _import_other_plugins(config_base, *, reload=False):
    """Import other plugin files from the default directory."""
    for entry in os.scandir('tagger/plugins'):
        if not entry.is_file():
            continue
        log.currently_importing = entry
        name = entry.name.rsplit('.', 1)[0]
        if name != config_base:
            module_name = f'tagger.plugins.{name}'
            if (reload and importlib.util.find_spec(module_name) is not None
                  and module_name in sys.modules):
                del sys.modules[module_name]
            try:
                importlib.import_module(module_name)
            except SyntaxError:
                if entry.name.endswith('.py'):
                    raise
                continue  # pass for non-python files
            startup_message(f'Registered plugin file \'{name}\'\n')


def _import_alt_dir_plugins(config_base):
    """Import other plugin files from the alternative directory."""
    try:
        directory = os.scandir(log.alternative_plugins_dir)
    except FileNotFoundError:
        warning('cannot find alternative plugins directory {}'.format(
            log.alternative_plugins_dir
        ))
        return
    for entry in directory:
        if not entry.is_file():
            continue
        log.currently_importing = entry
        name = entry.name.rsplit('.', 1)[0]
        if name != config_base:
            spec = importlib.util.spec_from_file_location(
                name, entry.path
            )
            if spec is not None:  # found a proper python file
                module = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                spec.loader.exec_module(module)
                startup_message(f'Registered plugin file \'{name}\'\n')


def _import_base_plugin(*, reload=False):
    """Import the default plugin file found in tagger.plugin."""
    if reload:
        del sys.modules['tagger.plugin']  # remove cache so reload occurs
    log.importing_main_plugin = True  # set to True so defaults are loaded
    importlib.import_module('tagger.plugin')
    log.importing_main_plugin = False
    startup_message('Registered default plugin hooks')
    startup_message('Registered default commands\n')


def reload_plugins(*, clean=False):
    """Reload all plugins if a plugin file was updated."""
    global registry, plugin
    plugin = _initialise_plugin()
    if clean:
        registry = {}
    log.new_commands = 0
    _import_base_plugin(reload=True)
    log.new_hooks = 0
    log.new_loaders = 0
    if tree is not None:
        log.plugin_file = tree.root.tags.get('config', log.plugin_file)
        # attempt to update the plugin config using the data tree
    initialise_plugins(reload=True)


def startup_message(message):
    """Display a message if log.is_startup is True."""
    if log.is_startup:
        print(message)


def register_hook(hook, *, single=False, default=None):
    """Register a new API hook and try to find matching functions.

    hook: hook name [str]
    single: hook only for main plugin file [bool]
    """
    hook = hook.strip()
    if hook in _hook_names:
        warning(f'hook \'{hook}\' already exists (did not overwrite)')
        return
    Hooks.pending_hooks[hook] = ([], None)[single]
    startup_message(f'created hook \'{hook}\'')
    if single and default is None:
        raise TypeError(f'no default hook for custom hook \'{hook}\'')
    Hooks.custom_hook_defaults[hook] = default


def _append_floating_hooks():
    for hook, value in Hooks.pending_hooks.items():
        plugin._dispatch_ref[hook] = value
        _hook_names[hook] = copy.copy(value)  # stop list duplicates
    remainder = []
    log.importing_main_plugin = True
    for hook, default in Hooks.custom_hook_defaults.items():
        if (hook in _hook_names
              and not isinstance(plugin._dispatch_ref.get(hook), list)):
            setattr(plugin, hook, default)
    log.importing_main_plugin = False
    for func in Hooks.floating_functions:
        if func.__name__ in _hook_names:
            if (getattr(func, '_file', None)
                  == os.path.basename(log.plugin_file)):
                log.importing_main_plugin = True
            if (not log.importing_main_plugin
                  and structure._is_single(func.__name__)):
                continue  # skip if hook is singular
            setattr(plugin, func.__name__, func)
            log.new_hooks += 1
            log.importing_main_plugin = False
            startup_message(f'Registered hook \'{func.__name__}\'')
        else:
            remainder.append(func)
    Hooks.floating_functions = remainder


def edits(func):
    """Decorator to indicate that the function modifies the data tree."""
    @wraps(func)
    def wrapper(*args, **kw):
        r = func(*args, **kw)
        log.unsaved_changes = True
        return r
    return wrapper


def priority(priority):
    """Decorator to give input handlers a .priority attribute."""
    def wrapper(func):
        func.priority = priority
        return func
    return wrapper


def may_return_none(func):
    """Decorator for input handlers that might purposefully return None."""
    func.may_return_none = True
    return func


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

    def __init__(self, root):
        """Initialise a data tree from a root object."""
        self.root = root
        self.current_node = self.root

    @classmethod
    def from_parser(cls, source):
        parser = parsers.InputPatternParser(lexers.InputLexer(source))
        root = parsers.construct_tree(parser)
        return cls(root)


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


def switch_node(node):
    """Move traversal into the given node.

    node: node to switch to [NodeType]
    return value: the previous node
    """
    current = tree.current_node
    if not is_node(node):
        raise NodeError('node is not instance of NodeType')
    tree.current_node = node
    return current


def return_from_node():
    """Move traversal back to the parent node.

    NodeError raised if current node is Root
    return value: None
    """
    if not hasattr(tree.current_node, 'parent'):
        # the root doesn't have a parent node
        raise NodeError('current node is the root of the tree')
    tree.current_node = tree.current_node.parent


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
    if not tests.not_whitespace(new):
        raise NodeError('data cannot be empty')
    node.data = new
    node.update_id()


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
        raise NodeError(f'tag \'{tag}\' not found')
    try:
        plugin.tag_name_input_test(node, tag, new_tag)
    except TypeError:
        raise NodeError(f'invalid tag name {new_tag}')
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
            raise NodeError(f'tag \'{tag}\' not found')
    if isinstance(new_value, list) and not new_value:
        new_value = None
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
    if isinstance(value, list) and not value:
        value = None
    try:
        plugin.tag_name_input_test(node, None, tag)
    except TypeError:  # don't handle NodeError so custom message not lost
        raise NodeError(f'invalid tag name {tag}')
    tag = plugin.tag_name_hook(node, tag, tag)
    try:
        plugin.tag_value_input_test(node, tag, None, value)
    except TypeError:
        raise NodeError(f'invalid tag value {value}')
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
        raise NodeError(f'tag \'{tag}\' not found')

    try:
        plugin.tag_value_input_test(node, tag, node.tags[tag], new_value)
    except TypeError:
        raise NodeError(f'invalid tag value {new_value}')
    new_value = plugin.tag_value_hook(
        node, tag, node.tags[tag], new_value
    )
    if new_value is None:
        warning('cannot append None value')
    elif isinstance(current, list):
        current.append(new_value)
    elif current is not None:
        node.tags[tag] = [current, new_value]
    elif current is None:
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
        raise NodeError(f'tag \'{tag}\' not found')


def exit():
    """Raise ProgramExit to end the CLI."""
    raise ProgramExit()


def manual_setup(data_source=None, warnings=False,
                 alternative_plugins_dir=None, alt_plugins_dir=None):
    """Manually call setup API functions.

    data_source: file to use as data_source [str <dir>]
    warnings: raise API warnings as errors [bool]
    alternative_plugins_dir: set directory in which to search
                             for plugins [str <dir>]
    alt_plugins_dir: mirror to alternative_plugins_dir (shorthand) [str <dir>]
    """
    alt_plugins_dir = alternative_plugins_dir or alt_plugins_dir
    log.warnings_on = warnings
    if data_source:
        log.data_source = os.path.abspath(data_source)
    if alt_plugins_dir:
        log.alternative_plugins_dir = os.path.abspath(alt_plugins_dir)
    _import_base_plugin()
    log.new_hooks = 0  # the previous import will change this value


def make_tree(source=None, file=None, overwrite=True):
    """Create a data tree from raw text or a file location.

    source: raw text to use to create data tree [str], or;
    file: path to text file to read [str]
    overwrite: [default=True] overwrite the current data tree if one exists
    """
    global tree
    if tree is not None and not overwrite:
        warning(
            'tree already created; use api.make_tree(source, overwrite=True) '
            'to overwrite and stop warning'
        )
    try:
        if source is None:
            if not file:
                file = log.data_source
            if not file:
                raise TypeError('no data source')
            with open(file, 'r') as f:
                source = f.read()
    except TypeError as e:
        if str(e) != 'no data source':
            raise
    else:
        tree = Tree.from_parser(source)
    log.unsaved_changes = False
    # the construction will call API functions so this must be reset to False


def run():
    """Run the traversal command line interface."""
    if tree is None:
        prev = log.is_startup
        log.is_startup = True
        initialise_plugins()  # they will not have been initialised
        # because the parser would have usually done this when constructing
        # the data tree (no source so no tree being loaded)
        log.is_startup = prev
    error_count = 0
    while True:
        try:
            if error_count > 200:
                print('More than 200 errors have occured. There may be an '
                      'issue.\nType \'continue\' to continue else exit')
                if input().strip().lower() == 'continue':
                    error_count = 0
                elif log.unsaved_changes:
                    _generate_commands('save and exit')
                    # run the save command to the default 'output.txt' and exit
                else:
                    raise ProgramExit
            prompt()
        except NodeError as e:
            error_count += 1
            print('\nError whilst executing command:', e)
        except CommandError as e:
            error_count += 1
            # raise
            print('\nError whilst processing command:', e)
        except InputError as e:
            error_count += 1
            print('\nError whilst processing input:', e)
        except SyntaxError as e:
            error_count += 1
            # raise
            print('\nError whilst parsing command:', e)
        except APIWarning as e:
            error_count += 1
            print('API Warning:', e)
        except ProgramExit:
            break
        except Exception:
            if tree is not None and log.unsaved_changes:
                log.disable_exemptions.append('save')
                # try to save data before crashing from another error
                _generate_commands('save and exit')
            raise


def prompt():
    """Read CLI input."""
    if tree is None:
        prev = log.disable_all, log.disable_exemptions, log.unsaved_changes
        log.disable_all = True
        log.disable_exemptions = ['help', 'load', 'exit', 'reload', 'set']
        log.unsaved_changes = False
        print('\nNo data tree - use the \'load\' command to load a tree')
        print(plugin.prompt_string(), end='')
        r = _generate_commands(input())
        log.disable_all, log.disable_exemptions, log.unsaved_changes = prev
    else:
        print(plugin.display_hook(tree.current_node))
        print(plugin.prompt_string(tree.current_node), end='')
        r = _generate_commands(input())
    plugin.capture_return(r)
    return r


def _generate_commands(command_str):
    """Generate commands from CLI text."""
    lexer = lexers.CLILexer(command_str)
    parser = parsers.CLIParser(lexer)
    commands = parser.generate_commands()
    plugin.inspect_commands(commands)
    print(commands, end='\n\n')
    command_queue.extend(commands)
    return_values = []
    while command_queue:
        # use while loop, because commands may add to the queue themselves
        c = command_queue.pop(0)
        return_values.append((c.ID, execute_command(c)))
    plugin.inspect_post_commands(post_commands)
    while post_commands:
        c = post_commands.pop(0)
        return_values.append((c.ID, execute_command(c)))
    print()
    return return_values


def execute_command(command):
    """Check command inputs are valid and then execute given command."""
    try:
        inputs = command.inputs  # may be an empty dict
    except AttributeError:
        raise InputError(f'no inputs given to command \'{command.ID}\'')
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
                was_none = True  # value not present
                try:
                    value = command.defaults[name]
                except KeyError:
                    fail = True  # no default given
                else:
                    fail = False
                    # escape the 'if' condition when the default value
                    # given is itself None
            if fail or not was_none:
                test = getattr(command, 'input_handler_'+name)
                value = test(value)
                if (value is None
                      and not getattr(test, 'may_return_none', False)):
                    warning(f'input handler for parameter \'{name}\' '
                            'returned None')
            inputs[name] = value
        except (NodeError, InputError) as e:
            raise InputError(str(e))
        except AttributeError:
            if was_none and value is None:
                raise CommandError('no default value given for parameter '
                    f'\'{name}\''
                )
    try:
        return command.execute(**inputs)
    except TypeError as e:
        if str(e).startswith('execute()'):
            # this should only match TypeError arising from the wrong
            # number of inputs given to the command
            raise InputError('not enough or too many inputs given to command '
                f'\'{command.ID}\''
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
        raise CommandError(f'command \'{self.ID}\' not implemented')

    def disabled(self):
        """Indicate whether a command is disabled in the current context."""
        return False

    def __init_subclass__(cls):
        if not cls.__doc__ and not cls.description:
            cls.description = ''
        elif not cls.description and cls.__doc__:
            cls.description = cls.__doc__
        if not hasattr(cls, 'ID'):
            raise CommandError(
                f'class \'{cls.__name__}\' is not bound to a command name -'
                ' no ID attribute'
            )
        registry[' '.join(cls.ID.split())] = cls
        log.new_commands += 1
        startup_message(f'Registered command \'{cls.ID}\'')

    signature = ''
    description = ''
    defaults = {}


def resolve_command(name):
    """Try to find a Command subclass which has the given registry entry.

    name: the keyword bound to the command [str]
    return value: Command subclass instance
    """
    try:
        return registry[name.lower()]()
    except KeyError:
        raise CommandError(f'unknown command \'{name}\'')


def is_disabled(command):
    """Check if a command is disabled.

    command: command instance or cubclass [Command/type]

    return: bool
    """
    if isinstance(command, type):
        command = command()  # instantiate if subclass given
    if command.ID in log.disable_exemptions:
        return False
    if log.disable_all:
        return True
    if command.ID in log.disabled:
        return True
    return command.disabled()


def child_index_from_node(node):
    try:
        for i, child in enumerate(getattr(node.parent, 'children', [])):
            if child is node:
                return i
    except AttributeError:
        raise NodeError('node is the root of the tree')


def resolve_signature(command):
    """Retrieve command signature or evaluate dynamic signature.

    command: command instance or subclass [Command/type]

    return: command's signature [str]
    """
    if isinstance(command, type):
        command = command()  # instantiate if subclass passed
    try:
        return command.signature()
    except TypeError:
        return command.signature


def fill_missing_args(command, args):
    """Try to fill in optional argument values of a command.

    command: command instance or subclass [Command/type]
    args: the arguments for the command [dict: str-any]

    1. A base dict is created by scanning the signature for inputs or flags.
    2. The dict is updated with the command's defaults if given
    3. The dict is updated with the given arguments which overwrite the
        defaults

    return: arguments with defaults filled in where possible [dict]
    """
    _lex = lexers.SignatureLexer(resolve_signature(command))
    _par = parsers.SignatureParser(_lex, command.ID)
    inputs = (parsers.CLIParser(lexers.CLILexer(''))
              .scan_for_inputs_or_flags(_par.make_signature()))
    inputs.update(command.defaults.copy())
    inputs.update(args)
    return inputs


def manual_execute(command, args):
    """Execute a command with given arguments from code rather than CLI.

    command: command name string or command instance/subclass
             [Command/type/str]
    args: the given arguments to the command [dict: str-any]

    return: return value of command (usually None) [any]
    """
    if isinstance(command, type):
        command = command()
    elif not isinstance(command, Command):  # should be a string
        command = resolve_command(command)
    command.inputs = fill_missing_args(command, args)
    return execute_command(command)


def test_input(input, message, *tests):
    """Raise an error if the test function fails.

    message: error message(s) to use [str, list:str]
    *tests: test commands to check input - each should return True to indicate
            that the test passed

    If messages is a list, a different error message will be used for each
    test whether the order of the messages should matche the order of the
    test functions.
    """
    try:
        r = 0
        for i, test in enumerate(tests):
            r = test(input)
            if r is not True:
                raise InputError
    except (NodeError, InputError, ValueError, TypeError):
        if isinstance(message, list):
            message = message[i]
        raise InputError(message)


def resolve_child(indices, node=None, offset=False):
    """Resolve a child node using a list of indices.

    indices: a list of indices to get to the child [list: int]
    node: the base node to start from [default=current node]
    offset: assume index 1 is the first index, not index 0

    The child is resolved in a way equivalent to:
    child = (node.children[indices[0]].children[indices[1]]
             .children[indices[2]].....children[indices[n]])

    return: the resolved node, otherwise IndexError raised
    """
    if offset:  # starting from 1
        new = []
        for i in indices:
            if i == 0:
                raise IndexError(str(i))
            if i > 0:
                new.append(i-1)
            else:
                new.append(i)
        indices = new
    if node is None:
        node = tree.current_node
    for i in indices:
        try:
            node = node.children[i]
        except IndexError:
            if offset and i >= 0:
                i += 1
            raise IndexError(str(i))
    return node


def compile_command(command_str, name, desc=''):
    """Return a command that executes the string as if typed into the CLI.

    command_str: the string that represents a command on the CLI
    name: the name to bind to the commannd
    desc: [optional] a description to give the command

    The .execute method of the CompiledCommand class will call
    _generate_commands(command_str) so that the string is parsed as if it
    was read from a CLI input.

    return: dynamically created CompiledCommand class
    """
    class CompiledCommand(Command):
        ID = name
        description = desc

        def execute(self):
            _generate_commands(command_str)

    return CompiledCommand


def warning(message):
    """Print a warning or raise an APIWarning.

    Output depends on log.warnings_on (APIWarning raised if True)
    """
    if log.warnings_on:
        raise APIWarning(message)
    else:
        print('API Warning:', message)


def is_node(obj):
    """Determine if an object is an instance of NodeType (Node or Root)."""
    return isinstance(obj, structure.NodeType)


class tests:
    """A collection of tests for input handlers."""

    @staticmethod
    def not_empty(input):
        """Test if input is not empty (any data type)."""
        return bool(input)

    @staticmethod
    def integer(input):
        """Test if input can be converted to an integer."""
        try:
            int(input)
        except ValueError:
            return False
        return True

    @staticmethod
    def numerical(input):
        """Test if input can be converted to float."""
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
    def whitespace(input):
        """Test if input contains only whitespace characters."""
        if not isinstance(input, str):
            return False
        return input.isspace()

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
        """Return functions to test if 0 < x <= num.

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

    is_valid_command_name = [
        lambda x: all(i[0] in (ascii_letters+'_') for i in x.split()),
        # starts with letter/underscore
        lambda x: not bool(set(x) - set(f'{ascii_letters}0123456789_ '))
        # only contains letters/numbers/underscores/
    ]

    @staticmethod
    def is_keyword(input):
        """Test if input is a valid keyword

        Characters, digits and underscores only (no leading digits)
        """
        if not isinstance(input, str):
            return False
        if len(input) == 0:
            return False
        if input[0] not in ascii_letters+'_':
            return False
        letters = f'{ascii_letters}0123456789_'
        return all(i in letters for i in input[1:])

    @staticmethod
    def is_child_reference(node):
        """Test if node is a child reference of the current node."""
        if not is_node(node):
            return False
        return getattr(node, 'parent', None) == tree.current_node

    @staticmethod
    def is_forward_reference(node):
        """Test if node is a forward reference of the current node."""
        if not is_node(node):
            return False
        return tree.current_node in node.parent_list


class Hooks:
    """Class which must be subclassed to register custom API hooks."""

    floating_functions = []
    custom_hook_defaults = {}

    def __init_subclass__(cls):
        """Initialise a subclass and register its valid hooks."""
        for k, v in cls.__dict__.items():
            if not callable(v):
                continue
            if k in _hook_names:
                if structure._is_single(k) and not log.importing_main_plugin:
                    continue
                setattr(plugin, k, v)
                log.new_hooks += 1
                startup_message(f'Registered hook \'{k}\'')
                if k == 'startup_hook':
                    v()
            else:
                v._file = log.currently_importing
                Hooks.floating_functions.append(v)


class Loader:
    """Class which must be subclassed to register custom loaders."""

    def __init_subclass__(cls):
        if not hasattr(cls, 'ID'):
            raise CommandError(
                f'class \'{cls.__name__}\' is not bound to a name -'
                ' no ID attribute'
            )
        loaders[' '.join(cls.ID.split())] = cls
        log.new_loaders += 1
        startup_message(f'Registered loader \'{cls.ID}\'')

    @staticmethod
    def found_plugin_file(file):
        """Set the plugin file and initialise plugins."""
        log.plugin_file = file
        reload_plugins()
