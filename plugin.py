"""Plugin for API execution hooks and custom commands."""

import os

from tagger import api
from tagger import structure
from tagger import lexers
from tagger import parsers


class Hooks(api.Hooks):
    def pre_node_creation_hook(data, depth, parents):
        """Edit data to node before creation.

        data: name of node or data held by node [str]
        depth: how many levels deep the node is [int]
        parents: the list of parents from top to bottom [Node]*
                 (includes the root node)

        return value: data to be held by node
        """
        return data

    def post_node_creation_hook(node):
        """Edit attribute of node after creation.

        node: the node that is edited [Node]

        return value: None
        """
        pass

    def tag_name_hook(node, old, new):
        """Edit new/existing tag name before being assigned.

        node: the node whose tag is being edited [Node]
        old: the current/old name of the tag being edited [str]
        new: the new name of the tag [str]

        return value: new name for tag
        """
        return new

    def tag_name_input_test(node, old, new):
        """Check whether the given input for a tag name is acceptable.

        node: the node whose tag is being edited [Node]
        old: the current/old name of the tag being edited [str]
        new: the new name of the tag [str]

        return value: None
        (raise TypeError to indicate invalid name, or NodeError to use
         a custom message)
        """
        return True

    def tag_value_hook(node, tag, old, new):
        """Edit value assigned to new/existing tag.

        node: the node whose tag is being edited [Node]
        tag: the name of the tag being edited [str]
        old: the current/old value of the tag [ANY]
        new: the new value of the tag [str]

        return value: new value for tag
        """
        return new

    def tag_value_input_test(node, tag, old, new):
        """Check whether the given input for a tag value is acceptable.

        node: the node whose tag is being edited [Node]
        tag: the name of the tag being edited [str]
        old: the current/old value of the tag [ANY]
        new: the new value of the tag [str]

        return value: None
        (raise TypeError to indicate invalid value, or NodeError to use
         a custom message)
        """
        return True

    def display_hook(current):
        """Customise the display upon prompt for command

        current: the current node [Node]

        return value: a string to display [str]
        """
        string = '\n[~'
        for node in api.tree.current_node.traversal_depth[1:]:
            string += '/' + node.id
            # display current node reference
        string += ']'
        # --- display the current node ---
        traversal = iter(current.traversal_depth)
        string = '\n'.join([string, next(traversal).data])  # the root's data
        for i, node in enumerate(traversal, start=1):
            string = '\n'.join([
                string,
                '{}in {}'.format(
                    '  ' * i,
                    node.data
                )
            ])

        i = len(current.traversal_depth)
        # --- display the current node's tags ---
        for k, v in current.tags.items():
            if v is None:
                string = '\n'.join([string, '{}• {}'.format('  ' * i, k)])
            else:
                if isinstance(v, list):
                    v = v.copy()
                    string = '\n'.join([string, '{}• {}: '.format('  ' * i, k)])
                    if v:
                        string = ''.join([string, str(v.pop(0)) + ','])
                        while v:
                            string = '\n'.join([
                                string,
                                '{}  {}  {},'.format('  ' * i, ' ' * len(k),
                                                     v.pop(0))
                            ])
                        string = string[:-1]  # remove last comma
                else:
                    string = '\n'.join([string, '{}• {}: {}'
                                        .format('  ' * i, k, v)])

        if current.children:
            string = '\n'.join([
                string,
                '{}Entries:'.format('  ' * (i - 1))
            ])

            # --- display the current node's child entries ---
            longest = max(len(str(len(current.children)))+1, (i*2)+1)
            # this will either indent using the current (depth * 2) or, if the
            # numbers of child entries is so long the last digits won't fit,
            # the greatest number of digits
            # len(str(len(x))) gives the number of digits in len(x)
            for j, node in enumerate(current.children, start=1):
                string = '\n'.join([string, '{} {}'.format(
                        r'{:>{}}'.format(j, longest), node.data)]
                )

        else:
            string = '\n'.join([string, '{}No Entries'.format('  ' * (i - 1))])

        return string

    def prompt_string(current=None):
        """Return the prompt string for CLI.

        current: the current node (or None if not in a data tree) [Node]

        return value: a string for the CLI prompt [str]
        """
        if current is None:
            return '> '
        return '>>> '

    def inspect_commands(commands):
        """Inspect/modify the commands about to be executed.

        commands: list of commands [Command]

        return value: None (modifications should be made in-place to list)
        """
        pass

    def inspect_post_commands(commands):
        """Inspect/modify the commands in the post_commands queue.

        commands: list of commands [Command]

        return value: None (modifications should be made in-place to list)
        """
        pass

    def capture_return(return_values):
        """Capture the return values of commands executed in each loop.

        return_values: a list of tuples in the form (ID, return_value)
                       for each command that run

        return value: None
        """
        return None

    def startup_hook():
        """Execute code as soon as the plugin is registered.

        return value: None
        """
        pass


