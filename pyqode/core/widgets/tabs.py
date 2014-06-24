# -*- coding: utf-8 -*-
"""
This module contains the implementation of a tab widget specialised to
show code editor tabs.
"""
import logging
import os
from pyqode.core.ui.dlg_unsaved_files_ui import Ui_Dialog
from pyqode.core.modes.filewatcher import FileWatcherMode
from pyqode.core.qt import QtCore, QtWidgets
from pyqode.core.qt.QtWidgets import QDialog, QTabBar, QTabWidget
# pylint: disable=too-many-instance-attributes, missing-docstring
# pylint: disable=protected-access


def _logger():
    return logging.getLogger(__name__)


class DlgUnsavedFiles(QDialog, Ui_Dialog):
    """
    This dialog shows the list of unsaved file in the CodeEditTabWidget.

    Use can choose to:
        - cancel: nothing changed, no tab will be closed
        - save all/save selected: save the selected files or all files
        - discard all changes: nothing will be saved but all tabs will be
        closed.

    """
    def __init__(self, parent, files=None):
        if files is None:
            files = []
        QtWidgets.QDialog.__init__(self, parent)
        Ui_Dialog.__init__(self)
        self.setupUi(self)
        self.bt_save_all = self.buttonBox.button(
            QtWidgets.QDialogButtonBox.SaveAll)
        self.bt_save_all.clicked.connect(self.accept)
        self.discarded = False
        self.bt_discard = self.buttonBox.button(
            QtWidgets.QDialogButtonBox.Discard)
        self.bt_discard.clicked.connect(self._set_discarded)
        self.bt_discard.clicked.connect(self.accept)
        for file in files:
            self._add_file(file)
        self.listWidget.itemSelectionChanged.connect(
            self._on_selection_changed)
        self._on_selection_changed()

    def _add_file(self, path):
        icon = QtWidgets.QFileIconProvider().icon(QtCore.QFileInfo(path))
        item = QtWidgets.QListWidgetItem(icon, path)
        self.listWidget.addItem(item)

    def _set_discarded(self):
        self.discarded = True

    def _on_selection_changed(self):
        nb_items = len(self.listWidget.selectedItems())
        if nb_items == 0:
            self.bt_save_all.setText("Save")
            self.bt_save_all.setEnabled(False)
        else:
            self.bt_save_all.setEnabled(True)
            self.bt_save_all.setText("Save selected")
            if nb_items == self.listWidget.count():
                self.bt_save_all.setText("Save all")


class ClosableTabBar(QTabBar):
    """
    Custom QTabBar that can be closed using a mouse middle click.
    """
    def __init__(self, parent):
        QtWidgets.QTabBar.__init__(self, parent)
        self.setTabsClosable(True)

    def mousePressEvent(self, event):  # pylint: disable=invalid-name
        QtWidgets.QTabBar.mousePressEvent(self, event)
        if event.button() == QtCore.Qt.MiddleButton:
            self.parentWidget().tabCloseRequested.emit(self.tabAt(
                event.pos()))


