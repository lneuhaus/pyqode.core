# -*- coding: utf-8 -*-
"""
This module contains the main window implementation.
"""
import mimetypes
import os
import sys

from pyqode.qt import QtCore
from pyqode.qt import QtWidgets

from pyqode.core import frontend
from pyqode.core.frontend import modes
from pyqode.core.frontend import widgets

from .editor import GenericCodeEdit
from .ui.main_window_ui import Ui_MainWindow


class MainWindow(QtWidgets.QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        # Load our UI (made in Qt Designer)
        self.setupUi(self)
        self.setup_recent_files_menu()
        self.setup_actions()
        self.setup_mimetypes()
        self.setup_status_bar_widgets()
        self.on_current_tab_changed()
        self.pygments_style = 'qt'

    def setup_status_bar_widgets(self):
        self.lbl_filename = QtWidgets.QLabel()
        self.lbl_encoding = QtWidgets.QLabel()
        self.lbl_cursor_pos = QtWidgets.QLabel()
        self.statusbar.addPermanentWidget(self.lbl_filename, 200)
        self.statusbar.addPermanentWidget(self.lbl_encoding, 20)
        self.statusbar.addPermanentWidget(self.lbl_cursor_pos, 20)

    def setup_actions(self):
        """ Connects slots to signals """
        self.actionOpen.triggered.connect(self.on_open)
        self.actionNew.triggered.connect(self.on_new)
        self.actionSave.triggered.connect(self.tabWidget.save_current)
        self.actionSave_as.triggered.connect(self.on_save_as)
        self.actionClose_tab.triggered.connect(self.tabWidget.close)
        self.actionClose_other_tabs.triggered.connect(
            self.tabWidget.close_others)
        self.actionClose_all_tabs.triggered.connect(self.tabWidget.close_all)
        self.actionQuit.triggered.connect(QtWidgets.QApplication.instance().quit)
        self.tabWidget.currentChanged.connect(self.on_current_tab_changed)
        self.actionAbout.triggered.connect(self.on_about)

    def setup_recent_files_menu(self):
        """ Setup the recent files menu and manager """
        self.recent_files_manager = widgets.RecentFilesManager(
            'pyqode', 'notepad')
        self.menu_recents = widgets.MenuRecentFiles(
            self.menuFile, title='Recents',
            recent_files_manager=self.recent_files_manager)
        self.menu_recents.open_requested.connect(self.open_file)
        self.menuFile.insertMenu(self.actionSave, self.menu_recents)
        self.menuFile.insertSeparator(self.actionSave)

    def setup_mimetypes(self):
        """ Setup additional mime types. """
        # setup some specific mimetypes
        mimetypes.add_type('text/xml', '.ui')  # qt designer ui forms
        mimetypes.add_type('text/x-rst', '.rst')  # rst docs
        mimetypes.add_type('text/x-cython', '.pyx')  # cython impl files
        mimetypes.add_type('text/x-cython', '.pxd')  # cython def files
        # cobol files
        for ext in ['.cbl', '.cob', '.cpy']:
            mimetypes.add_type('text/x-cobol', ext)
            mimetypes.add_type('text/x-cobol', ext.upper())
        if sys.platform == 'win32':
            # windows systems do not have a mimetypes for most of the codes
            # python, you have to add them all explicitely on windows,
            # otherwise there won't be any syntax highlighting
            mimetypes.add_type('text/x-python', '.py')
            mimetypes.add_type('text/x-python', '.pyw')
            mimetypes.add_type('text/x-c', '.c')
            mimetypes.add_type('text/x-c', '.h')
            mimetypes.add_type('text/x-cpp', '.hpp')
            mimetypes.add_type('text/x-cpp', '.cpp')
            mimetypes.add_type('text/x-cpp', '.cxx')

    def setup_mnu_edit(self, editor):
        self.menuEdit.addActions(editor.actions())
        self.menuEdit.addSeparator()
        self.setup_mnu_style(editor)

    def setup_mnu_modes(self, editor):
        for k, v in sorted(frontend.get_modes(editor).items()):
            a = QtWidgets.QAction(self.menuModes)
            a.setText(k)
            a.setCheckable(True)
            a.setChecked(True)
            a.changed.connect(self.on_mode_state_changed)
            a.mode = v
            self.menuModes.addAction(a)

    def setup_mnu_panels(self, editor):
        for zones, dic in sorted(frontend.get_panels(editor).items()):
            for k, v in dic.items():
                a = QtWidgets.QAction(self.menuModes)
                a.setText(k)
                a.setCheckable(True)
                a.setChecked(True)
                a.changed.connect(self.on_panel_state_changed)
                a.panel = v
                self.menuPanels.addAction(a)

    def setup_mnu_style(self, editor):
        """ setup the style menu for an editor tab """
        menu = QtWidgets.QMenu('Styles', self.menuEdit)
        group = QtWidgets.QActionGroup(self)
        current_style = frontend.get_mode(
            editor, modes.PygmentsSyntaxHighlighter).pygments_style
        group.triggered.connect(self.on_style_changed)
        for s in sorted(modes.PYGMENTS_STYLES):
            a = QtWidgets.QAction(menu)
            a.setText(s)
            a.setCheckable(True)
            if s == current_style:
                a.setChecked(True)
            group.addAction(a)
            menu.addAction(a)
        self.menuEdit.addMenu(menu)

    def closeEvent(self, QCloseEvent):
        """
        Delegates the close event to the tabWidget to be sure we do not quit
        the application while there are some still some unsaved tabs.
        """
        self.tabWidget.closeEvent(QCloseEvent)

    @QtCore.Slot(str)
    def open_file(self, path):
        """
        Creates a new GenericCodeEdit, opens the requested file and adds it
        to the tab widget.

        :param path: Path of the file to open
        """
        if path:
            index = self.tabWidget.index_from_filename(path)
            if index == -1:
                editor = GenericCodeEdit(self)
                editor.file_path = path
                editor.cursorPositionChanged.connect(
                    self.on_cursor_pos_changed)
                self.tabWidget.add_code_edit(editor)
                self.recent_files_manager.open_file(path)
                self.menu_recents.update_actions()
                frontend.open_file(editor, path)
            else:
                self.tabWidget.setCurrentIndex(index)
            self.refresh_color_scheme()

    @QtCore.Slot()
    def on_new(self):
        """
        Add a new empty code editor to the tab widget
        """
        self.tabWidget.add_code_edit(GenericCodeEdit(self), 'New document')
        self.refresh_color_scheme()

    @QtCore.Slot()
    def on_open(self):
        """
        Shows an open file dialog and open the file if the dialog was
        accepted.

        """
        filename, filter = QtWidgets.QFileDialog.getOpenFileName(self, 'Open')
        if filename:
            self.open_file(filename)

    @QtCore.Slot()
    def on_save_as(self):
        """
        Save the current editor document as.
        """
        path = self.tabWidget.currentWidget().file_path
        path = os.path.dirname(path) if path else ''
        filename, filter = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Save', path)
        if filename:
            self.tabWidget.save_current(filename)
            self.recent_files_manager.open_file(filename)
            self.menu_recents.update_actions()

    @QtCore.Slot()
    def on_current_tab_changed(self):
        self.menuEdit.clear()
        self.menuModes.clear()
        self.menuPanels.clear()
        editor = self.tabWidget.currentWidget()
        self.menuEdit.setEnabled(editor is not None)
        self.menuModes.setEnabled(editor is not None)
        self.menuPanels.setEnabled(editor is not None)
        self.actionSave.setEnabled(editor is not None)
        self.actionSave_as.setEnabled(editor is not None)
        self.actionClose_tab.setEnabled(editor is not None)
        self.actionClose_all_tabs.setEnabled(editor is not None)
        self.actionClose_other_tabs.setEnabled(
            editor is not None and self.tabWidget.count() > 1)
        if editor:
            self.setup_mnu_edit(editor)
            self.setup_mnu_modes(editor)
            self.setup_mnu_panels(editor)
            self.lbl_cursor_pos.setText('%d:%d' % frontend.cursor_position(
                editor))
            self.lbl_encoding.setText(editor.file_encoding)
            self.lbl_filename.setText(editor.file_path)
        else:
            self.lbl_cursor_pos.clear()
            self.lbl_encoding.clear()
            self.lbl_filename.clear()

    def refresh_color_scheme(self):
        style = self.pygments_style
        for i in range(self.tabWidget.count()):
            editor = self.tabWidget.widget(i)
            frontend.get_mode(
                editor, modes.PygmentsSyntaxHighlighter).pygments_style = style
            frontend.get_mode(
                editor, modes.CaretLineHighlighterMode).refresh()

    @QtCore.Slot(QtWidgets.QAction)
    def on_style_changed(self, action):
        self.pygments_style = action.text()
        self.refresh_color_scheme()

    @QtCore.Slot()
    def on_panel_state_changed(self):
        action = self.sender()
        action.panel.enabled = action.isChecked()

    @QtCore.Slot()
    def on_mode_state_changed(self):
        action = self.sender()
        action.mode.enabled = action.isChecked()

    @QtCore.Slot()
    def on_about(self):
        QtWidgets.QMessageBox.about(
            self, 'pyQode notepad',
            'This notepad application is an example of what you can do with '
            'pyqode.core.')

    @QtCore.Slot()
    def on_cursor_pos_changed(self):
        if self.tabWidget.currentWidget():
            self.lbl_cursor_pos.setText('%d:%d' % frontend.cursor_position(
                self.tabWidget.currentWidget()))