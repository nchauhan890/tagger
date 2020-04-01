"""Example commands for API."""

from tagger import api


class ShowChildrenCommand(api.Command):
    """Show the children of the current node."""

    ID = 'children'

    def disabled(self):
        return not bool(api.tree.current_node.children)

    def execute(self):
        for i, node in enumerate(api.tree.current_node.children, 1):
            print('{:>3} {}'.format(i, node.data))


class ShowCommand(api.Command):

    ID = 'show'

    def execute(self):
        print(api.plugin.display_hook(api.tree.current_node))


class ExampleCommand(api.Command):

    ID = 'example'
    signature = ('STRING=data [of NUMBER=node] [in NUMBER=pos] '
                 'NUMBER=repeats? STRING=conditions* keyword?')
    defaults = {'node': 0, 'pos': 0, 'repeats': 1}
    description = 'this command is to demonstrate signature parsing only'


class FlagCommand(api.Command):

    ID = 'flag'
    signature = '<one> <two> <three>'

    def execute(self, one, two, three):
        print('one:', one)
        print('two:', two)
        print('three:', three)
        print('this command is to demonstrate flags only')


class MutuallyExclusiveFlagCommand(api.Command):

    ID = 'mutually exclusive flag'
    signature = '<one>|<two three>'


class MakeTag(api.Command):

    ID = 'tag'
    signature = 'STRING=data'
