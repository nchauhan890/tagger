"""Parsers for data input, CLI and command signatures."""

import sys
sys.setrecursionlimit(200)

from tagger import lexers
from tagger import structure
from tagger import api

from tagger.lexers import (
    STAR, TEXT, TAG, EQUAL, NUMBER, STRING, SEMICOLON, LESS, OR, GREATER,
    EOF, LBRACKET, ARGUMENT, RBRACKET, OPTIONAL, VARIABLE, KEYWORD,
    LPAREN, RPAREN, LBRACE, RBRACE, INPUT, SLASH
)


class ParserBase:
    """Base class to perform essential parsing functions."""

    def __init__(self, lexer):
        self.lexer = lexer
        self.current_token = self.lexer.generate_token()
        self.buffer = []
        self._previous = None  # the token just consumed

    def eat(self, type, extra=''):
        """Consume the given token and advance to the next.

        type: the token type to eat [str]
        extra: suffix to add to error message

        return: the value of the consumed token
        """
        if self.current_token.type == type:
            value = self.current_token.value
            self.advance_token()
        else:
            value = (f' ({self.current_token.value})'
                     if self.current_token.type == KEYWORD else '')

            self.raise_error(f'invalid token {self.current_token.type}'
                             f'{value} (expected {type})', extra=extra)
        return value

    def advance_token(self):
        """Move to the next token from the lexer."""
        self._previous = self.current_token
        if self.buffer:
            self.current_token = self.buffer.pop(0)
        else:
            self.current_token = next(self.lexer)

    def lookahead(self, n=1):
        """Return an upcoming token without eating it.

        n: [default=1] how many tokens ahead to return [int]

        return: lookahead token [Token]
        """
        if n < 0:
            raise ValueError('lookahead cannot be negative')
        if n == 0:
            return self.current_token
        while len(self.buffer) < n:
            self.buffer.append(next(self.lexer))
        return self.buffer[n-1]

    def raise_error(self, msg, error=None, extra='', token=None):
        """Raise an error and add formatting to error message."""
        error = error or SyntaxError
        token = token or self.current_token
        if extra:
            extra = ' ' + extra.rstrip(' ')
        raise error('{}{} at {}.{}\ntoken: {}'.format(
            msg.rstrip(' '), extra, self.lexer.line,
            self.lexer.col, token.value or ''
        ))

    def reset(self):
        self.lexer.reset()
        self.__init__(self.lexer)


class InputPatternParser(ParserBase):
    """Parse tokens for data source and produce patterns."""

    def __next__(self):
        return self.generate_pattern()

    def _generate_tag(self, depth=0):
        name, value = self.eat(TAG), None
        if self.current_token.type == EQUAL:
            self.eat(EQUAL)
            value = self.eat(TEXT)
        return structure.TagPattern(name, value, depth)

    def generate_pattern(self):
        if self.current_token.type == EOF:
            return None
        if self.current_token.type == TEXT:
            return structure.TextPattern(self.eat(TEXT))
        elif self.current_token.type == TAG:
            return self._generate_tag()
        else:
            depth = len(self.eat(STAR))
            if self.current_token.type == TAG:
                return self._generate_tag(depth)
            else:
                return structure.NodePattern(self.eat(TEXT), depth)


