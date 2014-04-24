# -*- coding: utf-8 -*-
"""
This module contains interactive widgets:
    - interactive console: a text edit made to run subprocesses interactively
"""
import logging
import os

from PyQt4.QtCore import Qt, pyqtSignal, pyqtProperty as Property, QProcess
from PyQt4.QtGui import QTextEdit, QApplication, QTextCursor, QColor

from pyqode.core.frontend.client import PROCESS_ERROR_STRING


class InteractiveConsole(QTextEdit):
    """
    An interactive console is a QTextEdit specialised to run a process
    interactively

    The user will see the process outputs and will be able to
    interact with the process by typing some text, this text will be forwarded
    to the process stdin.

    You can customize the colors using the following attributes:
        - stdout_color: color of the process' stdout
        - stdin_color: color of the user inputs. Green by default
        - app_msg_color: color for custom application message (
                         process started, process finished)
        - stderr_color: color of the process' stderr

    """
    #: Signal emitted when the process has finished.
    process_finished = pyqtSignal(int)

    def __init__(self, parent=None):
        QTextEdit.__init__(self, parent)
        self._stdout_col = QColor("#404040")
        self._app_msg_col = QColor("#4040FF")
        self._stdin_col = QColor("#22AA22")
        self._stderr_col = QColor("#FF0000")
        self._usr_buffer = ""
        self._clear_on_start = True
        self.process = QProcess()
        self._merge_outputs = False
        self.process.finished.connect(self._write_finished)
        self.process.error.connect(self._write_error)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self._running = False
        self._writer = self.write
        self._user_stop = False

    def set_writer(self, writer):
        """
        Changes the writer function to handle writing to the text edit.

        A writer function must have the following prototype:

        .. code-block:: python

            def write(text_edit, text, color)
        """
        if self._writer != writer and self._writer:
            self._writer = None
        if writer:
            self._writer = writer

    def _on_stdout(self):
        txt = bytes(self.process.readAllStandardOutput()).decode('utf-8')
        logging.debug('stdout ready: %s' % txt)
        self._writer(self, txt, self.stdout_color)

    def _on_stderr(self):
        txt = bytes(self.process.readAllStandardError()).decode('utf-8')
        logging.debug('stderr ready: %s' % txt)
        self._writer(self, txt, self.stderr_color)

    def _get_background_col(self):
        p = self.palette()
        return p.color(p.Base)

    def _set_background_color(self, color):
        p = self.palette()
        p.setColor(p.Base, color)
        p.setColor(p.Text, self.stdout_color)
        self.setPalette(p)

    #: The console background color. Default is white.
    background_color = Property(
        QColor, _get_background_col, _set_background_color,
        "The console background color")

    def _get_stdout_col(self):
        return self._stdout_col

    def _set_stdout_col(self, color):
        self._stdout_col = color
        p = self.palette()
        p.setColor(p.Text, self.stdout_color)
        self.setPalette(p)

    #: Color of the process output. Default is black.
    stdout_color = Property(
        QColor, _get_stdout_col, _set_stdout_col,
        doc="The color of the process output (stdout)")

    def _get_err_col(self):
        return self._stderr_col

    def _set_err_col(self, color):
        self._stderr_col = color

    #: Color for stderr output if
    # :attr:`pyqode.widgets.QInteractiveConsole.mergeStderrWithStdout`is False.
    stderr_color = Property(
        QColor, _get_err_col, _set_err_col,
        doc="The color of the error messages (stderr)")

    def _get_stdin_col(self):
        return self._stdin_col

    def _set_stdin_col(self, color):
        self._stdin_col = color

    #: Color for user inputs. Default is green.
    stdin_color = Property(
        QColor, _get_stdin_col, _set_stdin_col,
        doc="The color of the user inputs (stdin)")

    def _get_app_message_color(self):
        return self._app_msg_col

    def _set_app_message_color(self, color):
        self._app_msg_col = color

    #: Color of the application messages (e.g.: 'Process started',
    #: 'Process finished with status %d')
    app_msg_color = Property(
        QColor, _get_app_message_color, _set_app_message_color,
        doc="Color of the application messages ('Process started', "
            "'Process finished with status %d')")

    def _get_clear_on_start(self):
        return self._clear_on_start

    def _set_clear_on_start(self, value):
        self._clear_on_start = value

    clear_on_start = Property(QColor, _get_clear_on_start, _set_clear_on_start,
                              doc='Clears output when the process starts')

    @property
    def merge_outputs(self):
        """
        Merge stderr with stdout. Default is False.

        If set to true, stderr and stdin won't have distinctive colors, i.e.
        stderr output will display with the same color as stdout.

        """
        return self._merge_outputs

    @merge_outputs.setter
    def merge_outputs(self, value):
        self._merge_outputs = value
        if value:
            self.process.setProcessChannelMode(QProcess.MergedChannels)
        else:
            self.process.setProcessChannelMode(QProcess.SeparateChannels)

    def closeEvent(self, *args, **kwargs):
        if self.process.state() == QProcess.Running:
            self.process.terminate()

    def start_process(self, process, args=None, cwd=None):
        """
        Starts a process interactively.

        :param process: Process to run
        :type process: str

        :param args: List of arguments (list of str)
        :type args: list

        :param cwd: Working directory
        :type cwd: str
        """
        if args is None:
            args = []
        if not self._running:
            if cwd:
                self.process.setWorkingDirectory(cwd)
            self._running = True
            self._process = process
            self._args = args
            if self._clear_on_start:
                self.clear()
            self._user_stop = False
            self.process.start(process, args)
            self._write_started()
        else:
            self._logger().warning('a process is already running')

    def _logger(self):
        return logging.getLogger(__name__)

    def stop_process(self):
        self._logger().debug('killing process')
        self.process.kill()
        self._user_stop = True

    def keyPressEvent(self, QKeyEvent):
        if QKeyEvent.key() == Qt.Key_Return or QKeyEvent.key() == Qt.Key_Enter:
            # send the user input to the child process
            self._usr_buffer += "\n"
            self.process.write(bytes(self._usr_buffer, "utf-8"))
            self._usr_buffer = ""
        else:
            if QKeyEvent.key() != Qt.Key_Backspace:
                txt = QKeyEvent.text()
                self._usr_buffer += txt
                self.setTextColor(self._stdin_col)
            else:
                self._usr_buffer = self._usr_buffer[
                    0:len(self._usr_buffer) - 1]
        # text is inserted here, the text color must be defined before this
        # line
        QTextEdit.keyPressEvent(self, QKeyEvent)

    def _write_finished(self, exitCode, exitStatus):
        self._writer(self, "\nProcess finished with exit code %d" % exitCode,
                     self._app_msg_col)
        self._running = False
        self._logger().debug('process finished (exitCode=%r, exitStatus=%r' %
                             (exitCode, exitStatus))
        self.process_finished.emit(exitCode)

    def _write_started(self):
        self._writer(self, "{0} {1}\n".format(
            self._process, " ".join(self._args)), self._app_msg_col)
        self._running = True
        self._logger().debug('process started')

    def _write_error(self, error):
        if self._user_stop:
            self._writer(self, '\nProcess stopped by the user',
                         self.app_msg_color)
            self._user_stop = False
        else:
            self._writer(self, "Failed to start {0} {1}\n".format(
                self._process, " ".join(self._args)), self.app_msg_color)
            err = PROCESS_ERROR_STRING[error]
            self._writer(self, "Error: %s" % err, self.stderr_color)
            self._logger().debug('process error: %s' % err)
        self._running = False

    @staticmethod
    def write(text_edit, text, color):
        """
        Default write function. Move the cursor to the end and insert text with
        the specified color.

        :param text_edit: QInteractiveConsole instance
        :type text_edit: pyqode.widgets.QInteractiveConsole

        :param text: Text to write
        :type text: str

        :param color: Desired text color
        :type color: QColor
        """
        text_edit.moveCursor(QTextCursor.End)
        text_edit.setTextColor(color)
        text_edit.insertPlainText(text)
        text_edit.moveCursor(QTextCursor.End)


if __name__ == "__main__":
    import sys
    from PyQt4.QtCore import QTimer

    if len(sys.argv) <= 1:
        app = QApplication(sys.argv)
        t = InteractiveConsole()
        t.resize(800, 600)
        t.show()
        t.start_process(sys.executable, args=[__file__, "subprocess"],
                        cwd=os.getcwd())
        # automatically stop process after 5s
        QTimer.singleShot(5000, t.stop_process)
        app.exec_()
    else:
        print("Hello from a subprocess!")
        d = input("Enter something:\n>>> ")
        sys.stderr.write('This message has been written to stderr\n')
        print("You've just typed '%s' in the QTextEdit" % d)
