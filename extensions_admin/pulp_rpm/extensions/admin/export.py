from gettext import gettext as _

from okaara import parsers
from pulp.bindings import responses
from pulp.client.commands import options
from pulp.client.commands.repo.sync_publish import RunPublishRepositoryCommand
from pulp.client import validators
from pulp.client.commands.polling import PollingCommand
from pulp.client.extensions.extensions import PulpCliOption, PulpCliFlag
from pulp.common import tags as tag_utils

from pulp_rpm.common import ids, constants


DESC_EXPORT_RUN = _('triggers an immediate export of a repository')
DESC_GROUP_EXPORT_RUN = _('triggers an immediate export of a repository group')
DESC_GROUP_EXPORT_STATUS = _('displays the status of a repository group\'s export task')

DESC_ISO_PREFIX = _('prefix to use in the generated ISO name, default: <repo-id>-<current_date>'
                    '.iso')
DESC_START_DATE = _('start date for an incremental export; only content associated with a '
                    'repository on or after the given value will be included in the exported '
                    'repository; dates should be in standard ISO8601 format: "1970-01-01T00:00:00"')
DESC_END_DATE = _('end date for an incremental export; only content associated with a repository '
                  'on or before the given value will be included in the exported repository; dates '
                  'should be in standard ISO8601 format: "1970-01-01T00:00:00"')
DESC_EXPORT_DIR = _('the full path to a directory; if specified, the repository will be exported '
                    'to the given directory instead of being placed in ISOs and published via '
                    'HTTP or HTTPS')
DESC_RELATIVE_URL = _('relative path at which the repository will be served when exported. '
                      'if specified with --export-dir, this will be the exported subdirectory name '
                      'instead of the default, which is the repository id.')
DESC_ISO_SIZE = _('the maximum size, in MiB (1024 kiB), of each exported ISO; if this is not '
                  'specified, single layer DVD-sized ISOs are created')
DESC_BACKGROUND = _('if specified, the CLI process will end but the process will continue on '
                    'the server; the progress can be later displayed using the status command')
# These two flags exist because there is currently no place to configure group publishes
DESC_SERVE_HTTP = _('the ISO images will be served over HTTP; default to False; if '
                    'this export is to a directory, this has no effect.')
DESC_SERVE_HTTPS = _('the ISO images will be served over HTTPS; defaults to True; if '
                     'this export is to a directory, this has no effect.')
DESC_MANIFEST = _('if this flag is used, a PULP_MANIFEST file will be created')

# The iso prefix is restricted to the same character set as an id, so we use the id_validator
OPTION_ISO_PREFIX = PulpCliOption('--iso-prefix', DESC_ISO_PREFIX, required=False,
                                  validate_func=validators.id_validator)
OPTION_START_DATE = PulpCliOption('--start-date', DESC_START_DATE, required=False,
                                  validate_func=validators.iso8601_datetime_validator)
OPTION_END_DATE = PulpCliOption('--end-date', DESC_END_DATE, required=False,
                                validate_func=validators.iso8601_datetime_validator)
OPTION_EXPORT_DIR = PulpCliOption('--export-dir', DESC_EXPORT_DIR, required=False)
OPTION_RELATIVE_URL = PulpCliOption('--relative-url', DESC_RELATIVE_URL, required=False)
OPTION_ISO_SIZE = PulpCliOption('--iso-size', DESC_ISO_SIZE, required=False,
                                parse_func=parsers.parse_optional_positive_int)
OPTION_SERVE_HTTPS = PulpCliOption('--serve-https', DESC_SERVE_HTTPS, required=False,
                                   default='true', parse_func=parsers.parse_boolean)
OPTION_SERVE_HTTP = PulpCliOption('--serve-http', DESC_SERVE_HTTP, required=False, default='false',
                                  parse_func=parsers.parse_boolean)
FLAG_MANIFEST = PulpCliFlag('--' + constants.CREATE_PULP_MANIFEST, DESC_MANIFEST, ['-m'])


