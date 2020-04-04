"""Parsers for data input, CLI and command signatures."""

from string import ascii_letters, digits

import sys
sys.setrecursionlimit(120)

from tagger import lexers
from tagger import structure
from tagger import api

from tagger.lexers import (
    STAR, TEXT, TAG, EQUAL, NUMBER, STRING, SEMICOLON, LESS, OR, GREATER,
    EOF, LBRACKET, ARGUMENT, RBRACKET, OPTIONAL, VARIABLE, KEYWORD,
    LPAREN, RPAREN,
)


class ParserBase:
    """Base class to perform essential parsing functions."""
    def __init__(self, lexer):
        self.lexer = lexer
        self.current_token = self.lexer.generate_token()
        self.buffer = []
        self._previous = None  # the token just consumed

    def eat(self, type, extra=''):
        if self.current_token.type == type:
            value = self.current_token.value
            self.advance_token()
        else:
            value = (' ({})'.format(self.current_token.value)
                     if self.current_token.type == KEYWORD else '')

            self.raise_error('invalid token {}{} (expected {})'.format(
                self.current_token.type, value,
                type), extra=extra
            )
        return value

    def advance_token(self):
        self._previous = self.current_token
        if self.buffer:
            self.current_token = self.buffer.pop(0)
        else:
            self.current_token = next(self.lexer)

    def lookahead(self, n=1):
        while len(self.buffer) < n:
            self.buffer.append(next(self.lexer))
        return self.buffer[n-1]

    def raise_error(self, msg, error=None, extra='', token=None):
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
        if (self.current_token.type != KEYWORD
            or self.current_token.value != keyword):
            self.raise_error('expected token KEYWORD ({})'.format(keyword))
        self.eat(KEYWORD)

    def token_is_keyword(self, token, keyword):
        return token.type == KEYWORD and token.value == keyword

    def command(self):
        current = self.current_token
        command_name = []
        current_reg = {}
        for k, v in api.registry.items():
            current_reg[tuple(k.split())] = v
        if current.type == EOF:
            return

        def error(t):
            self.raise_error(
                'invalid token {}'.format(t.type),
                token=t
            )

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
                    'unknown command \'{}\''.format(c),
                    token=current
                )
            current_reg = advance_registry_level(current_reg, c)
            command = loop_keyword(self, current_reg)
            command = command()  # instantiate the command class
        else:
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

    def scan_for_inputs_or_flags(self, phrase):
        r = {}
        for part in phrase:
            if isinstance(part, structure.Optional):
                part = part.pattern
                if isinstance(part, structure.Input):
                    r[part.argument] = None
                # ignore optional keyword
            elif isinstance(part, structure.Variable):
                part = part.pattern
                if isinstance(part, structure.Input):
                    r[part.argument] = []
                # ignore variable keyword
            elif isinstance(part, structure.Input):
                r[part.argument] = None
            elif isinstance(part, (structure.Or, structure.OptionalPhrase,
                                   structure.Phrase)):
                r.update(self.scan_for_inputs_or_flags(part.parts))
            elif isinstance(part, structure.Flag):
                r[part.name] = False
        return r

    def parse_using_signature(self, command):
        signature = api.resolve_signature(command)
        if command.disabled():
            raise api.CommandError('command \'{}\' is disabled'.format(
                command.ID
            ))
        self.sig = SignatureParser(
            lexers.SignatureLexer(signature),
            command.ID
        )
        self.signature_parts = self.sig.make_signature()
        self.parts = Buffer(iter(self.signature_parts))
        found_inputs = self.scan_for_inputs_or_flags(self.signature_parts)
        self.inputs = found_inputs
        # indicate whether optional/variable inputs/keywords were present
        # contains numerical values (0 = False, 1+ = number of occurences)
        self.pos = []
        self.current_optionals = []
        self.next_part()  # to initialise self.current_part

        c = 0
        while self.current_part.type != EOF:
            try:
                self.parse_signature_token()
            except api.CommandError as e:
                self.raise_error(
                    '{} for command \'{}\' (signature: {})'
                    .format(str(e), command.ID,
                    api.resolve_signature(command)),
                    error=api.CommandError
                )
        command.inputs = self.inputs
        return command

    def parse_signature_token(self):
        current_part = self.current_part
        if isinstance(current_part, structure.OptionalPhrase):
            self.parse_optional_signature()

        elif isinstance(current_part, structure.Phrase):
            self.parse_phrase()

        elif isinstance(current_part, structure.Or):
            found_something_not_optional = False
            # this will allow the Or to go 'unparsed' if all of the elements
            # inside it are optional i.e. OptionalPhrase or Flag or Optional
            for part in current_part.parts:
                if not isinstance(part, (structure.OptionalPhrase,
                    structure.Optional, structure.Flag)):
                    found_something_not_optional = True
                if self.part_matches_token(part):
                    self.current_part = part
                    self.parse_signature_token()
                    break
            else:  # unbroken (nothing parsed)
                if found_something_not_optional:
                    extra = (' ({})'.format(current_part.value)
                            if current_part.type == KEYWORD else '')
                    raise api.CommandError('expected token {}{}'.format(
                        current_part.type, extra
                    ))
                # don't raise an error if all were optional
            self.next_part()

        elif isinstance(current_part, structure.Flag):
            if self.flag_matches_lookahead(current_part):
                for part in current_part.parts:
                    self.eat_keyword(part.value)
                self.inputs[current_part.name] = True
            self.next_part()  # skip regardless

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
            elif self.token_is_keyword(self.current_token, current_part.value):
                # check whether token matches optional keyword's value
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
                while self.token_is_keyword(self.current_token,
                                            current_part.value):
                    self.eat_keyword(current_part.value)

                    # match the value, since KEYWORD can be any value
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
                'unexpected signature element \'{}\''
                .format(current_part.__class__.__name__)
            )

    def part_matches_token(self, part):
        if (isinstance(part, structure.Input)
            and self.current_token.type == part.type):
            return True
        if isinstance(part, structure.Flag):
            return self.flag_matches_lookahead(part)
        if self.token_is_keyword(self.current_token, part.value):
            return True
        if isinstance(part, structure.Or):
            return any(self.part_matches_token(p) for p in part.parts)
        return False

    def flag_matches_lookahead(self, flag):
        if self.current_token.type != KEYWORD:
            return False
        tokens = [self.current_token.value]
        for i in range(len(flag.parts[1:])):
            t = self.lookahead(i+1)
            if t.type != KEYWORD:
                return False
            tokens.append(t.value)
        name = '_'.join(tokens)
        return name == flag.name

    def parse_optional_signature(self):
        self.current_optionals.append(self.current_part)
        self.pos.append(0)
        self.next_part()  # initialise current optional phrase
        current = self.current_part
        if self.part_matches_token(current):
            for _ in range(len(self.current_optionals[-1].parts)):
                self.parse_signature_token()
        self.current_optionals.pop()
        self.pos.pop()
        self.next_part()
        # initialise the next token after the OptionalPhrase in the 'scope'
        # outside the current optional phrase

    def parse_phrase(self, part=None):
        if part is None:
            part = self.current_part
        self.current_optionals.append(part)
        self.pos.append(0)  # re-use the functionality for optional phrases
        self.next_part()  # initialise current phrase
        for _ in range(len(self.current_optionals[-1].parts)):
            self.parse_signature_token()
        self.current_optionals.pop()
        self.pos.pop()
        self.next_part()


