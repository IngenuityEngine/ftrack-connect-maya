# :coding: utf-8
# :copyright: Copyright (c) 2015 ftrack

import getpass
import sys
import pprint
import logging
import re
import os
import traceback

import ftrack_api
import ftrack_connect.application
import ftrack_connect_maya

import arkFTrack
import cOS
import settingsManager
globalSettings = settingsManager.globalSettings()

class LaunchApplicationAction(object):
    '''Discover and launch maya.'''

    identifier = 'ftrack-connect-launch-maya'

    def __init__(self, application_store, launcher, session):
        '''Initialise action with *applicationStore* and *launcher*.

        *applicationStore* should be an instance of
        :class:`ftrack_connect.application.ApplicationStore`.

        *launcher* should be an instance of
        :class:`ftrack_connect.application.ApplicationLauncher`.

        '''
        super(LaunchApplicationAction, self).__init__()

        self.logger = logging.getLogger(
            __name__ + '.' + self.__class__.__name__
        )

        self.application_store = application_store
        self.launcher = launcher
        self.session = session

    def is_valid_selection(self, selection):
        '''Return true if the selection is valid.'''
        if (
            len(selection) != 1 or
            selection[0]['entityType'] != 'task'
        ):
            return False

        entity = selection[0]
        task = self.session.get('Task', entity['entityId'])

        if task is None:
            return False

        return True

    def register(self):
        '''Register discover actions on logged in user.'''
        self.session.event_hub.subscribe(
            'topic=ftrack.action.discover and source.user.username={0}'.format(
                self.session.api_user
            ),
            self.discover,
            priority=10
        )

        self.session.event_hub.subscribe(
            'topic=ftrack.action.launch and source.user.username={0} '
            'and data.actionIdentifier={1}'.format(
                self.session.api_user, self.identifier
            ),
            self.launch
        )

        self.session.event_hub.subscribe(
            'topic=ftrack.connect.plugin.debug-information',
            self.get_version_information
        )

    def discover(self, event):
        '''Return discovered applications.'''

        if not self.is_valid_selection(
            event['data'].get('selection', [])
        ):
            return

        items = []
        applications = self.application_store.applications
        applications = sorted(
            applications, key=lambda application: application['label']
        )

        for application in applications:
            application_identifier = application['identifier']
            label = application['label']
            items.append({
                'actionIdentifier': self.identifier,
                'label': label,
                'icon': application.get('icon', 'default'),
                'variant': application.get('variant', None),
                'applicationIdentifier': application_identifier
            })

        return {
            'items': items
        }

    def launch(self, event):
        '''Handle *event*.

        event['data'] should contain:

            *applicationIdentifier* to identify which application to start.

        '''
        # Prevent further processing by other listeners.
        event.stop()

        if not self.is_valid_selection(
            event['data'].get('selection', [])
        ):
            return

        application_identifier = (
            event['data']['applicationIdentifier']
        )

        context = event['data'].copy()
        context['source'] = event['source']

        application_identifier = event['data']['applicationIdentifier']
        context = event['data'].copy()
        context['source'] = event['source']

        return self.launcher.launch(
            application_identifier, context
        )

    def get_version_information(self, event):
        '''Return version information.'''
        return dict(
            name='ftrack connect maya',
            version=ftrack_connect_maya.__version__
        )