class RpmExportCommand(RunPublishRepositoryCommand):
    """
    The 'pulp-admin rpm repo export run' command
    """

    def __init__(self, context, renderer):
        """
        The constructor for RpmExportCommand

        :param context: The client context to use for this command
        :type  context: pulp.client.extensions.core.ClientContext
        """
        override_config_options = [OPTION_EXPORT_DIR, OPTION_ISO_PREFIX, OPTION_ISO_SIZE,
                                   OPTION_START_DATE, OPTION_END_DATE, FLAG_MANIFEST,
                                   OPTION_RELATIVE_URL]

        super(RpmExportCommand, self).__init__(context=context,
                                               renderer=renderer,
                                               distributor_id=ids.TYPE_ID_DISTRIBUTOR_EXPORT,
                                               description=DESC_EXPORT_RUN,
                                               override_config_options=override_config_options)


class RpmGroupExportCommand(PollingCommand):
    """
    The 'pulp-admin rpm repo group export run' command.
    """

    def __init__(self, context, renderer, name='run', description=DESC_GROUP_EXPORT_RUN):
        """
        The constructor for RpmGroupExportCommand

        :param context:         The client context to use for this command
        :type  context:         pulp.client.extensions.core.ClientContext
        :param renderer:        The progress renderer to use with this command
        :type  renderer:        pulp.client.commands.repo.sync_publish.StatusRenderer
        :param name:            The name to use for the command. This should take i18n into account
        :type  name:            str
        :param description:     The description to use for the command. This should take i18n into
                                account
        :type description:      str
        """
        super(RpmGroupExportCommand, self).__init__(name, description, self.run, context)

        self.context = context
        self.prompt = context.prompt
        self.renderer = renderer

        self.add_option(options.OPTION_GROUP_ID)
        self.add_option(OPTION_ISO_PREFIX)
        self.add_option(OPTION_ISO_SIZE)
        self.add_option(OPTION_START_DATE)
        self.add_option(OPTION_END_DATE)
        self.add_option(OPTION_EXPORT_DIR)
        self.add_option(OPTION_RELATIVE_URL)
        self.add_option(OPTION_SERVE_HTTPS)
        self.add_option(OPTION_SERVE_HTTP)

        self.add_flag(FLAG_MANIFEST)

    def run(self, **kwargs):
        """
        The run function for the export command. This is the self.method method which is defined in
        the Command super class. This method does all the work for a group export run call.
        """
        # Grab all the configuration options
        group_id = kwargs[options.OPTION_GROUP_ID.keyword]
        iso_prefix = kwargs[OPTION_ISO_PREFIX.keyword]
        iso_size = kwargs[OPTION_ISO_SIZE.keyword]
        start_date = kwargs[OPTION_START_DATE.keyword]
        end_date = kwargs[OPTION_END_DATE.keyword]
        export_dir = kwargs[OPTION_EXPORT_DIR.keyword]
        relative_url = kwargs[OPTION_RELATIVE_URL.keyword]
        manifest = kwargs[FLAG_MANIFEST.keyword]
        serve_http = kwargs[OPTION_SERVE_HTTP.keyword]
        serve_https = kwargs[OPTION_SERVE_HTTPS.keyword]

        # Since the export distributor is not added to a repository group on creation, add it here
        # if it is not already associated with the group id

        # Find the export distributors for this repo group
        response = self.context.server.repo_group_distributor.distributors(group_id)
        all_distributors = response.response_body
        distributors = []
        # Iterate through and do comparison since the API doesn't support full search
        for distributor in all_distributors:
            if distributor.get('distributor_type_id') == ids.TYPE_ID_DISTRIBUTOR_GROUP_EXPORT:
                distributors.append(distributor)

        if len(distributors) == 0:
            distributor_config = {
                constants.PUBLISH_HTTP_KEYWORD: serve_http,
                constants.PUBLISH_HTTPS_KEYWORD: serve_https,
            }
            response = self.context.server.repo_group_distributor.create(
                group_id,
                ids.TYPE_ID_DISTRIBUTOR_GROUP_EXPORT,
                distributor_config)
            distributors = [response.response_body]

        publish_config = {
            constants.PUBLISH_HTTP_KEYWORD: serve_http,
            constants.PUBLISH_HTTPS_KEYWORD: serve_https,
            constants.ISO_PREFIX_KEYWORD: iso_prefix,
            constants.ISO_SIZE_KEYWORD: iso_size,
            constants.START_DATE_KEYWORD: start_date,
            constants.END_DATE_KEYWORD: end_date,
            constants.EXPORT_DIRECTORY_KEYWORD: export_dir,
            constants.RELATIVE_URL_KEYWORD: relative_url,
            constants.CREATE_PULP_MANIFEST: manifest,
        }

        # Remove keys from the config that have None value.
        for key, value in publish_config.items():
            if value is None:
                del publish_config[key]

        self.prompt.render_title(_('Exporting Repository Group [%s]' % group_id))

        # Retrieve all publish tasks for this repository group
        tasks_to_poll = _get_publish_tasks(group_id, self.context)

        if len(tasks_to_poll) > 0:
            msg = _('A publish task is already in progress for this repository group.')
            self.context.prompt.render_paragraph(msg, tag='in-progress')
            self.poll(tasks_to_poll, kwargs)
        else:
            # If there is no existing publish for this repo group, start one
            for distributor in distributors:
                response = self.context.server.repo_group_actions.publish(group_id,
                                                                          distributor.get('id'),
                                                                          publish_config)
                self.poll(response.response_body, kwargs)

    def progress(self, task, spinner):
        """
        Render the progress report, if it is available on the given task.

        :param task:    The Task that we wish to render progress about
        :type  task:    pulp.bindings.responses.Task
        :param spinner: Not used by this method, but the superclass will give it to us
        :type  spinner: okaara.progress.Spinner
        """
        if task.progress_report is not None:
            self.renderer.display_report(task.progress_report)