class TabWidget(QTabWidget):
    """
    QTabWidget specialised to hold CodeEdit instances (or any other
    object that has the same interace).

    It ensures that there is only one open editor tab for a specific file path,
    it adds a few utility methods to quickly manipulate the current editor
    widget. It will automatically rename tabs that share the same base filename
    to include their distinctive parent directory.

    It handles tab close requests automatically and show a dialog box when
    a dirty tab widget is being closed. It also adds a convenience QTabBar
    with a "close", "close others" and "close all" menu. (You can add custom
    actions by using the addAction and addSeparator methods).

    It exposes a variety of signal and slots for a better integration with
    your applications( dirty_changed, save_current, save_all, close_all,
    close_current, close_others).

    """
    #: Signal emitted when a tab dirty flag changed
    dirty_changed = QtCore.Signal(bool)
    #: Signal emitted when the last tab has been closed
    last_tab_closed = QtCore.Signal()
    #: Signal emitted when a tab has been closed
    tab_closed = QtCore.Signal(QtWidgets.QWidget)

    @property
    def active_editor(self):
        """
        Returns the current editor widget or None if the current tab widget is
        not a subclass of CodeEdit or if there is no open tab.
        """
        return self._current

    def __init__(self, parent):
        QtWidgets.QTabWidget.__init__(self, parent)
        self._current = None
        self.currentChanged.connect(self._on_current_changed)
        self.tabCloseRequested.connect(self._on_tab_close_requested)
        tab_bar = ClosableTabBar(self)
        tab_bar.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        tab_bar.customContextMenuRequested.connect(self._show_tab_context_menu)
        self.setTabBar(tab_bar)
        self.tab_bar = tab_bar
        self._context_mnu = QtWidgets.QMenu()
        for name, slot in [('Close', self.close),
                           ('Close others', self.close_others),
                           ('Close all', self.close_all)]:
            qaction = QtWidgets.QAction(name, self)
            qaction.triggered.connect(slot)
            self._context_mnu.addAction(qaction)
            self.addAction(qaction)
        # keep a list of widgets (to avoid PyQt bug where
        # the C++ class loose the wrapped obj type).
        self._widgets = []

    @QtCore.Slot()
    def close(self):
        """
        Closes the active editor
        """
        self.tabCloseRequested.emit(self.currentIndex())

    @QtCore.Slot()
    def close_others(self):
        """
        Closes every editors tabs except the current one.
        """
        current_widget = self.currentWidget()
        self._try_close_dirty_tabs(exept=current_widget)
        i = 0
        while self.count() > 1:
            widget = self._widgets[i]
            if widget != current_widget:
                self.removeTab(i)
            else:
                i = 1

    @QtCore.Slot()
    def close_all(self):
        """
        Closes all editors
        """
        if self._try_close_dirty_tabs():
            while self.count():
                widget = self._widgets[0]
                self.removeTab(0)
                self.tab_closed.emit(widget)
            return True
        return False

    def _ensure_unique_name(self, code_edit, name):
        if name is not None:
            code_edit._tab_name = name
        else:
            code_edit._tab_name = code_edit.file.name
        file_name = code_edit.file.name
        if self._name_exists(file_name):
            file_name = self._rename_duplicate_tabs(
                code_edit, code_edit.file.name, code_edit.file.path)
            code_edit._tab_name = file_name

    @QtCore.Slot()
    def save_current(self, path=None):
        """
        Save current editor content. Leave file to None to erase the previous
        file content. If the current editor's file_path is None and path
        is None, the function will call
        ``QtWidgets.QFileDialog.getSaveFileName`` to get a valid save filename.

        """
        try:
            if not path and not self._current.file.path:
                path, filter = QtWidgets.QFileDialog.getSaveFileName(
                    self, 'Choose destination path')
                if not path:
                    return False
            old_path = self._current.file.path
            try:
                self._current.file.save(path)
            except AttributeError:
                self._current.save(path)
            # path (and icon) may have changed
            code_edit = self._current
            if path and old_path != path:
                self._ensure_unique_name(code_edit, code_edit.file.name)
                self.setTabText(self.currentIndex(), code_edit._tab_name)
                ext = os.path.splitext(path)[1]
                old_ext = os.path.splitext(old_path)[1]
                if ext != old_ext:
                    icon = QtWidgets.QFileIconProvider().icon(
                        QtCore.QFileInfo(code_edit.file.path))
                    self.setTabIcon(self.currentIndex(), icon)
            return True
        except AttributeError:  # not an editor widget
            pass
        return False

    @QtCore.Slot()
    def save_all(self):
        """
        Save all editors.
        """
        initial_index = self.currentIndex()
        for i in range(self.count()):
            try:
                self.setCurrentIndex(i)
                self.save_current()
            except AttributeError:
                pass
        self.setCurrentIndex(initial_index)

    def addAction(self, action):  # pylint: disable=invalid-name
        """
        Adds an action to the TabBar context menu

        :param action: QAction to append
        """
        self._context_mnu.addAction(action)

    def add_separator(self):
        """
        Adds a separator to the TabBar context menu.

        :returns The separator action.
        """
        return self._context_mnu.addSeparator()

    def index_from_filename(self, path):
        """
        Checks if the path is already open in an editor tab.

        :returns: The tab index if found or -1
        """
        if path:
            for i, widget in enumerate(self._widgets):
                try:
                    if widget.file.path == path:
                        return i
                except AttributeError:
                    pass  # not an editor widget
        return -1

    @staticmethod
    def _del_code_edit(code_edit):
        try:
            code_edit.backend.stop()
        except AttributeError:
            pass
        # code_edit.deleteLater()
        # del code_edit

    def add_code_edit(self, code_edit, name=None):
        """
        Adds a code edit tab, sets its text as the editor.file.name and
        sets it as the active tab.

        The widget is only added if there is no other editor tab open with the
        same filename, else the already open tab is set as current.

        :param code_edit: The code editor widget tab to append
        :type code_edit: pyqode.core.api.CodeEdit

        :param icon: The tab widget icon. Optional
        :type icon: QtWidgets.QIcon or None

        :return: Tab index
        """
        index = self.index_from_filename(code_edit.file.path)
        if index != -1:
            # already open, just show it
            self.setCurrentIndex(index)
            # no need to keep this instance
            self._del_code_edit(code_edit)
            return -1
        self._ensure_unique_name(code_edit, name)
        index = self.addTab(code_edit, code_edit.file.icon, code_edit._tab_name)
        self.setCurrentIndex(index)
        self.setTabText(index, code_edit._tab_name)
        try:
            code_edit.setFocus(True)
        except TypeError:
            # PySide
            code_edit.setFocus()
        try:
            file_watcher = code_edit.modes.get(FileWatcherMode)
        except (KeyError, AttributeError):
            # not installed
            pass
        else:
            file_watcher.file_deleted.connect(self._on_file_deleted)
        return index

    def addTab(self, elem, icon, name):  # pylint: disable=invalid-name
        """
        Extends QTabWidget.addTab to keep an internal list of added tabs.
        """
        self._widgets.append(elem)
        return super().addTab(elem, icon, name)

    def _name_exists(self, name):
        """
        Checks if we already have an opened tab with the same name.
        """
        for i in range(self.count()):
            if self.tabText(i) == name:
                return True
        return False

    def _save_editor(self, code_edit):
        path = None
        if not code_edit.file.path:
            path = QtWidgets.QFileDialog.getSaveFileName(
                self, 'Choose destination path')
        if path:
            code_edit.file.save(path)

    def _rename_duplicate_tabs(self, current, name, path):
        """
        Rename tabs whose title is the same as the name
        """
        for i in range(self.count()):
            if self.widget(i)._tab_name == name and self.widget(i) != current:
                file_path = self._widgets[i].file.path
                if file_path:
                    parent_dir = os.path.split(os.path.abspath(
                        os.path.join(file_path, os.pardir)))[1]
                    new_name = os.path.join(parent_dir, name)
                    self.setTabText(i, new_name)
                    self._widgets[i]._tab_name = new_name
                break
        if path:
            parent_dir = os.path.split(os.path.abspath(
                os.path.join(path, os.pardir)))[1]
            return os.path.join(parent_dir, name)
        else:
            return name

    def _on_current_changed(self, index):
        widget = self._widgets[index]
        if self._current:
            # needed if the user set save_on_focus_out to True which change
            # the dirty flag
            self._on_dirty_changed(self._current.dirty)
        self._current = widget
        try:
            if self._current:
                self._current.dirty_changed.connect(self._on_dirty_changed)
                self._on_dirty_changed(self._current.dirty)
                self._current.setFocus()
        except AttributeError:
            pass  # not an editor widget

    def removeTab(self, index):  # pylint: disable=invalid-name
        """
        Removes tab at index ``index``.

        This method will emits tab_closed for the removed tab.

        """
        QTabWidget.removeTab(self, index)
        widget = self._widgets.pop(index)
        if widget == self._current:
            self._current = None
        self.tab_closed.emit(widget)
        self._del_code_edit(widget)

    def _on_tab_close_requested(self, index):
        widget = self._widgets[index]
        try:
            if not widget.dirty:
                self.removeTab(index)
            else:
                dlg = DlgUnsavedFiles(
                    self, files=[widget.file.path if widget.file.path else
                                 widget._tab_name])
                if dlg.exec_() == dlg.Accepted:
                    if not dlg.discarded:
                        self._save_editor(widget)
                    self.removeTab(index)
        except AttributeError:
            _logger().warning('Failed to close tab %d', index)
        if self.count() == 0:
            self.last_tab_closed.emit()

    def _show_tab_context_menu(self, position):
        self._context_mnu.popup(self.mapToGlobal(position))

    def _try_close_dirty_tabs(self, exept=None):
        """
        Tries to close dirty tabs. Uses DlgUnsavedFiles to ask the user
        what he wants to do.
        """
        widgets, filenames = self._collect_dirty_tabs(exept=exept)
        if not len(filenames):
            return True
        dlg = DlgUnsavedFiles(self, files=filenames)
        if dlg.exec_() == dlg.Accepted:
            if not dlg.discarded:
                for item in dlg.listWidget.selectedItems():
                    filename = item.text()
                    widget = None
                    for widget in widgets:
                        if widget.file.path == filename:
                            break
                    if widget != exept:
                        widget.file.save()
                        self.removeTab(self.indexOf(widget))
            return True
        return False

    def _collect_dirty_tabs(self, exept=None):
        """
        Collects the list of dirty tabs
        """
        widgets = []
        filenames = []
        for i in range(self.count()):
            widget = self._widgets[i]
            try:
                if widget.dirty and widget != exept:
                    widgets.append(widget)
                    filenames.append(widget.file.path)
            except AttributeError:
                pass
        return widgets, filenames

    def _on_dirty_changed(self, dirty):
        """
        Adds a star in front of a dirtt tab and emits dirty_changed.
        """
        try:
            title = self._current._tab_name
            index = self.indexOf(self._current)
            if dirty:
                self.setTabText(index, "* " + title)
            else:
                self.setTabText(index, title)
        except AttributeError:
            pass
        self.dirty_changed.emit(dirty)

    def closeEvent(self, event):  # pylint: disable=invalid-name
        """
        On close, we try to close dirty tabs and only process the close
        event if all dirty tabs were closed by the user.
        """
        if not self.close_all():
            event.ignore()
        else:
            event.accept()

    def _on_file_deleted(self, editor):
        """
        Removes deleted files from the tab widget.
        """
        self.removeTab(self.indexOf(editor))