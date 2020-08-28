"""Defines commanda to load a data tree from different formats."""

import json

from tagger import api
from tagger import lexers
from tagger import parsers
from tagger import structure


class JSONLoaderCommand(api.Loader):
    """Load a data tree from a JSON file rather than tagger format."""

    ID = 'json'

    def load(self, file):
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
                self.found_plugin_file(tags['config'])
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

    def save(self, file):
        object = self.recursive_convert(api.tree.root)
        with open(file, 'w') as f:
            json.dump(object, f, indent=2)

    def recursive_convert(self, node):
        object = {'data': node.data}
        tags = getattr(node, 'tags', None)
        if tags:
            object['tags'] = tags
        if node.children:
            object['children'] = [
                self.recursive_convert(child) for child in node.children
            ]
        return object


class DefaultLoaderCommand(api.Loader):
    """Load a data tree from tagger format."""

    ID = 'default'

    def load(self, file):
        with open(file, 'r') as f:
            source = f.read()
        parser = parsers.InputPatternParser(lexers.InputLexer(source))
        return parsers.construct_tree(parser)

    def save(self, file):
        self.depth = 0
        with open(file, 'w') as f:
            self.file = f
            self.write_data(api.tree.root.data)
            tags = api.tree.root.tags.copy()
            self.write_tags(tags)
            for child in api.tree.root.children:
                self.write_line('')
                self.recursive_save(child)

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
        tag = tag.replace('=', '\\=')
        tag = tag.replace('\\', '\\\\')
        if value:
            return '{}`{}={}'.format('*' * self.depth, tag, value)
        return '{}`{}'.format('*' * self.depth, tag)

    def write_line(self, line):
        self.file.write('{}\n'.format(line))
