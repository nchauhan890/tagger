"""Example commands for API."""

from tagger import api


class Hooks(api.Hooks):
    def startup_hook():
        print('example startup hook')

    def custom_hook():
        print('custom hook used')


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
        # print(api.plugin.display_hook(api.tree.current_node))
        pass


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


class CustomHookDemoCommand(api.Command):

    ID = 'hook demo'

    def execute(self):
        api.plugin.custom_hook()


class NodeReferenceCommand(api.Command):

    ID = 'node ref'
    signature = 'NODEREF/forward=node'

    def execute(self, node):
        print(node)


api.register_hook('custom_hook', single=True, default=Hooks.custom_hook)
