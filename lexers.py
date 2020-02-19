"""Lexers for data input, CLI and command signatures."""

from string import (ascii_letters, digits, whitespace, ascii_uppercase,
                    ascii_lowercase)

text_chars = ascii_letters + digits + '\'\\¦,.<>/?;:@#~[]{}=+-_!"£€`¬$%^&*()'
string_chars = text_chars + whitespace


class Token:
    def __init__(self, type, value):
        self.type = type
        self.value = value

    def __repr__(self):
        return 'Token({}, {})'.format(repr(self.type), repr(self.value))


STAR = 'STAR'
TEXT = 'TEXT'
TAG = 'TAG'
EQUAL = 'EQUAL'
# for CLI lexer:
NUMBER = 'NUMBER'
STRING = 'STRING'
KEYWORD = 'KEYWORD'
SEMICOLON = 'SEMICOLON'  # to separate commands
# for command signatures:
LBRACKET = 'LBRACKET'
RBRACKET = 'RBRACKET'
OPTIONAL = 'OPTIONAL'
VARIABLE = 'VARIABLE'
ARGUMENT = 'ARGUMENT'  # in signatures 'NUMBER=index' where argument is =index
LESS = 'LESS'
GREATER = 'GREATER'
OR = 'OR'
LPAREN = 'LPAREN'
RPAREN = 'RPAREN'
EOF = 'EOF'


_single_char_conversion = {
    '[': LBRACKET,
    ']': RBRACKET,
    '?': OPTIONAL,
    '*': VARIABLE,
    '<': LESS,
    '>': GREATER,
    '|': OR,
    '(': LPAREN,
    ')': RPAREN,
}


class LexerBase:
    """Base class to perform essential lexer functions."""

    def __init__(self, text):
        self.data = text
        self.pos = 0
        self.queued_tokens = []
        self.line = 1
        self.col = 0

    def next(self, n=1):
        """Return the character n places forward of the pointer."""
        try:
            return self.data[self.pos + n]
        except IndexError:
            return ''

    def __next__(self):
        if self.queued_tokens:
            return self.queued_tokens.pop(0)
        return self.generate_token()

    def reset(self):
        self.__init__(self.data)

    @property
    def current(self):
        try:
            return self.data[self.pos]
        except IndexError:
            return ''

    def advance(self, n=1):
        """Move the pointer forward to the next character(s)."""
        r = ''
        for i in range(n):
            try:
                char = self.data[self.pos + i]
                self.col += 1
                if char == '\n':
                    self.line += 1
                    self.col = 0
                r += char
            except IndexError:
                char = ''
        self.pos += n
        return r

    def generate_token(self, *args, **kw):
        """Generate a token to be used by parser."""
        raise TypeError('generate_token not implemented in {}'
                        .format(type(self).__name__))

    def raise_error(self, msg, error=None):
        error = error or SyntaxError
        slice_start = max(0, self.pos-12)
        min_pos = min(11, self.pos)
        raise error('{} at {}.{}\n{}\n{}^'.format(
            msg.rstrip(' '), self.line,
            self.col, self.data[slice_start:self.pos+12],
            ' ' * min_pos
        ))


