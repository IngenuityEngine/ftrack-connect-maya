# :coding: utf-8
# :copyright: Copyright (c) 2015 ftrack

from PySide import QtCore, QtGui

from ftrack_connect.ui.widget import entity_path
from ftrack_connect.ui.widget import entity_browser
import ftrack
import os


class ContextSelector(QtGui.QWidget):
    entityChanged = QtCore.Signal(object)

    def __init__(self, parent=None):
        super(ContextSelector, self).__init__(parent=parent)
        self._entity = None

        self.entityBrowser = entity_browser.EntityBrowser()
        self.entityBrowser.setMinimumWidth(600)
        self.entity_path = entity_path.EntityPath()
        self.entityBrowseButton = QtGui.QPushButton('Browse')

        layout = QtGui.QHBoxLayout()
        self.setLayout(layout)

        layout.addWidget(self.entity_path)
        layout.addWidget(self.entityBrowseButton)

        self.entityBrowseButton.clicked.connect(
            self._onEntityBrowseButtonClicked
        )
        self.entityChanged.connect(self.entity_path.setEntity)
        self.entityBrowser.selectionChanged.connect(
            self._onEntityBrowserSelectionChanged
        )

    def reset(self):
        current_entity = os.getenv(
            'FTRACK_TASKID',
            os.getenv('FTRACK_SHOTID')
        )
        entity = ftrack.Task(current_entity)
        self.entity_path.setEntity(entity)
        self.setEntity(entity)

    def setEntity(self, entity):
        '''Set the *entity* for the view.'''
        self._entity = entity
        self.entityChanged.emit(entity)

    def _onEntityBrowseButtonClicked(self):
        '''Handle entity browse button clicked.'''
        # Ensure browser points to parent of currently selected entity.
        if self._entity is not None:
            location = []
            try:
                parents = self._entity.getParents()
            except AttributeError:
                pass
            else:
                for parent in parents:
                    location.append(parent.getId())

            location.reverse()
            self.entityBrowser.setLocation(location)

        # Launch browser.
        if self.entityBrowser.exec_():
            selected = self.entityBrowser.selected()
            if selected:
                self.setEntity(selected[0])
            else:
                self.setEntity(None)

    def _onEntityBrowserSelectionChanged(self, selection):
        '''Handle selection of entity in browser.'''
        self.entityBrowser.acceptButton.setDisabled(True)
        if len(selection) == 1:
            entity = selection[0]

            # Prevent selecting Projects or Tasks directly under a Project to
            # match web interface behaviour.
            if isinstance(entity, ftrack.Task):
                objectType = entity.getObjectType()
                if (
                    objectType == 'Task'
                    and isinstance(entity.getParent(), ftrack.Project)
                ):
                    return

                self.entityBrowser.acceptButton.setDisabled(False)