class GroupExportStatusCommand(PollingCommand):
    """
    The rpm repo group export status command.
    """

    def __init__(self, context, renderer, name='status', description=DESC_GROUP_EXPORT_STATUS):
        """
        The constructor for GroupExportStatusCommand

        :param context:         The client context to use for this command
        :type  context:         pulp.client.extensions.core.ClientContext
        :param renderer:        The progress renderer to use with this command
        :type  renderer:        pulp.client.commands.repo.sync_publish.StatusRenderer
        :param name:            The name to use for the command. This should take i18n into account
        :type  name:            str
        :param description:     The description to use for the command. This should take i18n into
                                account
        :type description:      str
        """
        super(GroupExportStatusCommand, self).__init__(name, description, self.run, context)

        self.context = context
        self.prompt = context.prompt
        self.renderer = renderer

        self.add_option(options.OPTION_GROUP_ID)

    def run(self, **kwargs):
        """
        This is the self.method method which is defined in the Command super class. This method
        does all the work for a group export status call.
        """
        group_id = kwargs[options.OPTION_GROUP_ID.keyword]
        self.prompt.render_title(_('Repository Group [%s] Export Status' % group_id))

        # Retrieve the task id, if it exists
        tasks_to_poll = _get_publish_tasks(group_id, self.context)

        if not tasks_to_poll:
            msg = _('The repository group is not performing any operations')
            self.prompt.render_paragraph(msg, tag='no-tasks')
        else:
            self.poll(tasks_to_poll, kwargs)

    def progress(self, task, spinner):
        """
        Render the progress report, if it is available on the given task.

        :param task:    The Task that we wish to render progress about
        :type  task:    pulp.bindings.responses.Task
        :param spinner: Not used by this method, but the superclass will give it to us
        :type  spinner: okaara.progress.Spinner
        """
        if task.progress_report is not None:
            self.renderer.display_report(task.progress_report)


def _get_publish_tasks(resource_id, context):
    """
    Get the list of currently running publish tasks for the given repo_group id.

    :param resource_id:     The id of the resource to retrieve the task id for. This should be a
                            repo or group id
    :type  resource_id:     str
    :param context:         The client context is used when fetching existing task ids
    :type  context:         pulp.client.extensions.core.ClientContext

    :return: The Task, if it exists. If it does not, this will return None
    :rtype:  list of pulp.bindings.responses.Task
    """
    tags = [tag_utils.resource_tag(tag_utils.RESOURCE_REPOSITORY_GROUP_TYPE, resource_id),
            tag_utils.action_tag(tag_utils.ACTION_PUBLISH_TYPE)]
    criteria = {'filters': {'state': {'$nin': responses.COMPLETED_STATES}, 'tags': {'$all': tags}}}
    return context.server.tasks_search.search(**criteria)
