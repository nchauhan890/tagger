"""Defines commanda to load a data tree from different formats."""

import json

from tagger import api
from tagger import lexers
from tagger import parsers
from tagger import structure


class JSONLoaderCommand(api.Command):
    """Load a data tree from a JSON file rather than tagger format."""

    ID = 'json loader'  # commands are case-insensitive
    signature = 'STRING=file'

    def disabled(self):
        return api.tree is not None

    def execute(self, file):
        with open(file, 'r') as f:
            try:
                object = json.load(f)
            except json.decoder.JSONDecodeError as e:
                raise api.CommandError(f'cannot load file:\n{str(e)}')
            if 'data' not in object:
                api.warning('no tree title given, defaulting to Tree')
                object['data'] = 'Tree'
            root = structure.Root(object['data'])
            tags = object.get('tags', {})
            if 'config' in tags:
                api.found_plugin_file(tags['config'])
            self.add_tags(root, tags)
            for child in object.get('children', []):
                root.children.append(self.recursive_construct(
                    child, depth=1, parent=root
                ))
            return root

    def recursive_construct(self, object, depth, parent):
        if 'data' not in object:
            raise SyntaxError(f'no data for node at level {depth} '
                              f'(parent: {parent.data})')
        node = api.new_node(object['data'], parent)
        self.add_tags(node, object.get('tags', {}))
        for child in object.get('children', []):
            node.children.append(self.recursive_construct(
                child, depth=depth+1, parent=node
            ))
        return node

    def add_tags(self, node, tags):
        for k, v in tags.items():
            if not isinstance(v, list):
                api.append_tag_value(k, v, node, create=True)
                continue
            for i in v:
                api.append_tag_value(k, i, node, create=True)
            # create new tags (or append to existing if duplicate names)


class DefaultLoaderCommand(api.Command):
    """Load a data tree from tagger format."""

    ID = 'default loader'
    signature = 'STRING=file'
    description = 'load data tree from default tagger format'

    def execute(self, file):
        with open(file, 'r') as f:
            source = f.read()
        parser = parsers.InputPatternParser(lexers.InputLexer(source))
        return parsers.construct_tree(parser)
