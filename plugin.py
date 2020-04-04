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

        return value: bool
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

        return value: bool
        """
        return True

    def display_hook(current):
        """Customise the display upon prompt for command

        current: the current node [Node]

        return value: a string to display [str]
        """
        traversal = iter(current.traversal_depth)
        string = ''
        for i in api.tree.traversal_numbers:
            string += str(i + 1) + '.'
        string = string[:-1]  # remove trailing dot
        # --- display the current node ---
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

        current: the current node [Node]

        return value: a string for the CLI prompt [str]
        """
        return '>>> '

    def inspect_commands(commands):
        """Modify the commands about to be executed.

        commands: list of commands [Command]

        return value: list of commands
        """
        return commands

    def inspect_post_commands(commands):
        """Modify the commands in the post_commands queue.

        commands: list of commands [Command]

        return value: list of commands
        """
        return commands

    def startup_hook():
        """Execute code as soon as the plugin is registered.

        return value: None
        """
        pass


class ExitCommand(api.Command):

    ID = 'exit'
    description = 'exit the program'

    def execute(self):
        if api.log.unsaved_changes:
            print('There are unsaved changes to the data tree')
        print('Are you sure? Type \'yes\' to confirm')
        v = input().lower().strip()
        if v == 'yes':
            api.exit()


class SaveCommand(api.Command):

    ID = 'save'
    signature = '[as STRING=name|<current>] <and exit>'
    defaults = {'name': None}
    description = 'save the data tree to a file'

    def execute(self, name, current, and_exit):
        cwd = os.path.split(api.log.data_source)[0]
        if current:
            file = api.log.data_source
        elif name is None:
            file = 'output.txt'
            if file in os.listdir(cwd):
                i = 1
                file = 'output_{}.txt'.format(i)
                while file in os.listdir(cwd):
                    i += 1
                    file = 'output_{}.txt'.format(i)
            file = os.path.join(cwd, file)
        else:
            if name in os.listdir(cwd):
                print('File already exists - do you want to overwrite?')
                r = input('Type \'yes\' to overwrite\n').strip().lower()
                if r != 'yes':
                    return
            file = os.path.join(cwd, name)

        self.depth = 0
        with open(file, 'w') as f:
            self.file = f
            self.write_data(api.tree.root.data)
            tags = api.tree.root.tags.copy()
            self.write_tags(tags)
            for child in api.tree.root.children:
                self.write_line('')
                self.recursive_save(child)
            print('Saved to {}'.format(file))
            api.unsaved_changes = False

        if and_exit:
            api.manual_execute(ExitCommand(), {})

    def recursive_save(self, node):
        self.depth += 1
        self.write_data(node.data)
        self.write_tags(node.tags)
        for child in node.children:
            self.recursive_save(child)
        self.depth -= 1

    def write_tags(self, tags):
        for k, v in tags.items():
            if v is None:
                v = ''
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


class HelpCommand(api.Command):

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
                self.signature_syntax(s) for s in _sig_parts
            ]))
            if api.is_disabled(c):
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
        if isinstance(signature, structure.Or):
            return '({})'.format(' | '.join([
                self.signature_syntax(x) for x in signature.parts
            ]))
        if isinstance(signature, structure.Flag):
            return ' '.join([self.signature_syntax(x)
                             for x in signature.parts])
        if isinstance(signature, structure.Input):
            if signature.type == lexers.NUMBER:
                return 'n'
            if signature.type == lexers.STRING:
                return '\'{}\''.format(signature.argument)
        return str(signature.value)
