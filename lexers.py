"""Lexers for data input, CLI and command signatures."""

from string import ascii_letters, digits, whitespace

from tagger import structure

text_chars = ascii_letters + digits + '\'\\¦,.<>/?;:@#~[]{}=+-_!"£€`¬$%^&*()'
string_chars = text_chars + whitespace


class Token:
    """Represent an element of an input, holding value and type."""

    def __init__(self, type, value):
        self.type = type
        self.value = value

    def __repr__(self):
        return f'Token({repr(self.type)}, {repr(self.value)})'


# for input data
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
LBRACKET = 'LBRACKET'  # optional signature phrase
RBRACKET = 'RBRACKET'
LBRACE = 'LBRACE'      # capture keyword
RBRACE = 'RBRACE'
OPTIONAL = 'OPTIONAL'
VARIABLE = 'VARIABLE'
INPUT = 'INPUT'
ARGUMENT = 'ARGUMENT'  # in signatures 'NUMBER=index' where argument is =index
LESS = 'LESS'
GREATER = 'GREATER'
OR = 'OR'
DOT = 'DOT'
DOTDOT = 'DOTDOT'
TILDE = 'TILDE'
SLASH = 'SLASH'
LPAREN = 'LPAREN'    # non-capture, for grouping only
RPAREN = 'RPAREN'
EOF = 'EOF'

_single_char_conversion = {  # helper lookup table to make it faster to
    '[': LBRACKET,           # convert elements that are only a single
    ']': RBRACKET,           # character long
    '{': LBRACE,
    '}': RBRACE,
    '?': OPTIONAL,
    '*': VARIABLE,
    '<': LESS,
    '>': GREATER,
    '|': OR,
    '(': LPAREN,
    ')': RPAREN,
    '/': SLASH
}
_single_char_conversion_CLI = {
    '.': DOT,
    '~': TILDE,
    '/': SLASH,
    '*': STAR,
}


class LexerBase:
    """Base class to perform essential lexer functions."""

    def __init__(self, text):
        self.data = text
        self.pos = 0
        self.queued_tokens = []
        self.line = 1
        self.col = 0
        self.current = self.data[self.pos] if self.data else ''

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
                break  # reached the end of the data
        self.pos += n
        try:
            self.current = self.data[self.pos]
        except IndexError:
            self.current = ''
        return r

    def generate_token(self, *args, **kw):
        """Generate a token to be used by parser."""
        raise TypeError(
            f'generate_token not implemented in {type(self).__name__}'
        )

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
        """Tokenise one element of input data."""
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
        self.raise_error(f'invalid character \'{char}\' in data source')


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
        """Tokenise one element of CLI input."""
        char = self.current
        while char.isspace():
            self.advance()
            char = self.current
        if not char:
            return Token(EOF, None)
        if char in digits:
            return Token(NUMBER, self.collect_number())
        elif char == '-' and self.next() in digits and self.next():
            self.advance()  # skip -, but make the result negative
            return Token(NUMBER, -self.collect_number())
        elif char in ascii_letters + '_':
            return self.collect_text()
        elif char == '?':
            self.advance()
            return Token(KEYWORD, 'help')
        elif char == '\'':
            return Token(STRING, self.collect_string())
        elif char == ';':
            return Token(SEMICOLON, self.advance())
        elif char == '.' and self.next() == '.':
            return Token(DOTDOT, self.advance(2))
        elif char in _single_char_conversion_CLI:
            return Token(_single_char_conversion_CLI[char], self.advance())
        self.raise_error(f'invalid character \'{char}\' in command')


class SignatureLexer(LexerBase):
    """Tokenise a command signature."""

    def generate_token(self):
        """Tokenise one element of a command signature."""
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
        elif char in ascii_letters + '_':
            return self.collect_text()
        self.raise_error(f'invalid character \'{char}\' in command')

    def skip_whitespace(self):
        while self.current.isspace():
            self.advance()
        return self.current

    def collect_text(self, argument=False):
        r = ''
        letters = ascii_letters + digits + '_'
        while self.current and self.current in letters:
            # treat separate words as separate tokens, but allow numbers
            # within the word (not as the start character)
            r += self.advance()
        if argument:
            return r
        if r in structure._inputs:
            token = Token(INPUT, r)
        else:
            token = Token(KEYWORD, r.lower())  # only commands as lowercase
        return token

    def argument(self):
        r = self.collect_text(argument=True)
        if not r:
            self.raise_error('missing argument name')
        return r
