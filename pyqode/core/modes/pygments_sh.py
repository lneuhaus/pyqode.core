# -*- coding: utf-8 -*-
"""
This module contains Syntax Highlighting mode and the QSyntaxHighlighter based
on pygments.

.. note: This code is taken and adapted from the IPython project.
"""
import logging
import sys
from pygments.util import ClassNotFound
from pygments.formatters.html import HtmlFormatter
from pygments.lexer import Error
from pygments.lexer import RegexLexer
from pygments.lexer import Text
from pygments.lexers.agile import PythonLexer
from pygments.lexers.compiled import CLexer, CppLexer
from pygments.lexers.dotnet import CSharpLexer
from pygments.styles import get_style_by_name
from pygments.token import Whitespace, Comment
from pygments.styles import get_all_styles
from pygments.lexer import _TokenType
from pygments.lexers import get_lexer_for_filename, get_lexer_for_mimetype
from pyqode.core.api.syntax_highlighter import SyntaxHighlighter, ColorScheme, \
    TextBlockUserData
from pyqode.qt import QtGui
from pyqode.qt.QtCore import QRegExp


def _logger():
    """ Returns the module's logger """
    return logging.getLogger(__name__)


#: A sorted list of available pygments styles, for convenience
PYGMENTS_STYLES = sorted(list(get_all_styles()))

if hasattr(sys, 'frozen'):
    PYGMENTS_STYLES += ['darcula', 'qt']


def get_tokens_unprocessed(self, text, stack=('root',)):
    """ Split ``text`` into (tokentype, text) pairs.

        Monkeypatched to store the final stack on the object itself.
    """
    # pylint: disable=protected-access,too-many-branches
    pos = 0
    tokendefs = self._tokens
    if hasattr(self, '_saved_state_stack'):
        statestack = list(self._saved_state_stack)
    else:
        statestack = list(stack)
    try:
        statetokens = tokendefs[statestack[-1]]
    except KeyError:
        self._saved_state_stack = None
        return
    while 1:
        for rexmatch, action, new_state in statetokens:
            match = rexmatch(text, pos)
            if match:
                if type(action) is _TokenType:
                    yield pos, action, match.group()
                else:
                    for item in action(self, match):
                        yield item
                pos = match.end()
                if new_state is not None:
                    # state transition
                    if isinstance(new_state, tuple):
                        for state in new_state:
                            if state == '#pop':
                                statestack.pop()
                            elif state == '#push':
                                statestack.append(statestack[-1])
                            else:
                                statestack.append(state)
                    elif isinstance(new_state, int):
                        # pop
                        del statestack[new_state:]
                    elif new_state == '#push':
                        statestack.append(statestack[-1])
                    else:
                        assert False, "wrong state def: %r" % new_state
                    statetokens = tokendefs[statestack[-1]]
                break
        else:
            try:
                if text[pos] == '\n':
                    # at EOL, reset state to "root"
                    pos += 1
                    statestack = ['root']
                    statetokens = tokendefs['root']
                    yield pos, Text, '\n'
                    continue
                yield pos, Error, text[pos]
                pos += 1
            except IndexError:
                break
    self._saved_state_stack = list(statestack)

# Monkeypatch!
RegexLexer.get_tokens_unprocessed = get_tokens_unprocessed


# Even with the above monkey patch to store state, multiline comments do not
# work since they are stateless (Pygments uses a single multiline regex for
# these comments, but Qt lexes by line). So we need to append a state for
# comments # to the C and C++ lexers. This means that nested multiline
# comments will appear to be valid C/C++, but this is better than the
# alternative for now.
def replace_pattern(tokens, new_pattern):
    """ Given a RegexLexer token dictionary 'tokens', replace all patterns that
        match the token specified in 'new_pattern' with 'new_pattern'.
    """
    for state in tokens.values():
        for index, pattern in enumerate(state):
            if isinstance(pattern, tuple) and pattern[1] == new_pattern[1]:
                state[index] = new_pattern

# More monkeypatching!
COMMENT_START = (r'/\*', Comment.Multiline, 'comment')
COMMENT_STATE = [(r'[^*/]', Comment.Multiline),
                 (r'/\*', Comment.Multiline, '#push'),
                 (r'\*/', Comment.Multiline, '#pop'),
                 (r'[*/]', Comment.Multiline)]
replace_pattern(CLexer.tokens, COMMENT_START)
replace_pattern(CppLexer.tokens, COMMENT_START)
CLexer.tokens['comment'] = COMMENT_STATE
CppLexer.tokens['comment'] = COMMENT_STATE
CSharpLexer.tokens['comment'] = COMMENT_STATE


