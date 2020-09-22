"""Objects used for data parsing and to implement CLI/signature parsing."""

from string import ascii_lowercase, digits

from tagger import api
from tagger.lexers import (
    NUMBER, STRING, DOT, DOTDOT, TILDE, SLASH, EOF, KEYWORD, INPUT
)

_id_chars = set(ascii_lowercase+digits+'_')
_inputs = {}


class NodeType:
    """Base type of Node class."""

    def __repr__(self):
        return f'{self.__class__.__name__}({self.data})'

    def update_id(self):
        if '_id' in self.tags:
            name = list(str(self.tags['_id']))
            name = ''.join([i for i in name if i in _id_chars])
        else:
            name = self.data.lower()
            new = []
            finished = False
            for char in name:
                if len(new) > 5:
                    finished = True
                if char == ' ':
                    if finished:
                        break
                    new.append('_')
                if char not in _id_chars:
                    continue
                new.append(char)
            name = ''.join(new)
        name = '_'.join([i for i in name.split('_') if i])
        if name[0] in digits:
            name = '_' + name
        try:
            changed = True
            while changed:
                changed = False
                for child in self.parent.children:
                    if getattr(child, '_id', '') == name:
                        name += '_'
                        changed = True
        except AttributeError:
            pass
        self.id = name


class Root(NodeType):
    """Base of the data tree."""

    def __init__(self, name, tags=None):
        tags = tags or {}
        self.data = name
        self.tags = tags
        self.children = []
        self.depth = 0
        self.update_id()

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
        self.update_id()

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
                               'implemented')

    def scan(self):
        return {}

    def set_input(self, parser, key, value):
        try:
            current = parser.inputs[key]
        except KeyError:
            raise api.CommandError('signature object tried to assign to '
                                   f'unscanned input \'{key}\'')
        if isinstance(current, list):
            current.append(value)
        else:
            parser.inputs[key] = value

    def signature_syntax(self):
        return str(self.value)


class InputType(SignatureElement):
    """Base class for inputs in signatures."""

    options = []

    def __init_subclass__(cls):
        _inputs[cls.name.upper()] = cls

    def __init__(self, value, option=None):
        self.type = INPUT
        self.value = value
        self.option = option

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

    def signature_syntax(self):
        if len(self.parts) == 1:
            return self.parts[0].signature_syntax()
        return '({})'.format(' '.join([
            i.signature_syntax() for i in self.parts
        ]))


class OptionalPhrase(PhraseWrapperType):
    """Mark an optional phrase in signatures."""

    is_optional = True

    def signature_syntax(self):
        return '[{}]'.format(' '.join([
            i.signature_syntax() for i in self.parts
        ]))


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

    def signature_syntax(self):
        return '[{}]'.format(' '.join([i.signature_syntax()
                                       for i in self.parts]))


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

    def signature_syntax(self):
        return '({})'.format(' | '.join([
            i.signature_syntax() for i in self.parts
        ]))


class Keyword(SignatureElement):
    """Mark a keyword in signatures."""

    def match(self, parser, offset=0):
        token = parser.lookahead(offset)
        return token.type == KEYWORD and token.value == self.value

    def parse(self, parser):
        parser.eat(KEYWORD)


class StringInput(InputType):
    """Mark a string input in signatures."""

    name = 'STRING'

    def parse(self, parser):
        self.set_input(parser, self.value, parser.current_token.value)
        parser.eat(STRING)

    def match(self, parser, offset=0):
        return parser.lookahead(offset).type == STRING

    def signature_syntax(self):
        return '\'{}\''.format(self.value)


class NumberInput(InputType):
    """Mark a numerical input in signatures."""

    name = 'NUMBER'
    options = ('positive', 'negative')

    def parse(self, parser):
        token = parser.current_token
        number = parser.eat(NUMBER)
        if self.option == 'positive' and number < 0:
            parser.raise_error('expected NUMBER (positive)', token=token)
        elif self.option == 'negative' and number >= 0:
            parser.raise_error('expected NUMBER (negative)', token=token)
        self.set_input(parser, self.value, number)

    def match(self, parser, offset=0):
        return parser.lookahead(offset).type == NUMBER

    def signature_syntax(self):
        return 'n'


