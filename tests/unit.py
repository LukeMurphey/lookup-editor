"""
This class tests the lookup editor related classes including:

    lookup_editor.LookupEditor
    lookup_editor.lookup_backups.LookupBackups
    lookup_editor.shortcuts
    lookup_backups_rest_handler.LookupBackupsHandler
    lookup_backups_rest_handler.LookupEditorHandler

These tests assume your local instance has a lookup file of test.csv available.
"""

import unittest
import sys
import os
import re
import json
import hashlib
import logging
import errno

from splunk import AuthenticationFailed, SplunkdConnectionException
from splunk.auth import getSessionKey
from splunk.rest import simpleRequest

sys.path.append( os.path.join("..", "src", "bin") )

from lookup_editor import shortcuts, lookup_backups, LookupEditor
from lookup_backups_rest_handler import LookupBackupsHandler
from lookup_editor_rest_handler import LookupEditorHandler

logger = logging.getLogger('splunk.appserver.lookup_editor.unit_test')

# This declares which app the lookup_test.csv file is
TEST_CSV_APP = 'lookup_test'

def skipIfCantAuthenticate(func):
    """
    This decorator will cause tests to be skipped if a session key could not be obtained.
    """
    def _decorator(self, *args, **kwargs):

        try:
            self.get_session_key()
        except AuthenticationFailed:
            self.skipTest("Could not authenticate with Splunk")
            return
        except SplunkdConnectionException:
            self.skipTest("Splunkd not accessible")
            return

        return func(self, *args, **kwargs)

    return _decorator

def skipIfLookupTestNotInstalled(func):
    """
    This decorator will cause tests to be skipped if the host doesn't have the lookup_test app
    installed.
    """
    def _decorator(self, *args, **kwargs):

        try:
            session_key = self.get_session_key()

            response, _ = simpleRequest('/servicesNS/nobody/system/apps/local/lookup_test',
                                        sessionKey=session_key,
                                        method='GET')

            if response.status == 404:
                self.skipTest("lookup_test app is not installed")
                return
        except AuthenticationFailed:
            self.skipTest("Could not authenticate with Splunk")
            return
        except SplunkdConnectionException:
            self.skipTest("Splunkd not accessible")
            return

        return func(self, *args, **kwargs)

    return _decorator

class LookupEditorTestCase(unittest.TestCase):
    """
    This base class offers functionality to help tests cases for the lookup editor.
    """

    session_key = None

    def get_session_key(self):
        """
        Get a session key to Splunk.
        """
        if self.session_key is not None:
            return self.session_key
        else:
            self.session_key = getSessionKey(username='admin', password='changeme')
            return self.session_key

    def strip_splunk_path(self, file_path):
        """
        Strip out the part of the path that refers to the local Splunk install.
        """

        etc_start = file_path.find("/etc/")
        return file_path[etc_start:]

class TestLookupEditRESTHandler(LookupEditorTestCase):
    """
    This tests the REST handler to ensure that it is functioning.
    """

    @skipIfCantAuthenticate
    def test_ping_handler(self):
        """
        Make sure the handler is onlne.
        """
        response, _ = simpleRequest("/services/data/lookup_edit/ping",
                                    sessionKey=self.get_session_key())
        self.assertEqual(response.status, 200)

    def test_function_signature(self):
        """
        Test the creation of the function signature from the path.
        """

        sig = LookupEditorHandler.get_function_signature("get", "test_a_function")
        self.assertEqual(sig, "get_test_a_function")

    def test_function_signature_sub_path(self):
        """
        Test the creation of the function signature from the path.
        """

        sig = LookupEditorHandler.get_function_signature("get", "first_part/second_part")
        self.assertEqual(sig, "get_first_part_second_part")

    @skipIfLookupTestNotInstalled
    def test_csv_export(self):
        """
        Test whether the exported CSV file matches.
        """

        url = '/services/data/lookup_edit/lookup_as_file?namespace=lookup_test&owner=nobody&lookup_file=1k_rows.csv&lookup_type=csv'
        response, content = simpleRequest(url,
                                          sessionKey=self.get_session_key())

        self.assertEqual(response.status, 200)

        sha224 = hashlib.sha224()
        sha224.update(content)

        expected_hash = 'c58fb78aa6a8ef9e3a646213d7a12d085a9fe63154a2b8a2423db62f'
        self.assertEqual(sha224.hexdigest(), expected_hash)
        self.assertEqual(response.status, 200)

    @skipIfLookupTestNotInstalled
    def test_kv_export(self):
        """
        Test whether the exported CSV file matches.
        """

        url = ('/services/data/lookup_edit/lookup_as_file?'
              'namespace=lookup_test&owner=nobody'
              '&lookup_file=test_kv_store_hierarchy&lookup_type=kv')

        response, content = simpleRequest(url,
                                          sessionKey=self.get_session_key())

        self.assertEqual(response.status, 200)

        # first_line = re.split("\n", content)[0]
        first_line = content.split(b'\n')[0]

        self.assertEqual(first_line.count(b","), 7)