class ExitCommand(api.Command):
    """Command to exit the program."""

    ID = 'exit'
    description = 'exit the program'

    def signature(self):
        if api.tree is None:
            return ''
        return '<and return> <without saving>'

    def execute(self, **kw):
        without_saving = kw.get('without_saving', False)
        and_return = kw.get('and_return', False)
        if api.log.unsaved_changes and not without_saving:
            print('There are unsaved changes to the data tree')
            return
        if not without_saving:
            print('Are you sure? Type \'yes\' to confirm')
            v = input().lower().strip()
        else:
            v = 'yes'
        if v == 'yes':
            if and_return:
                api.tree = None
            else:
                api.exit()


class SaveCommand(api.Command):
    """Command to save data tree to output file."""

    ID = 'save'
    signature = '[as STRING=name|<current>] <and exit> [using STRING=loader]'
    defaults = {'name': None, 'loader': 'default'}
    description = 'save the data tree to a file'

    def execute(self, name, current, and_exit, loader):
        cwd = os.path.split(api.log.data_source)[0]
        if name is None and not current:
            file = 'output.txt'
            if file in os.listdir(cwd):
                i = 1
                file = 'output_{}.txt'.format(i)
                while file in os.listdir(cwd):
                    i += 1
                    file = 'output_{}.txt'.format(i)
            file = os.path.join(cwd, file)
        else:
            if current:
                name = os.path.basename(api.log.data_source)
            if name in os.listdir(cwd):
                print('File already exists - do you want to overwrite?')
                r = input('Type \'yes\' to overwrite\n').strip().lower()
                if r != 'yes':
                    return
            file = os.path.join(cwd, name)

        try:
            loader = api.loaders[loader]()
        except KeyError:
            raise api.CommandError(f'no loader \'{loader}\'')
        if not hasattr(loader, 'save'):
            raise api.CommandError('loader has no save method')
        loader.save(file)
        print('Saved to {}'.format(file))
        api.unsaved_changes = False

        if and_exit:
            api.manual_execute(ExitCommand(), {})

    def input_handler_loader(self, i):
        return ' '.join(i.split())  # remove double whitespace


class HelpCommand(api.Command):
    """Command to display information about other commands."""

    ID = 'help'
    description = ('display information about registered commands or about '
                   'a specific command')

    def signature(self):
        r = '[{}]'.format('|'.join(['<{}>'.format(k)
                          for k in api.registry.keys()]))
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
            for k, v in api.registry.items():
                if api.is_disabled(v):
                    disabled.append(k)
                else:
                    print('-', k)
            if not disabled:
                return
            print('\nCommands disabled in current context:')
            for k in disabled:
                print('-', k)
        else:
            c = api.resolve_command(command)
            # don't catch error, it will have the correct message already
            signature = api.resolve_signature(c)
            print('Help on command \'{}\':\n'.format(c.ID))
            if c.description:
                print('- description:', c.description)
            if signature:
                print('- signature:', ' '.join(signature.split()))
                # this removes double
            _lexer = lexers.SignatureLexer(signature)
            _parser = parsers.SignatureParser(_lexer, c.ID)
            _sig_parts = _parser.make_signature()
            print('- syntax:', c.ID, ' '.join([
                s.signature_syntax() for s in _sig_parts
            ]))
            if api.is_disabled(c):
                print('- disabled in current context')


class ReloadCommand(api.Command):
    """Command to reload plugin files."""

    ID = 'reload'
    signature = '<and clean> <verbose>'
    description = 'reload all plugin files'

    def execute(self, and_clean, verbose):
        if verbose:
            current = api.log.is_startup
            api.log.is_startup = True
        api.reload_plugins(clean=and_clean)
        if verbose:
            api.log.is_startup = current


class LoadCommand(api.Command):
    """Command to find a loader to manually load a data tree."""

    ID = 'load'
    signature = 'STRING=file [using STRING=loader]'
    description = 'find a loader command to manually load a data tree'
    defaults = {'loader': 'default'}

    def disabled(self):
        return api.tree is not None

    def execute(self, file, loader):
        try:
            loader = api.loaders[loader]()
        except KeyError:
            raise api.CommandError(f'no loader \'{loader}\'')
        if not hasattr(loader, 'load'):
            raise api.CommandError('loader has no load method')
        prev = api.log.disable_all, api.log.is_startup
        api.log.disable_all = False
        api.log.is_startup = True
        api.log.data_source = os.path.abspath(file)
        r = loader.load(file)
        api.log.disable_all, api.log.is_startup = prev
        # run the loading command
        api.tree = api.Tree(r)
        # value of first (loader) command to be run

    def input_handler_loader(self, i):
        return ' '.join(i.split())


class SetCommand(api.Command):
    """Set api.log values."""

    ID = 'set'
    signature = ('STRING=name to (STRING=value STRING=extra*)'
                 '|(NUMBER=value NUMBER=extra*)')
    description = 'set a value in api.log'

    def execute(self, name, value, extra):
        super().execute()
