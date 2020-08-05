"""Objects used for data parsing and to implement CLI/signature parsing."""

from tagger import api
from tagger.lexers import (NUMBER, STRING, EOF, KEYWORD)


class NodeType:
    """Base type of Node class."""

    def __repr__(self):
        return f'{self.__class__.__name__}({self.data})'


class Root(NodeType):
    """Base of the data tree."""

    def __init__(self, name, tags=None):
        tags = tags or {}
        self.data = name
        self.tags = tags
        self.children = []
        self.depth = 0

    @property
    def parent_list(self):
        return []  # property to make it read-only

    @property
    def traversal_depth(self):
        return [self]

    @property
    def number_of_parents(self):
        return 0


class Node(NodeType):
    """A data point in the data tree."""

    def __init__(self, data, depth, parent, tags=None):
        self.data = data
        self.depth = depth
        self.tags = tags or {}
        self.parent = parent
        self.children = []
        self._parent_list = [*self.parent.parent_list, self.parent]

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
            return (f'TagPattern({self.data!r}, {self.value!r}, '
                    f'{self.depth!r})')

        if isinstance(self, NodePattern):
            return f'NodePattern({self.data!r}, {self.depth!r})'

        if isinstance(self, TextPattern):
            return f'TextPattern({self.data!r})'
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


class SignatureElement:
    """Produced by SignatureParser to represent a part of a signature."""

    is_optional = False

    def __init__(self, token, **kwargs):
        self.value = token.value
        self.type = token.type
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __repr__(self):
        return '{}({})'.format(
            self.__class__.__name__,
            ', '.join('{}={}'.format(
                k, repr(v)) for k, v in self.__dict__.items()
            )
        )

    def __len__(self):
        return 1

    def match(self, parser, offset=0):
        return False

    def parse(self, parser):
        raise api.CommandError(f'parsing for {self.__class__.__name__} not yet'
                               'implemented', error=api.CommandError)

    def scan(self):
        return {}

    def set_input(self, parser, key, value):
        try:
            current = parser.inputs[key]
        except KeyError:
            raise api.CommandError('signature object tried to assign to '
                                   f'unscanned input {key}')
        if isinstance(current, list):
            current.append(value)
        else:
            parser.inputs[key] = value


class InputType(SignatureElement):
    """Base class for inputs in signatures."""

    def scan(self):
        return {self.value: None}


class WrapperType(SignatureElement):
    """Base class for wrappers around signature elements."""

    def __init__(self, pattern):
        self.pattern = pattern
        self.type = pattern.type
        self.value = pattern.value

    def scan(self):
        return self.pattern.scan()


class PhraseWrapperType(SignatureElement):
    """Base class for wrappers around multiple signature elements."""

    def __init__(self, parts):
        self.parts = parts
        self._parts = parts.copy()   # will contain a modified version
        self.type = parts[0].type    # containing only matched parts (where
        self.value = parts[0].value  # there were unmatched, optional parts)

    def __len__(self):
        return len(self.parts)

    def scan(self):
        inputs = {}
        for part in self.parts:
            inputs.update(part.scan())
        return inputs

    def match(self, parser, offset=0):
        new = []
        for part in self.parts:
            if not part.match(parser, offset=+offset):
                # don't return false if the part is optional
                if part.is_optional:
                    continue  # temporarily remove unmatched optional from
                return False  # new parts list
            else:
                offset += 1  # only change offset if something was there
                new.append(part)
        self._parts = new
        return True

    def parse(self, parser):
        for part in self._parts:
            part.parse(parser)


class KeywordPhraseWrapperType(PhraseWrapperType):
    """Base class for wrappers around multiple keywords in signatures."""

    def __init__(self, parts):
        self.parts = parts
        self.type = parts[0].type
        self.value = parts[0].value

    def match(self, parser, offset=0):
        for i, part in enumerate(self.parts):
            token = parser.lookahead(i+offset)
            if token.type != KEYWORD or token.value != part.value:
                return False
        return True

    def parse(self, parser):
        for part in self.parts:
            current = parser.current_token
            if current.type == KEYWORD and current.value == part.value:
                parser.eat(KEYWORD)
            else:
                raise api.CommandError(
                    f'expected token KEYWORD ({part.value})'
                )