class CLIParser(ParserBase):
    """Parse tokens from CLI input and produce commands."""

    def generate_commands(self):
        """Create list of commands from CLI input."""
        commands = []
        c = self.command()
        if c is not None:
            commands.append(c)
        while self.current_token.type == SEMICOLON:
            self.eat(SEMICOLON)
            c = self.command()
            if c is not None:
                commands.append(c)
        self.eat(EOF)
        return commands

    def eat_keyword(self, keyword):
        """Eat a keyword token, checking it has the correct value too."""
        if (self.current_token.type == KEYWORD
              or self.current_token.value == keyword):
            self.eat(KEYWORD)
        self.raise_error(f'expected token KEYWORD ({keyword})')

    def command(self):
        """Generate one command by parsing CLI input."""
        current = self.current_token
        current_reg = {}
        for k, v in api.registry.items():
            current_reg[tuple(k.split())] = v
        if current.type == EOF:
            return

        def error(t):
            self.raise_error(f'invalid token {t.type}', token=t)

        def first_level_key(dict):
            for key in dict:
                if key:
                    yield key[0]

        def loop_keyword(self, current_reg):
            if (self.current_token.type == KEYWORD
                    and self.current_token.value in first_level_key(
                        current_reg
                    )):
                c = self.eat(KEYWORD)
                current_reg = advance_registry_level(current_reg, c)
                return loop_keyword(self, current_reg)
            else:
                try:
                    return current_reg[()]
                except KeyError:
                    error(self.current_token)

        def advance_registry_level(reg, value):
            new = {}
            for k, v in reg.items():
                if k and k[0] == value:
                    new[k[1:]] = v
            return new

        if current.type == KEYWORD:
            c = self.eat(KEYWORD)
            if c not in first_level_key(current_reg):
                self.raise_error(
                    f'unknown command \'{c}\'',
                    token=current
                )
            current_reg = advance_registry_level(current_reg, c)
            command = loop_keyword(self, current_reg)
            command = command()  # instantiate the command class
        else:
            error(current)

        return self.parse_using_signature(command)

    def scan_for_inputs_or_flags(self, phrase):
        """Search the input for inputs or flags."""
        r = {}
        for part in phrase:
            r.update(part.scan())
        return r

    def next_part(self):
        try:
            self.current_part = next(self.parts)
        except StopIteration:
            self.current_part = structure.End()

    def parse_using_signature(self, command):
        """Parse a command's arguments using its signature.

        command: command instance [Command]

        return: command with inputs assigned to it [Command]
        """
        if hasattr(command, 'sig_cache'):
            self.signature_parts = command.sig_cache
        else:
            signature = api.resolve_signature(command)
            if api.is_disabled(command):
                raise api.CommandError(f'command \'{command.ID}\' is disabled')
            self.sig = SignatureParser(
                lexers.SignatureLexer(signature),
                command.ID
            )
            self.signature_parts = self.sig.make_signature()
            type(command).sig_cache = self.signature_parts  # set on class

        self.parts = Buffer(iter(self.signature_parts))
        found_inputs = self.scan_for_inputs_or_flags(self.signature_parts)
        self.inputs = found_inputs
        self.next_part()  # to initialise self.current_part

        while not isinstance(self.current_part, structure.End):
            try:
                if self.current_token.type == STAR:
                    self.eat(STAR)
                self.parse_signature_token()
            except api.CommandError as e:
                self.raise_error(
                    f'{str(e)} for command \'{command.ID}\'\n'
                    f'(signature: {api.resolve_signature(command)})',
                    error=api.CommandError
                )
        command.inputs = self.inputs
        return command

    def parse_signature_token(self):
        """Parse one element of a command's signature."""
        current_part = self.current_part
        if current_part.match(self):
            current_part.parse(self)
            self.next_part()
        elif current_part.is_optional:
            self.next_part()
        else:
            message = f'expected token {current_part.type}'
            if isinstance(current_part, structure.Keyword):
                message += f' ({current_part.value})'
            message += f' in {current_part.__class__.__name__}'
            raise api.CommandError(message)


