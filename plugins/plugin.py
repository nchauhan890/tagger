"""Plugin for API execution hooks and custom commands."""


from tagger import api


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
    if node.depth < 4:
        type = ('character', 'quote', 'analysis')[node.depth - 1]
        if type not in node.tags:
            node.tags[type] = None


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
                v = ', '.join([str(vi) for vi in v])
            string = '\n'.join([string, '{}• {}: {}'.format('  ' * i, k, v)])

    if current.children:
        string = '\n'.join([
            string,
            '{}Entries:'.format('  ' * (i - 1))
        ])

        # --- display the current node's child entries ---
        longest = max(len(str(len(current.children)))+1, (i*2)+1)
        # this will either indent using the current (depth * 2) or, if the
        # numbers of child entries is so long the last digits won't fit, the
        # greatest number of digits
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


class ShowChildrenCommand(api.Command):

    ID = 'children'

    @staticmethod
    def disabled():
        return not bool(api.tree.current_node.children)

    def execute(self):
        for i, node in enumerate(api.tree.current_node.children, 1):
            print('{:>3} {}'.format(i, node.data))


class ExampleCommand(api.Command):

    ID = 'example'
    signature = ('STRING=data [of NUMBER=node] [in NUMBER=pos] '
                 'NUMBER=repeats? STRING=conditions* keyword?')
    defaults = {'node': 0, 'pos': 0, 'repeats': 1, 'conditions': None}

    def execute(self, data, node=0, pos=0, repeats=1, conditions=None):
        print('this command is to demonstrate signature parsing only')


class FlagCommand(api.Command):

    ID = 'flag'
    signature = '<one> <two> <three>'


class MutuallyExclusiveFlagCommand(api.Command):
    ID = 'f'
    signature = '<one>|<two three>'