class NodeRefInput(InputType):
    """Mark a reference to a node as an input in signatures."""

    name = 'NODEREF'
    options = ('forward', 'child')

    def match(self, parser, offset=0):
        return (parser.lookahead(offset).type
                in (DOT, DOTDOT, TILDE, SLASH, KEYWORD, NUMBER))

    def parse(self, parser):
        if self.option == 'forward':
            self.parse_forward(parser)
            return
        elif self.option == 'child':
            self.parse_child(parser)
            return
        ref = []
        if parser.current_token.type in (DOT, DOTDOT, TILDE):
            ref.append(parser.eat(parser.current_token.type))
        elif parser.current_token.type == KEYWORD:
            ref.extend(['.', parser.eat(KEYWORD)])
        elif parser.current_token.type == NUMBER:
            ref.extend(['.', parser.eat(NUMBER)])
        else:
            ref.append('.')  # assume starting slash means from current (dot)
        while parser.current_token.type == SLASH:
            parser.eat(SLASH)
            if parser.current_token.type in (DOTDOT, NUMBER, KEYWORD):
                ref.append(parser.eat(parser.current_token.type))
            else:
                raise api.CommandError(
                    'expected token NUMBER, KEYWORD or DOTDOT'
                )
        self.set_input(parser, self.value, ref)

    def parse_forward(self, parser):
        ref = []
        if parser.current_token.type == DOT:
            ref.append(parser.eat(parser.current_token.type))
        elif parser.current_token.type == KEYWORD:
            ref.extend(['.', parser.eat(KEYWORD)])
        elif parser.current_token.type == NUMBER:
            ref.extend(['.', parser.eat(NUMBER)])
        else:
            ref.append('.')  # assume starting slash means from current (dot)
        while parser.current_token.type == SLASH:
            parser.eat(SLASH)
            if parser.current_token.type in (NUMBER, KEYWORD):
                ref.append(parser.eat(parser.current_token.type))
            else:
                raise api.CommandError(
                    'expected token NUMBER or KEYWORD (forward reference)'
                )
        self.set_input(parser, self.value, ref)

    def parse_child(self, parser):
        ref = []
        if parser.current_token.type == DOT:
            ref.append(parser.eat(parser.current_token.type))
            parser.eat(SLASH)
        else:
            ref.append('.')
        if parser.current_token.type in (NUMBER, KEYWORD):
            ref.append(parser.eat(parser.current_token.type))
        else:
            raise api.CommandError(
                'expected token NUMBER or KEYWORD (child reference)'
            )
        self.set_input(parser, self.value, ref)

    def signature_syntax(self):
        return '<node>'


class Optional(WrapperType):
    """Wrapper around inputs to mark them as optional."""

    is_optional = True

    def match(self, parser, offset=0):
        return self.pattern.match(parser, offset=offset)

    def parse(self, parser):
        self.pattern.parse(parser)

    def signature_syntax(self):
        return '{}?'.format(self.pattern.signature_syntax())


class Variable(WrapperType):
    """Wrapper around inputs to mark them as variable repetition."""

    is_optional = True

    def scan(self):
        inputs = self.pattern.scan()
        inputs = {k: [] for k in inputs}
        return inputs

    def match(self, parser, offset=0):
        return self.pattern.match(parser, offset=offset)

    def parse(self, parser):
        while self.pattern.match(parser):
            self.pattern.parse(parser)

    def signature_syntax(self):
        return '{}*'.format(self.pattern.signature_syntax())


class End(SignatureElement):
    """Mark the end of a signature."""

    def __init__(self):
        self.value = None
        self.type = EOF

    def signature_syntax(self):
        return ''


class NameDispatcher:
    """Helper class to convert attribute lookup to dictionary lookup."""

    def __init__(self, reference, getter_hook=None, setter_hook=None):
        self._dispatch_ref = reference
        self._getter_hook = getter_hook or (lambda ref, k, v: v)
        self._setter_hook = setter_hook or (lambda ref, k, v: v)

    def __getattribute__(self, k):
        if k in _dispatch_names:
            return object.__getattribute__(self, k)
        try:
            r = self._dispatch_ref[k]
        except KeyError as e:
            raise AttributeError(str(e))
        return self._getter_hook(self._dispatch_ref, k, r)

    def __setattr__(self, k, v):
        if k in _dispatch_names:
            object.__setattr__(self, k, v)
        else:
            v = self._setter_hook(self._dispatch_ref, k, v)
            self._dispatch_ref[k] = v


class PluginHookDispatcher(NameDispatcher):
    def __getattribute__(self, k):
        if k in _dispatch_names:
            return object.__getattribute__(self, k)
        try:
            r = self._dispatch_ref[k]
            if r is None:
                return lambda *args, **kw: None
        except KeyError as e:
            raise AttributeError(str(e))
        r = self._getter_hook(self._dispatch_ref, k, r)
        if isinstance(r, list):
            def hook_caller(*args, **kw):
                # return [hook(*args, **kw) for hook in r]
                [hook(*args, **kw) for hook in r]
            hook_caller.__name__ = k + '_hook_caller'
            return hook_caller
        return r

    def __setattr__(self, k, v):
        if k in _dispatch_names:
            object.__setattr__(self, k, v)
        else:
            v = self._setter_hook(self._dispatch_ref, k, v)
            if isinstance(self._dispatch_ref[k], list):
                self._dispatch_ref[k].append(v)
            elif api.log.importing_main_plugin:
                self._dispatch_ref[k] = v


_dispatch_names = ['_dispatch_ref', '_getter_hook', '_setter_hook']


def _is_single(key):
    return not isinstance(api.plugin._dispatch_ref.get(key, []), list)


def warn_if_new(message):
    def _warn_if_new(ref, key, value):
        if key not in ref:
            api.warning(f'{message} {key}')
        return value
    return _warn_if_new


def error_if_test(test, message):
    def _error_if_test(ref, key, value):
        if test(value):
            raise TypeError(f'{message} {key}')
        return value
    return _error_if_test
