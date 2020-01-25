"""Parsers for data input, CLI and command signatures."""

from string import ascii_letters, digits

import lexers
import structure
import api

from lexers import (
    STAR, TEXT, TAG, EQUAL, NUMBER, STRING, ENTER, EXIT, IN, RETURN, REMOVE,
    NEW, EDIT, SEMICOLON, EOF, AT, OF, DATA, VALUE, NAME, LBRACKET, ARGUMENT,
    RBRACKET, OPTIONAL, VARIABLE, used_tokens, reserved_keywords
)
# token types that are keywords
keyword_tokens = [*used_tokens.values(), TEXT]


class ParserBase:
    """Base class to perform essential parsing functions."""
    def __init__(self, lexer):
        self.lexer = lexer
        self.current_token = self.lexer.generate_token()
        self.buffer = []

    def eat(self, type, extra=''):
        if self.current_token.type == type:
            value = self.current_token.value
            self.advance_token()
        else:
            self.raise_error('invalid token {} (expected {})'.format(
                self.current_token.type,
                type), extra=extra
            )
        return value

    def advance_token(self):
        if self.buffer:
            self.current_token = self.buffer.pop(0)
        else:
            self.current_token = next(self.lexer)

    def lookahead(self, n=1):
        while len(self.buffer) < n:
            self.buffer.append(next(self.lexer))
        return self.buffer[n-1]

    def raise_error(self, msg, error=None, extra=''):
        error = error or SyntaxError
        if extra:
            extra = ' ' + extra.rstrip(' ')
        raise error('{}{} at {}.{}\ntoken: {}'.format(
            msg.rstrip(' '), extra, self.lexer.line,
            self.lexer.col, self.current_token.value or ''
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
        commands = []
        c = self.command()
        if c is not None:
            commands.append(c)
        while self.current_token.type == SEMICOLON:
            self.eat(SEMICOLON)
            c  = self.command()
            if c is not None:
                commands.append(c)
        self.eat(EOF)
        return commands

    def eat_keyword(self, keyword):
        if keyword in reserved_keywords:
            self.eat(used_tokens[keyword])
            return
        if (self.current_token.type != TEXT
            or self.current_token.value != keyword):
            self.raise_error('expected token TEXT ({})'.format(keyword))
        self.eat(TEXT)

    def current_token_is_keyword(self, kw):
        return (self.current_token.type == TEXT
                and self.current_token.value == kw)

    def command(self):
        current = self.current_token.type
        command = None
        if current == EOF:
            return

        def error(t):
            self.raise_error('invalid token {}'.format(t))

        single_conversion = {
            ENTER: api.EnterCommand,
            RETURN: api.ReturnCommand,
            REMOVE: api.RemoveCommand,
            EXIT: api.ExitCommand,
            IN: api.InCommand
        }
        if current in single_conversion:
            self.eat(current)
            command = single_conversion[current]()

        elif current == NEW:
            self.eat(NEW)
            if self.current_token.type == DATA:
                self.eat(DATA)
                command = api.NewDataCommand()

            elif self.current_token.type == TAG:
                self.eat(TAG)
                command = api.NewTagCommand()
            # if this doesn't return, self.raise_error will be called
            # at the bottom

        elif current == EDIT:
            self.eat(EDIT)
            if self.current_token.type == DATA:
                self.eat(DATA)
                command = api.EditDataCommand()

            elif self.current_token.type == TAG:
                self.eat(TAG)
                if self.current_token.type == NAME:
                    self.eat(NAME)
                    command = api.EditTagNameCommand()

                elif self.current_token.type == VALUE:
                    self.eat(VALUE)
                    command = api.EditTagValueCommand()
            # if this 2nd level if statement ends, the error will be raised
            # at the end of the method still

        elif current == TEXT:
            name = self.eat(TEXT)
            command = api.resolve(name)()

        if command is None:
            error(current)

        return self.parse_using_signature(command)

    def next_part(self):
        try:
            if self.current_optionals:
                self.current_part = (self.current_optionals[-1]
                                     .parts[self.pos[-1]])
                self.pos[-1] += 1
                return
            self.current_part = next(self.parts)
        except (StopIteration, IndexError):
            self.current_part = structure.End()

    def parse_using_signature(self, command):
        self.sig = SignatureParser(
            lexers.SignatureLexer(command.signature),
            command.ID
        )
        self.parts = Buffer(iter(self.sig.make_signature()))
        self.pos = []
        self.current_optionals = []
        self.inputs = {}
        self.next_part()  # to initialise self.current_part

        while self.current_part.type != EOF:
            try:
                self.parse_signature_token()
            except api.CommandError as e:
                self.raise_error(
                    '{} for command \'{}\' (signature: {})'
                    .format(str(e), command.ID, command.signature),
                    error=api.CommandError
                )

        command.inputs = self.inputs
        return command

    def parse_signature_token(self):
        current_part = self.current_part
        if isinstance(current_part, structure.OptionalPhrase):
            self.parse_optional_signature()

        elif isinstance(current_part, structure.Optional):
            current_part = current_part.pattern
            if (isinstance(current_part, structure.Input)
                and current_part.type == self.current_token.type):
                self.inputs[current_part.argument] = (
                    self.eat(
                        current_part.type,
                        extra='for input \'{}\''.format(
                            current_part.argument
                        )
                ))

            elif (self.current_token.value == current_part.value
                  and self.current_token.type in keyword_tokens):
                self.eat_keyword(current_part.value)
            self.next_part()  # skip regardless (since this is optional)

        elif isinstance(current_part, structure.Variable):
            current_part = current_part.pattern
            if isinstance(current_part, structure.Input):
                while self.current_token.type == current_part.type:
                    if current_part.argument not in self.inputs:
                        self.inputs[current_part.argument] = []
                    self.inputs[current_part.argument].append(
                        self.eat(
                            current_part.type,
                            extra='for input \'{}\''.format(
                                current_part.argument)
                        )
                    )  # all variable arguments go into a list
            else:  # it's a keyword
                while (self.current_token.value == current_part.value
                       and self.current_token.type in keyword_tokens):
                    if self.current_token.type == TEXT:
                        self.eat_keyword(current_part.value)
                        # match the value, not type since TEXT can be any value
            self.next_part()

        elif isinstance(current_part, structure.Input):
            self.inputs[current_part.argument] = (
                self.eat(
                    current_part.type,
                    extra='for input \'{}\''.format(current_part.argument))
            )  # attempt to match string or number
            self.next_part()

        elif isinstance(current_part, structure.Keyword):
            self.eat_keyword(current_part.value)
            self.next_part()

        else:
            raise api.CommandError(
                'unexpected token {}'.format(self.current_token.type)
            )

    def parse_optional_signature(self):
        self.current_optionals.append(self.current_part)
        self.pos.append(0)
        self.next_part()  # initialise current optional phrase
        current = self.current_part
        if (isinstance(current, structure.Input)
            and self.current_token.type == current.type):
            for _ in range(len(self.current_optionals[-1].parts)):
                self.parse_signature_token()
        elif (current.type in [*used_tokens.values(), TEXT]
              and self.current_token.value == current.value):
            for _ in range(len(self.current_optionals[-1].parts)):
                self.parse_signature_token()
        self.current_optionals.pop()
        self.pos.pop()
        self.next_part()
        # initialise the next token after the OptionalPhrase in the 'scope'
        # outside the current optional phrase


class SignatureParser(ParserBase):
    """Parse tokens for command signatures and produce patterns."""
    def __init__(self, lexer, name):
        self.name = name
        ParserBase.__init__(self, lexer)

    def eat(self, *args, **kw):
        return ParserBase.eat(self, *args,
            extra='in signature\nfor command \'{}\' (signature: {})'.format(
                self.name, self.lexer.data
        )
        )

    def make_signature(self):
        parts = [self.get_part()]
        if parts[-1] == None:
            return []
        while self.current_token.type != EOF:
            part = self.get_part()
            if part is None:
                break
            parts.append(part)
        return parts

    def get_part(self):
        optional, variable, r = False, False, None
        if self.current_token.type == OPTIONAL:
            self.eat(OPTIONAL)
            optional = True
        elif self.current_token.type == VARIABLE:
            self.eat(VARIABLE)
            variable = True
        if self.current_token.type == LBRACKET:
            r = self.optional_phrase()

        elif self.current_token.type in ('NUMBER', 'STRING'):
            token = self.current_token
            self.eat(self.current_token.type)
            r = structure.Input(token, self.eat(ARGUMENT))
        elif self.current_token.type == TEXT:
            r = structure.Keyword(self.current_token)
            self.eat(TEXT)
        elif self.current_token.type == EOF:
            r = structure.End()
        else:
            self.raise_error(
                'invalid token {}'.format(self.current_token.type)
            )
        if isinstance(r, (structure.Input, structure.Keyword)):
            if optional:
                r = structure.Optional(r)
            elif variable:
                r = structure.Variable(r)
        return r

    def optional_phrase(self):
        self.eat(LBRACKET)
        parts = [self.get_part()]
        while self.current_token.type != RBRACKET:
            if self.current_token.type == EOF:
                raise api.CommandError(
                    'missing RBRACKET, got {}'.format(self.current_token.type)
                )
            parts.append(self.get_part())
        self.eat(RBRACKET)
        r = structure.OptionalPhrase(parts)
        return r


class Buffer:
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
    import plugin
    lookahead = parser.lookahead(1)
    children = []
    parent_list = _parent.parent_list
    while lookahead:
        try:
            diff = lookahead.depth - _depth
        except AttributeError:
            parser.obj.raise_error('cannot have text')
        # print('depth:', _depth, '   diff:', diff)
        if diff > 1:
            parser.obj.raise_error('cannot have new data point {} levels '
                'deeper than current level'.format(diff))
        elif diff == 0:
            current = next(parser)
            if isinstance(current, structure.TagPattern):
                try:
                    children[-1].tags[current.data] = current.value
                except IndexError:
                    parser.obj.raise_error('no data point to tag')
            else:
                data = plugin.pre_node_creation_hook(
                    current.data, _depth,
                    parent_list
                )
                node = structure.Node(current.data, _depth, _parent)
                plugin.post_node_creation_hook(node)
                children.append(node)
                # print('added', children[-1])
        elif diff == 1:
            try:
                target = _parent if _top_level else children[-1]
                target.children.extend(
                    _recursive_construct(parser, _depth + 1, target)
                )
            except IndexError:
                # print('error going deeper:', _parent, children)
                parser.obj.raise_error('no parent to add deeper level to')
        else:
            break
        lookahead = parser.lookahead(1)
    return children


def construct_tree(parser):
    parser = Buffer(parser)
    title = next(parser).data
    if isinstance(parser.lookahead(1), structure.TextPattern):
        author = next(parser).data
    if isinstance(parser.lookahead(1), structure.TextPattern):
        desc = next(parser).data
    other = {}
    while isinstance(parser.lookahead(1), structure.TagPattern):
        pattern = next(parser)
        other[pattern.data] = pattern.value
    root = structure.Root(title, author, desc, other)
    root.children.extend(_recursive_construct(
        parser, _depth=0, _parent=root, _top_level=True
    ))
    return root
