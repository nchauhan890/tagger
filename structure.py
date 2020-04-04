"""Objects used for data parsing."""

from tagger import api


class Root:
    """Base of the data tree."""
    def __init__(self, name, tags=None):
        tags = tags or {}
        self.data = name
        self.tags = tags
        self.children = []
        self.depth = 0

    def __repr__(self):
        return 'Root({})'.format(self.data)

    @property
    def parent_list(self):
        return []  # property to make it read-only

    @property
    def traversal_depth(self):
        return [self]

    @property
    def number_of_parents(self):
        return 0


class Node:
    """A data point in the data tree."""
    def __init__(self, data, depth, parent):
        self.data = data
        self.depth = depth
        self.tags = {}
        self.parent = parent
        self.children = []
        self._parent_list = [*self.parent.parent_list, self.parent]

    def __repr__(self):
        return 'Node({})'.format(self.data)

    def _clean_data(self):
        self.data = str(self.data)
        for k, v in self.tags.items():
            if not isinstance(k, str):
                self.tags[str(k)] = str(v)
                del self.tags[k]
            else:
                self.tags[k] = str(v)

    @property
    def parent_list(self):
        return self._parent_list
        # property to make it read-only

    @property
    def traversal_depth(self):
        return [*self._parent_list, self]

    @property
    def number_of_parents(self):
        return len(self.parent_list)


class Pattern:
    """Produced by input parser to represent text, tags and data points."""
    def __repr__(self):
        if isinstance(self, TagPattern):
            return 'TagPattern({}, {}, {})'.format(
                repr(self.data), repr(self.value), repr(self.depth)
            )
        if isinstance(self, NodePattern):
            return 'NodePattern({}, {})'.format(
                repr(self.data), repr(self.depth)
            )
        if isinstance(self, TextPattern):
            return 'TextPattern({})'.format(repr(self.data))
        return super().__str__()


class TextPattern(Pattern):
    def __init__(self, data):
        self.data = data


class NodePattern(Pattern):
    def __init__(self, data, depth):
        self.data = data
        self.depth = depth


class TagPattern(Pattern):
    def __init__(self, data, value, depth):
        self.data = data
        self.value = value
        self.depth = depth


class SignaturePattern:
    """Produced by SignatureParser to represent optionals/variables/inputs.

    Used when parsing command signatures.
    """
    def __init__(self, token):
        self.value = token.value
        self.type = token.type


class Optional(SignaturePattern):
    """Wrapper around signature elements that may not be present."""
    def __init__(self, pattern):
        self.pattern = pattern
        self.type = pattern.type
        self.value = pattern.value


class Variable(SignaturePattern):
    """Wrapper around signature elements that can be repeated"""
    def __init__(self, pattern):
        self.pattern = pattern
        self.type = pattern.type
        self.value = pattern.value


class Keyword(SignaturePattern):
    pass


class Flag(SignaturePattern):
    def __init__(self, pattern):
        self.parts = pattern.parts  # a Phrase object
        self.type = pattern.type
        self.value = pattern.value
        self.name = '_'.join([kw.value for kw in self.parts])


class Input(SignaturePattern):
    """Represents the STRING or NUMBER input field in signatures."""
    def __init__(self, token, argument_name):
        super().__init__(token)
        self.argument = argument_name


class Or(SignaturePattern):
    def __init__(self, parts):
        self.parts = parts
        self.type = self.parts[0].type
        self.value = self.parts[0].value


class End(SignaturePattern):
    def __init__(self):
        self.type = 'EOF'
        self.value = None


class Phrase(SignaturePattern):
    def __init__(self, parts):
        self.parts = parts
        self.type = self.parts[0].type
        self.value = self.parts[0].value


class OptionalPhrase(SignaturePattern):
    """Represents a group of elements which all may or may not be present."""
    def __init__(self, parts):
        self.parts = parts
        self.type = self.parts[0].type
        self.value = self.parts[0].value

    def __next__(self):
        return next(self.parts)


class NameDispatcher:
    def __init__(self, reference, warn=None):
        self._dispatch_ref = reference
        self._warn = warn

    def __getattribute__(self, k):
        if k in ['_dispatch_ref', '_warn']:
            return object.__getattribute__(self, k)
        try:
            return self._dispatch_ref[k]
        except KeyError as e:
            raise AttributeError(str(e))

    def __setattr__(self, k, v):
        if k in ['_dispatch_ref', '_warn']:
            object.__setattr__(self, k, v)
        elif self._warn is not None and k not in self._dispatch_ref:
            api.warning(str(self._warn) + k)
        self._dispatch_ref[k] = v
