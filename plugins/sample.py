"""Plugin hooks for sample data."""

from tagger import api


class Hooks(api.Hooks):
    def post_node_creation_hook(node):
        if node.depth < 4:
            type = ('character', 'quote', 'analysis')[node.depth - 1]
            if type not in node.tags:
                api.new_tag(type, node=node)