class InputLexer(LexerBase):
    """Tokenise a data source."""

    def asterisk(self):
        r = ''
        while self.current == '*':
            r += self.advance()
        return r

    def collect_text(self):
        r = ''
        while self.current not in {'`', '*', '\n'} and self.current:
            if self.current == '\\':
                if self.next() in {'\\', '*', '`'} and self.next():
                    # allow these characters if after backslash
                    self.advance()
                    r += self.advance()
                elif self.next() == '\n':
                    self.advance(2)
                    # skip over newlines after line continuation
            else:
                r += self.advance()
        return r.strip('\n')

    def collect_tag(self):
        self.advance()  # skip backtick `tag=value
        r = ''
        while self.current not in {'`', '*', '=', '\n'} and self.current:
            if self.current == '\\':
                if self.next() in {'\\', '*', '`', '='} and self.next():
                    # allow these characters if after backslash
                    self.advance()
                    r += self.advance()
                elif self.next() == '\n':
                    self.advance(2)
                    # skip over newlines after line continuation
            else:
                r += self.advance()
        if self.current == '=':
            self.queued_tokens.append(Token(EQUAL, self.advance()))
            self.queued_tokens.append(Token(TEXT, self.collect_text()))
        r = r.strip()
        if not r:
            self.raise_error('cannot have empty tag name')
        return r

    def generate_token(self):
        while self.current == '\n':
            self.advance()  # skip newlines
        char = self.current
        if not char:
            return Token(EOF, None)
        elif char == '*':
            return Token(STAR, self.asterisk())
        elif char == '`':
            return Token(TAG, self.collect_tag())
        elif char in string_chars:
            return Token(TEXT, self.collect_text())
        self.raise_error(
            'invalid character \'{}\' in data source'.format(char)
        )


class CLILexer(LexerBase):
    """Tokenise a CLI input."""

    def collect_number(self):
        r = ''
        while self.current and self.current in digits:
            r += self.advance()
        return int(r)  # won't fail as only digits are accepted

    def collect_text(self):
        r = ''
        letters = ascii_letters + digits + '_'
        while self.current and self.current in letters:
            # treat separate words as separate tokens, but allow numbers
            # within the word (not as the start character)
            r += self.advance()
        r = r.lower()
        return Token(KEYWORD, r)

    def collect_string(self):
        r = ''
        self.advance()  # skip opening quote (')
        while (self.current and self.current in string_chars
               and self.current != '\''):
            if self.current == '\\' and self.next() == '\'':
                self.advance()  # skip backslash and allow quote to be added
            r += self.advance()
        if self.current != '\'':
            self.raise_error('unclosed string')
        self.advance()  # skip closing quote
        return r

    def generate_token(self):
        char = self.current
        while char.isspace():
            self.advance()
            char = self.current
        if not char:
            return Token(EOF, None)
        if char in digits:
            return Token(NUMBER, self.collect_number())
        elif char in ascii_letters + '_':
            return self.collect_text()
        elif char == '?':
            self.advance()
            return Token(KEYWORD, 'help')
        elif char == '\'':
            return Token(STRING, self.collect_string())
        elif char == ';':
            return Token(SEMICOLON, self.advance())
        self.raise_error('invalid character \'{}\' in command'.format(char))


class SignatureLexer(LexerBase):
    """Tokenise a command signature."""

    def generate_token(self):
        char = self.current
        if char.isspace():
            char = self.skip_whitespace()
        if not char:
            return Token(EOF, None)
        elif char == '=':
            self.advance()  # skip '='
            return Token(ARGUMENT, self.argument())
        elif char in _single_char_conversion:
            return Token(_single_char_conversion[char], self.advance())
        elif char in ascii_uppercase:
            return self.collect_text(upper=True)
        elif char in ascii_lowercase + '_':
            return self.collect_text()
        self.raise_error('invalid character \'{}\' in command'.format(char))

    def skip_whitespace(self):
        while self.current.isspace():
            self.advance()
        return self.current

    def collect_text(self, upper=False, argument=False):
        r = ''
        letters = (ascii_uppercase if upper
                   else ascii_lowercase + digits + '_')
        while self.current and self.current in letters:
            # treat separate words as separate tokens, but allow numbers
            # within the word (not as the start character)
            r += self.advance()
        if argument:
            return r
        if upper and r in ('NUMBER', 'STRING'):
            token = Token(r, r)  # these literals have to be uppercase
        else:
            token = Token(KEYWORD, r.lower())  # only commands as lowercase
        return token

    def argument(self):
        r = self.collect_text(argument=True)
        if not r:
            self.raise_error('missing argument name')
        return r