class PygmentsSH(SyntaxHighlighter):
    """
    This mode enable syntax highlighting using the pygments library. This is a
    generic syntax highlighter, it is slower than a native highlighter and
    does not do any code folding detection. Use it as a fallback for languages
    that do not have a native highlighter available. Check the other pyqode
    namespace packages to see what other languages are available (at the time
    of writing, only python has specialised support).

    .. warning:: There are some issues with multi-line comments, they are not
                 properly highlighted until a full re-highlight is triggered.
                 The text is automatically re-highlighted on save.
    """
    # pylint: disable=too-many-instance-attributes
    #: Mode description
    DESCRIPTION = "Apply syntax highlighting to the editor using pygments"

    @property
    def pygments_style(self):
        """
        Gets/Sets the pygments style
        """
        return self._pygments_style

    @pygments_style.setter
    def pygments_style(self, value):
        """
        Gets/Sets the pygments style
        """
        self._pygments_style = value
        self._update_style()
        # triggers a rehighlight
        self.color_scheme = ColorScheme(value)

    def __init__(self, document, lexer=None, color_scheme=None):
        super().__init__(document, color_scheme=color_scheme)
        self._pygments_style = self.color_scheme.name
        self._document = document
        self._style = None
        self._formatter = HtmlFormatter(nowrap=True)
        self._lexer = lexer if lexer else PythonLexer()

        self._brushes = {}
        self._formats = {}
        self._init_style()
        self._prev_block = None

    def _init_style(self):
        """ Init pygments style """
        self._update_style()

    def on_install(self, editor):
        """
        :type editor: pyqode.code.api.CodeEdit
        """
        self._clear_caches()
        self._update_style()
        super().on_install(editor)

    def on_state_changed(self, state):
        self.enabled = state

    def set_mime_type(self, mime_type):
        try:
            self.set_lexer_from_mime_type(mime_type)
        except:
            pass

    def set_lexer_from_filename(self, filename):
        """
        Change the lexer based on the filename (actually only the extension is
        needed)

        :param filename: Filename or extension
        """
        if filename.endswith("~"):
            filename = filename[0:len(filename) - 1]
        try:
            self._lexer = get_lexer_for_filename(filename)
            _logger().info('lexer for filename (%s): %r', filename,
                           self._lexer)
        except:
            pass  # lexer not found

    def set_lexer_from_mime_type(self, mime, **options):
        """
        Sets the pygments lexer from mime type.
        """
        self._lexer = get_lexer_for_mimetype(mime, **options)
        _logger().info('lexer for mimetype (%s): %r', mime, self._lexer)

    def highlight_block(self, text, block):
        # pylint: disable=protected-access
        original_text = text
        if self.editor and self._lexer and self.enabled:
            if block.blockNumber():
                prev_data = self._prev_block.userData()
                if prev_data:
                    if hasattr(prev_data, "syntax_stack"):
                        self._lexer._saved_state_stack = prev_data.syntax_stack
                    elif hasattr(self._lexer, '_saved_state_stack'):
                        del self._lexer._saved_state_stack

            # Lex the text using Pygments
            index = 0
            usd = block.userData()
            if usd is None:
                usd = TextBlockUserData()
                block.setUserData(usd)
            tokens = list(self._lexer.get_tokens(text))
            for token, text in tokens:
                length = len(text)
                self.setFormat(index, length, self._get_format(token))
                index += length

            if hasattr(self._lexer, '_saved_state_stack'):
                setattr(usd, "syntax_stack", self._lexer._saved_state_stack)
                # Clean up for the next go-round.
                del self._lexer._saved_state_stack

            # spaces
            text = original_text
            expression = QRegExp(r'\s+')
            index = expression.indexIn(text, 0)
            while index >= 0:
                index = expression.pos(0)
                length = len(expression.cap(0))
                self.setFormat(index, length, self._get_format(Whitespace))
                index = expression.indexIn(text, index + length)

            self._prev_block = block

    def _update_style(self):
        """ Sets the style to the specified Pygments style.
        """
        try:
            self._style = get_style_by_name(self._pygments_style)
        except ClassNotFound:
            # unknown style, also happen with plugins style when used from a
            # frozen app.
            if self._pygments_style == 'qt':
                from pyqode.core.styles import QtStyle
                self._style = QtStyle
            elif self._pygments_style == 'darcula':
                from pyqode.core.styles import DarculaStyle
                self._style = DarculaStyle
            else:
                self._style = get_style_by_name('default')
                self._pygments_style = 'default'
        self._clear_caches()

    def _clear_caches(self):
        """ Clear caches for brushes and formats.
        """
        self._brushes.clear()
        self._formats.clear()

    def _get_format(self, token):
        """ Returns a QTextCharFormat for token or None.
        """
        if token == Whitespace:
            return self.editor.whitespaces_foreground

        if token in self._formats:
            return self._formats[token]

        result = self._get_format_from_style(token, self._style)

        self._formats[token] = result
        return result

    def _get_format_from_style(self, token, style):
        """ Returns a QTextCharFormat for token by reading a Pygments style.
        """
        result = QtGui.QTextCharFormat()
        for key, value in list(style.style_for_token(token).items()):
            if value:
                if key == 'color':
                    result.setForeground(self._get_brush(value))
                elif key == 'bgcolor':
                    result.setBackground(self._get_brush(value))
                elif key == 'bold':
                    result.setFontWeight(QtGui.QFont.Bold)
                elif key == 'italic':
                    result.setFontItalic(True)
                elif key == 'underline':
                    result.setUnderlineStyle(
                        QtGui.QTextCharFormat.SingleUnderline)
                elif key == 'sans':
                    result.setFontStyleHint(QtGui.QFont.SansSerif)
                elif key == 'roman':
                    result.setFontStyleHint(QtGui.QFont.Times)
                elif key == 'mono':
                    result.setFontStyleHint(QtGui.QFont.TypeWriter)
        return result

    def _get_brush(self, color):
        """ Returns a brush for the color.
        """
        result = self._brushes.get(color)
        if result is None:
            qcolor = self._get_color(color)
            result = QtGui.QBrush(qcolor)
            self._brushes[color] = result
        return result

    @staticmethod
    def _get_color(color):
        """ Returns a QColor built from a Pygments color string.
        """
        color = str(color).replace("#", "")
        qcolor = QtGui.QColor()
        qcolor.setRgb(int(color[:2], base=16),
                      int(color[2:4], base=16),
                      int(color[4:6], base=16))
        return qcolor