class Phrase(PhraseWrapperType):
    """Mark a grouped phrase in signatures."""


class OptionalPhrase(PhraseWrapperType):
    """Mark an optional phrase in signatures."""

    is_optional = True


class Flag(KeywordPhraseWrapperType):
    """Mark a flag in signatures."""

    is_optional = True

    def scan(self):
        name = '_'.join(part.value for part in self.parts)
        return {name: False}

    def parse(self, parser):
        super().parse(parser)
        self.set_input(
            parser, '_'.join(part.value for part in self.parts), True
        )


class Capture(KeywordPhraseWrapperType):
    """Mark a keyword capture."""

    def scan(self):
        name = '_'.join(part.value for part in self.parts)
        return {name: False}

    def parse(self, parser):
        super().parse(parser)
        self.set_input(
            parser, '_'.join(part.value for part in self.parts), True
        )


class Or(PhraseWrapperType):
    """Mark an OR expression in signatures."""

    def __init__(self, parts):
        super().__init__(parts)
        self.part_found = None
        self.part_len = 0

    def __len__(self):
        return max(len(p) for p in self.parts)

    def match(self, parser, offset=0):
        matched = False
        for i, part in enumerate(self.parts):
            if part.match(parser, offset=offset):
                if len(part) > self.part_len:
                    self.part_found = i
                matched = True
        return matched

    def parse(self, parser):
        if self.part_found is None:
            raise api.CommandError('cannot parse OR expression')
        self.parts[self.part_found].parse(parser)

    @property
    def is_optional(self):
        return all(part.is_optional for part in self.parts)


class Keyword(SignatureElement):
    """Mark a keyword in signatures."""

    def match(self, parser, offset=0):
        token = parser.lookahead(offset)
        return token.type == KEYWORD and token.value == self.value

    def parse(self, parser):
        parser.eat(KEYWORD)


class StringInput(InputType):
    """Mark a string input in signatures."""

    def parse(self, parser):
        self.set_input(parser, self.value, parser.current_token.value)
        parser.eat(STRING)

    def match(self, parser, offset=0):
        return parser.lookahead(offset).type == STRING


class NumberInput(InputType):
    """Mark a numerical input in signatures."""

    def parse(self, parser):
        self.set_input(parser, self.value, parser.current_token.value)
        parser.eat(NUMBER)

    def match(self, parser, offset=0):
        return parser.lookahead(offset).type == NUMBER


class Optional(WrapperType):
    """Wrapper around inputs to mark them as optional."""

    is_optional = True

    def match(self, parser, offset=0):
        return self.pattern.match(parser, offset=offset)

    def parse(self, parser):
        self.pattern.parse(parser)


class Variable(WrapperType):
    """Wrapper around inputs to mark them as variable repetition."""

    is_optional = True

    def scan(self):
        inputs = self.pattern.scan()
        inputs = {k: [] for k in inputs}
        # print('variable', inputs)
        return inputs

    def match(self, parser, offset=0):
        return self.pattern.match(parser, offset=offset)

    def parse(self, parser):
        while self.pattern.match(parser):
            self.pattern.parse(parser)


class End(SignatureElement):
    """Mark the end of a signature."""

    def __init__(self):
        self.value = None
        self.type = EOF


class NameDispatcher:
    """Helper class to convert attribute lookup to dictionary lookup.

    Can warn when value being returned is None and when a non-existent
    key is being assigned to.
    """

    def __init__(self, reference, warn=None, error_if_none=None):
        self._dispatch_ref = reference
        self._warn = warn
        self._error_none = error_if_none

    def __getattribute__(self, k):
        if k in ['_dispatch_ref', '_warn', '_error_none']:
            return object.__getattribute__(self, k)
        try:
            r = self._dispatch_ref[k]
            if r is None and self._error_none is not None:
                raise TypeError('{} ({})'.format(self._error_none, k))
            return r
        except KeyError as e:
            raise AttributeError(str(e))

    def __setattr__(self, k, v):
        if k in ['_dispatch_ref', '_warn', '_error_none']:
            object.__setattr__(self, k, v)
        elif self._warn is not None and k not in self._dispatch_ref:
            api.warning(str(self._warn) + k)
        else:
            self._dispatch_ref[k] = v