class SignatureParser(ParserBase):
    """Parse tokens for command signatures."""
    def __init__(self, lexer, name):
        self.name = name
        self.queue = []
        ParserBase.__init__(self, lexer)

    def eat(self, *args, **kw):
        return ParserBase.eat(self, *args,
            extra=f'in signature\nfor command \'{self.name}\' '
                  f'(signature: {self.lexer.data})', **kw)

    def raise_error(self, *args, **kw):
        return ParserBase.raise_error(self, *args, **kw,
            extra=f'in signature\nfor command \'{self.name}\' '
                  f'(signature: {self.lexer.data})')

    def make_signature(self):
        """Parse a command signature to create a list of parts.

        return: parts list [List: structure.SignatureElement]
        """
        parts = [self.get_part()]
        if parts[-1] == None:
            return []
        while self.current_token.type != EOF:
            part = self.get_part()
            if part is None:
                continue
            parts.append(part)
        return parts

    def get_part(self):
        """Produce one signature part by recursive descent parsing."""
        return self.or_()

    def or_(self):
        r = [self.variable_optional()]
        while self.current_token.type == OR:
            self.eat(OR)
            r.append(self.variable_optional())
        if r[1:]:
            return structure.Or(r)
        else:
            return r[0]  # don't return an OR if none were present

    def variable_optional(self):
        r = self.atom()
        if isinstance(r, (structure.InputType, structure.Keyword,
                          structure.Flag, structure.Capture,
                          structure.Phrase)):
            if self.current_token.type == OPTIONAL:
                self.eat(OPTIONAL)
                r = structure.Optional(r)
            elif self.current_token.type == VARIABLE:
                self.eat(VARIABLE)
                r = structure.Variable(r)
        return r

    def atom(self):
        r = None
        if self.current_token.type == LBRACKET:
            r = self.phrase(optional=True)

        elif self.current_token.type == LPAREN:
            r = self.phrase()

        elif self.current_token.type == LESS:
            r = self.flag_or_capture(type='flag')

        elif self.current_token.type == LBRACE:
            r = self.flag_or_capture(type='capture')

        elif self.current_token.type == INPUT:
            value = self.eat(INPUT)
            cls = structure._inputs[value]
            option = None
            if self.current_token.type == SLASH:
                self.eat(SLASH)
                kw = self.current_token
                self.eat(KEYWORD)
                if kw.value not in cls.options:
                    self.raise_error(f'invalid input option \'{kw.value}\'',
                                     token=kw)
                option = kw.value
            r = cls(self.eat(ARGUMENT), option=option)

        elif self.current_token.type == KEYWORD:
            r = structure.Keyword(self.current_token)
            self.eat(KEYWORD)

        elif self.current_token.type == EOF:
            r = structure.End()
        else:
            self.raise_error(f'invalid token {self.current_token.type}')
        return r

    def phrase(self, optional=False):
        self.eat(LBRACKET if optional else LPAREN)
        parts = [self.get_part()]
        end = RBRACKET if optional else RPAREN
        while self.current_token.type != end:
            if self.current_token.type == EOF:
                raise api.CommandError(
                    f'missing {end}, got {self.current_token.type}'
                )
            parts.append(self.get_part())
        self.eat(RBRACKET if optional else RPAREN)
        if optional:
            r = structure.OptionalPhrase(parts)
        else:
            r = structure.Phrase(parts)
        return r

    def flag_or_capture(self, type):
        # flags and captures have the same type of parsing
        if type == 'flag':
            start, end, pattern = LESS, GREATER, structure.Flag
        else:
            start, end, pattern = LBRACE, RBRACE, structure.Capture
        self.eat(start)
        keywords = [structure.Keyword(self.current_token)]
        self.eat(KEYWORD)
        while self.current_token.type == KEYWORD:
            keywords.append(structure.Keyword(self.current_token))
            self.eat(KEYWORD)
        self.eat(end)
        return pattern(keywords)


class Buffer:
    """Wrap an iterable to allow lookahead functionality."""

    def __init__(self, obj):
        self.obj = obj
        self.queue = []

    def lookahead(self, n=1):
        while len(self.queue) < n:
            self.queue.append(next(self.obj))
        return self.queue[n-1]

    def __next__(self):
        try:
            if self.queue:
                r = self.queue.pop(0)
            else:
                r = next(self.obj)
            return r
        except IndexError:
            raise StopIteration


def _recursive_construct(parser, _depth, _parent, _top_level=False):
    """Construct data tree using recursion."""
    plugin = api.plugin
    lookahead = parser.lookahead(1)
    children = []
    parent_list = _parent.parent_list
    while lookahead:
        try:
            diff = lookahead.depth - _depth
        except AttributeError:
            parser.obj.raise_error('cannot have text')
        if diff > 1:
            parser.obj.raise_error(f'cannot have new data point {diff} '
                                   'levels deeper than current level')
        elif diff == 0:
            current = next(parser)
            if isinstance(current, structure.TagPattern):
                try:
                    children[-1]
                except IndexError:
                    parser.obj.raise_error('no data point to tag')
                api.append_tag_value(
                    current.data, current.value, node=children[-1], create=True
                )
            else:
                data = plugin.pre_node_creation_hook(
                    current.data, _depth,
                    parent_list
                )
                node = structure.Node(data, _depth, _parent)
                children.append(node)
        elif diff == 1:
            try:
                target = _parent if _top_level else children[-1]
                target.children.extend(
                    _recursive_construct(parser, _depth + 1, target)
                )
            except IndexError:
                parser.obj.raise_error('no parent to add deeper level to')
        else:
            break
        lookahead = parser.lookahead(1)
    for c in children:
        plugin.post_node_creation_hook(c)
    return children


def construct_tree(parser):
    """Construct a data tree using a parser's output.

    parser: [InputPatternParser]

    return: data tree [structure.Root]
    """
    parser = Buffer(parser)
    title = next(parser)
    if title is None:
        api.warning('no tree title given, defaulting to Tree')
        title = 'Tree'
    else:
        title = title.data
    root = structure.Root(title)
    initialised = False
    while isinstance(parser.lookahead(1), structure.TagPattern):
        pattern = next(parser)
        api.append_tag_value(pattern.data, pattern.value, root, create=True)
        if pattern.data == 'config':
            api.Loader.found_plugin_file(pattern.value)
            initialised = True
    if not initialised:
        api.initialise_plugins()  # no config tag found

    root.children.extend(_recursive_construct(
        parser, _depth=0, _parent=root, _top_level=True
    ))
    return root