class SignatureParser(ParserBase):
    """Parse tokens for command signatures and produce patterns."""
    def __init__(self, lexer, name):
        self.name = name
        ParserBase.__init__(self, lexer)

    def eat(self, *args, **kw):
        return ParserBase.eat(self, *args,
            extra='in signature\nfor command \'{}\' (signature: {})'.format(
                self.name, self.lexer.data
        ))

    def make_signature(self):
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
        return self.or_()

    def or_(self):
        r = [self.atom()]
        while self.current_token.type == OR:
            self.eat(OR)
            r.append(self.atom())
        if r[1:]:
            return structure.Or(r)
        else:
            return r[0]

    def atom(self):
        r = None
        if self.current_token.type == LBRACKET:
            r = self.phrase(optional=True)

        elif self.current_token.type == LPAREN:
            r = self.phrase()

        elif self.current_token.type == LESS:
            r = self.flag()

        elif self.current_token.type in ('NUMBER', 'STRING'):
            token = self.current_token
            self.eat(self.current_token.type)
            r = structure.Input(token, self.eat(ARGUMENT))
        elif self.current_token.type == KEYWORD:
            r = structure.Keyword(self.current_token)
            self.eat(KEYWORD)
        elif self.current_token.type == EOF:
            r = structure.End()
        else:
            self.raise_error(
                'invalid token {}'.format(self.current_token.type)
            )
        if isinstance(r, (structure.Input, structure.Keyword)):
            if self.current_token.type == OPTIONAL:
                self.eat(OPTIONAL)
                r = structure.Optional(r)
            elif self.current_token.type == VARIABLE:
                self.eat(VARIABLE)
                r = structure.Variable(r)
        return r

    def phrase(self, optional=False):
        self.eat(LBRACKET if optional else LPAREN)
        parts = [self.get_part()]
        end = RBRACKET if optional else RPAREN
        while self.current_token.type != end:
            if self.current_token.type == EOF:
                raise api.CommandError(
                    'missing {}, got {}'.format(end, self.current_token.type)
                )
            parts.append(self.get_part())
        self.eat(RBRACKET if optional else RPAREN)
        if optional:
            r = structure.OptionalPhrase(parts)
        else:
            r = structure.Phrase(parts)
        return r

    def flag(self):
        self.eat(LESS)
        flags = [structure.Keyword(self.current_token)]
        self.eat(KEYWORD)
        while self.current_token.type == KEYWORD:
            flags.append(structure.Keyword(self.current_token))
            self.eat(KEYWORD)
        self.eat(GREATER)
        return structure.Flag(structure.Phrase(flags))


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
            parser.obj.raise_error('cannot have new data point {} levels '
                'deeper than current level'.format(diff))
        elif diff == 0:
            current = next(parser)
            if isinstance(current, structure.TagPattern):
                try:
                    children[-1]
                except IndexError:
                    parser.obj.raise_error('no data point to tag')
                tags = children[-1].tags
                current.data = plugin.tag_name_hook(
                    children[-1], None, current.data
                )
                current.value = plugin.tag_value_hook(
                    children[-1], current.data, None, current.value
                )
                api.append_tag_value(
                    current.data, current.value, node=children[-1], create=True
                )
            else:
                data = plugin.pre_node_creation_hook(
                    current.data, _depth,
                    parent_list
                )
                node = structure.Node(current.data, _depth, _parent)
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
            api.log.plugin_file = pattern.value
            api.initialise_plugins()
            initialised = True
    if not initialised:
        api.initialise_plugins()  # no config tag found

    root.children.extend(_recursive_construct(
        parser, _depth=0, _parent=root, _top_level=True
    ))
    return root