class TestLookupBackupRESTHandler(LookupEditorTestCase):
    """
    This tests the REST handler to ensure that it is functioning.
    """

    @skipIfCantAuthenticate
    def test_ping_handler(self):
        """
        Make sure the handler is onlne.
        """
        response, _ = simpleRequest("/services/data/lookup_backup/ping",
                                    sessionKey=self.get_session_key())
        self.assertEqual(response.status, 200)

    def test_function_signature(self):
        """
        Test the creation of the function signature from the path.
        """

        sig = LookupBackupsHandler.get_function_signature("get", "test_a_function")
        self.assertEqual(sig, "get_test_a_function")

class TestLookupShortcuts(LookupEditorTestCase):
    """
    This tests the shortcuts class which contains helper functions for managing lookups.
    """

    def test_make_lookup_filename_valid(self):
        """
        Test the make_lookup_filename() functions ability to create a lookup file path.
        """

        # Global lookup
        self.assertEqual(self.strip_splunk_path(shortcuts.make_lookup_filename("test.csv", namespace="some_app")), "/etc/apps/some_app/lookups/test.csv")
        self.assertEqual(self.strip_splunk_path(shortcuts.make_lookup_filename("test.csv")), "/etc/apps/lookup_editor/lookups/test.csv")

        # User lookup
        self.assertEqual(self.strip_splunk_path(shortcuts.make_lookup_filename("test.csv", owner='some_user')), "/etc/users/some_user/lookup_editor/lookups/test.csv")
        self.assertEqual(self.strip_splunk_path(shortcuts.make_lookup_filename("test.csv", namespace="some_app", owner='some_user')), "/etc/users/some_user/some_app/lookups/test.csv")

        # A user of nobody
        self.assertEqual(self.strip_splunk_path(shortcuts.make_lookup_filename("test.csv", owner='nobody')), "/etc/apps/lookup_editor/lookups/test.csv")

        # A user of blank
        self.assertEqual(self.strip_splunk_path(shortcuts.make_lookup_filename("test.csv", owner='')), "/etc/apps/lookup_editor/lookups/test.csv")
        self.assertEqual(self.strip_splunk_path(shortcuts.make_lookup_filename("test.csv", owner=' ')), "/etc/apps/lookup_editor/lookups/test.csv")

    def test_make_lookup_filename_invalid(self):
        """
        Test the creation of a lookup file via make_lookup_filename() when the path includes
        disallowed characters.
        """

        # Invalid characters
        self.assertEqual(self.strip_splunk_path(shortcuts.make_lookup_filename("../test.csv")),
                          "/etc/apps/lookup_editor/lookups/test.csv")

        self.assertEqual(self.strip_splunk_path(shortcuts.make_lookup_filename("test.csv", namespace="../some_app")),
                          "/etc/apps/some_app/lookups/test.csv")
    
        self.assertEqual(self.strip_splunk_path(shortcuts.make_lookup_filename("test.csv", owner="../some_user")),
                          "/etc/users/some_user/lookup_editor/lookups/test.csv")

    def test_flatten_dict(self):
        """
        Test the flattening of a dict via flatten_dict().
        """

        d = '{ "name" : "Test", "configuration" : { "views" : [ { "name" : "some_view", "app" : "some_app" } ], "delay" : 300, "delay_readable" : "5m", "hide_chrome" : true, "invert_colors" : true }, "_user" : "nobody", "_key" : "123456789" }'
        flattened_d = shortcuts.flatten_dict(json.loads(d))
        self.assertEqual(flattened_d['configuration.delay'], 300)
        self.assertEqual(flattened_d['configuration.views'][0]['app'], 'some_app')
        self.assertEqual(flattened_d['name'], "Test")

    def test_flatten_dict_specified_fields(self):
        """
        Test the flattening of a dict via flatten_dict() but only convert the given fields.
        """

        d = '{ "name" : "Test", "configuration" : { "views" : [ { "name" : "some_view", "app" : "some_app" } ], "delay" : 300, "delay_readable" : "5m", "hide_chrome" : true, "invert_colors" : true }, "_user" : "nobody", "_key" : "123456789" }'
        flattened_d = shortcuts.flatten_dict(json.loads(d), fields=['name', 'configuration', '_user', '_key'])

        self.assertEqual(flattened_d['name'], 'Test')

        # Now parse the text within the configuration element and make sure it is the expected JSON
        c = json.loads(flattened_d['configuration'])

        self.assertEqual(c['views'][0]["name"], 'some_view')