class ApplicationStore(ftrack_connect.application.ApplicationStore):

    def _checkMayaLocation(self):
        prefix = None

        maya_location = os.getenv('MAYA_LOCATION')

        if maya_location and os.path.isdir(maya_location):
            prefix = maya_location.split(os.sep)
            prefix[0] += os.sep

        return prefix

    def _discoverApplications(self):
        '''Return a list of applications that can be launched from this host.

        An application should be of the form:

            dict(
                'identifier': 'name_version',
                'label': 'Name version',
                'path': 'Absolute path to the file',
                'version': 'Version of the application',
                'icon': 'URL or name of predefined icon'
            )

        '''
        applications = []
        versions = [v.replace('.', '\.') for v in globalSettings.get('FTRACK_CONNECT').get('MAYA').get('version')]

        if sys.platform == 'darwin':
            prefix = ['/', 'Applications']
            maya_location = self._checkMayaLocation()
            if maya_location:
                prefix = maya_location

            applications.extend(self._searchFilesystem(
                expression=prefix + ['Autodesk', 'maya.+', 'Maya.app'],
                label='Maya',
                applicationIdentifier='maya_{version}',
                icon='maya',
                variant='{version}'
            ))

        elif sys.platform == 'win32':
            prefix = ['C:\\', 'Program Files.*']
            maya_location = self._checkMayaLocation()
            if maya_location:
                prefix = maya_location

            maya_version_expression = re.compile(
                r'(?P<version>{})'.format('|'.join(versions))
            )

            applications.extend(self._searchFilesystem(
                expression=prefix + ['Autodesk', 'Maya.+', 'bin', 'maya.exe'],
                label='Maya',
                applicationIdentifier='maya_{version}',
                icon='maya',
                variant='{version}',
                versionExpression=maya_version_expression
            ))

        elif 'linux' in sys.platform:
            prefix = ['/', 'usr', 'autodesk', 'maya.+']
            maya_location = self._checkMayaLocation()
            if maya_location:
                prefix = maya_location

            maya_version_expression = re.compile(
                r'maya(?P<version>{})'.format('|'.join(versions))
            )

            applications.extend(self._searchFilesystem(
                expression=prefix + ['bin', 'maya$'],
                label='Maya',
                applicationIdentifier='maya_{version}',
                icon='maya',
                variant='{version}',
                versionExpression=maya_version_expression
            ))

        self.logger.debug(
            'Discovered applications:\n{0}'.format(
                pprint.pformat(applications)
            )
        )

        return applications


class ApplicationLauncher(ftrack_connect.application.ApplicationLauncher):
    '''Custom launcher to modify environment before launch.'''

    def __init__(self, application_store, plugin_path, session):
        '''.'''
        super(ApplicationLauncher, self).__init__(application_store)

        self.plugin_path = plugin_path
        self.session = session

    def _getApplicationEnvironment(
        self, application, context=None
    ):
        '''Override to modify environment before launch.'''

        # Make sure to call super to retrieve original environment
        # which contains the selection and ftrack API.
        environment = super(
            ApplicationLauncher, self
        )._getApplicationEnvironment(application, context)

        entity = context['selection'][0]
        task = self.session.query('Task where id is "{}"'.format(entity['entityId'])).one()

        # most of the environment setup has been moved to launchTask
        # frameRange = arkFTrack.ftrackUtil.getFrameRange(task.get('parent'))
        # environment['FS'] = frameRange.get('start_frame')
        # environment['FE'] = frameRange.get('end_frame')

        environment['FTRACK_TASKID'] = task.get('id')
        environment['FTRACK_SHOTID'] = task.get('parent_id')

        # maya_connect_scripts = os.path.join(self.plugin_path, 'scripts')
        # maya_connect_plugins = os.path.join(self.plugin_path, 'plug_ins')

        # environment = ftrack_connect.application.appendPath(
        #     maya_connect_scripts,
        #     'PYTHONPATH',
        #     environment
        # )
        # environment = ftrack_connect.application.appendPath(
        #     maya_connect_scripts,
        #     'MAYA_SCRIPT_PATH',
        #     environment
        # )
        # environment = ftrack_connect.application.appendPath(
        #     maya_connect_plugins,
        #     'MAYA_PLUG_IN_PATH',
        #     environment
        # )

        # if float(application['version']) < 2017:
        #     environment['QT_PREFERRED_BINDING'] = 'PySide'
        # else:
        #     environment['QT_PREFERRED_BINDING'] = 'PySide2'

        return environment


def register(session, **kw):
    '''Register hooks.'''

    logger = logging.getLogger(
        'ftrack_plugin:ftrack_connect_maya_hook.register'
    )

    # Validate that session is an instance of ftrack_api.Session. If not,
    # assume that register is being called from an old or incompatible API and
    # return without doing anything.
    if not isinstance(session, ftrack_api.session.Session):
        return

    # Create store containing applications.
    application_store = ApplicationStore()

    # Create a launcher with the store containing applications.
    launcher = ApplicationLauncher(
        application_store, plugin_path=os.environ.get(
            'FTRACK_CONNECT_MAYA_PLUGINS_PATH',
            os.path.abspath(
                os.path.join(
                    os.path.dirname(__file__), '..', 'ftrack_connect_maya'
                )
            )
        ),
        session=session
    )

    # Create action and register to respond to discover and launch actions.
    action = LaunchApplicationAction(application_store, launcher, session)
    action.register()
