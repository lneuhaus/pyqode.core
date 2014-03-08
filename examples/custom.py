#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#The MIT License (MIT)
#
#Copyright (c) <2013-2014> <Colin Duquesnoy and others, see AUTHORS.txt>
#
#Permission is hereby granted, free of charge, to any person obtaining a copy
#of this software and associated documentation files (the "Software"), to deal
#in the Software without restriction, including without limitation the rights
#to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#copies of the Software, and to permit persons to whom the Software is
#furnished to do so, subject to the following conditions:
#
#The above copyright notice and this permission notice shall be included in
#all copies or substantial portions of the Software.
#
#THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
#THE SOFTWARE.
#
"""
A simple example that shows how to setup a custom code editor widget based on
pyqode.core.QCodeEdit
"""
import sys
from pyqode.qt import QtGui
import pyqode.core


def main():
    app = QtGui.QApplication(sys.argv)
    window = QtGui.QMainWindow()
    editor = pyqode.core.QCodeEdit()
    editor.openFile(__file__)
    editor.installMode(pyqode.core.PygmentsSyntaxHighlighter(editor.document()))
    editor.installPanel(pyqode.core.SearchAndReplacePanel(),
                        position=pyqode.core.PanelPosition.TOP)
    window.setCentralWidget(editor)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