class TestLookupEditor(LookupEditorTestCase):
    """
    This tests the class which manages lookup backups.
    """

    def setUp(self):
        self.lookup_editor = LookupEditor(logger=logger)

    @skipIfCantAuthenticate
    def test_resolve_lookup_filename(self):
        """
        Test resolve_lookup_filename() to resolve a lookup file name.
        """

        file_path = self.lookup_editor.resolve_lookup_filename('test.csv', 'search', 'nobody',
                                                               False, None,
                                                               session_key=self.get_session_key())

        self.assertEqual(self.strip_splunk_path(file_path),
                          '/etc/apps/' + TEST_CSV_APP + '/lookups/test.csv')

    @skipIfCantAuthenticate
    def test_resolve_lookup_filename_version(self):
        """
        Test resolve_lookup_filename() to resolve a lookup file name to the backed up version.
        """

        file_path = self.lookup_editor.resolve_lookup_filename('test.csv', 'search', 'nobody',
                                                               False, '1234',
                                                               session_key=self.get_session_key())

        self.assertEqual(self.strip_splunk_path(file_path),
                          '/etc/apps/' + TEST_CSV_APP + '/lookups/lookup_file_backups/search/nobody/test.csv/1234')
        
    @skipIfCantAuthenticate
    def test_resolve_lookup_filename_version_no_user(self):
        """
        Test resolve_lookup_filename() to resolve a lookup file name to the backed up version
        without providing a user.
        """

        file_path = self.lookup_editor.resolve_lookup_filename('test.csv', 'search', None, False,
                                                 '1234', session_key=self.get_session_key())

        self.assertEqual(self.strip_splunk_path(file_path),
                          '/etc/apps/' + TEST_CSV_APP + '/lookups/lookup_file_backups/search/nobody/test.csv/1234')

    @skipIfLookupTestNotInstalled
    def test_get_kv_fields_from_transform(self):
        """
        Test getting the fields of a lookup from a transform.
        """

        fields = self.lookup_editor.get_kv_fields_from_transform(self.get_session_key(), 'test_kv_store_transform_fields', 'lookup_test', None)

        self.assertEqual(len(fields), 4)

class TestLookupBackups(LookupEditorTestCase):
    """
    This tests the class which manages lookup backups.
    """

    def setUp(self):
        self.lookup_backups = lookup_backups.LookupBackups(logger=logger)

    @skipIfCantAuthenticate
    def test_get_backup_directory(self):
        """
        Ensure that get_backup_directory() returns the correct directory.
        """

        dir = self.lookup_backups.get_backup_directory(self.get_session_key(),
                                                       "test.csv", namespace="search",
                                                       owner="nobody")

        self.assertEqual(self.strip_splunk_path(dir),
                          '/etc/apps/' + TEST_CSV_APP + '/lookups/lookup_file_backups/search/nobody/test.csv')

    @skipIfCantAuthenticate
    def test_get_backup_directory_with_resolved(self):
        """
        Ensure that get_backup_directory() returns the correct directory when given a value for resolved_lookup_path.
        """
        self.lookup_editor = LookupEditor(logger=logger)
        resolved_lookup_path = self.lookup_editor.resolve_lookup_filename('test.csv',
                                                                          'search',
                                                                          'nobody',
                                                                          False,
                                                                          None,
                                                                          session_key=self.get_session_key())

        dir = self.lookup_backups.get_backup_directory(self.get_session_key(), "test.csv",
                                                       namespace="search", owner="nobody",
                                                       resolved_lookup_path=resolved_lookup_path)

        self.assertEqual(self.strip_splunk_path(dir),
                          '/etc/apps/' + TEST_CSV_APP + '/lookups/lookup_file_backups/search/nobody/test.csv')

if __name__ == "__main__":
    unittest.main()
