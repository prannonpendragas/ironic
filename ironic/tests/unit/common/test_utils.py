# Copyright 2011 Justin Santa Barbara
# Copyright 2012 Hewlett-Packard Development Company, L.P.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import copy
import datetime
import errno
import os
import os.path
import shutil
import tempfile
import time
from unittest import mock

import jinja2
from oslo_concurrency import processutils
from oslo_config import cfg
from oslo_utils import netutils
import psutil

from ironic.common import exception
from ironic.common import utils
from ironic.tests import base

CONF = cfg.CONF


class BareMetalUtilsTestCase(base.TestCase):

    def test_create_link(self):
        with mock.patch.object(os, "symlink", autospec=True) as symlink_mock:
            symlink_mock.return_value = None
            utils.create_link_without_raise("/fake/source", "/fake/link")
            symlink_mock.assert_called_once_with("/fake/source", "/fake/link")

    def test_create_link_EEXIST(self):
        with mock.patch.object(os, "symlink", autospec=True) as symlink_mock:
            symlink_mock.side_effect = OSError(errno.EEXIST)
            utils.create_link_without_raise("/fake/source", "/fake/link")
            symlink_mock.assert_called_once_with("/fake/source", "/fake/link")


class GenericUtilsTestCase(base.TestCase):
    @mock.patch.object(utils, 'hashlib', autospec=True)
    def test__get_hash_object(self, hashlib_mock):
        algorithms_available = ('md5', 'sha1', 'sha224',
                                'sha256', 'sha384', 'sha512')
        hashlib_mock.algorithms_guaranteed = algorithms_available
        hashlib_mock.algorithms = algorithms_available
        # | WHEN |
        utils._get_hash_object('md5')
        utils._get_hash_object('sha1')
        utils._get_hash_object('sha224')
        utils._get_hash_object('sha256')
        utils._get_hash_object('sha384')
        utils._get_hash_object('sha512')
        # | THEN |
        calls = [mock.call.md5(), mock.call.sha1(), mock.call.sha224(),
                 mock.call.sha256(), mock.call.sha384(), mock.call.sha512()]
        hashlib_mock.assert_has_calls(calls)

    def test__get_hash_object_throws_for_invalid_or_unsupported_hash_name(
            self):
        # | WHEN | & | THEN |
        self.assertRaises(exception.InvalidParameterValue,
                          utils._get_hash_object,
                          'hickory-dickory-dock')

    def test_file_has_content_equal(self):
        data = b'Mary had a little lamb, its fleece as white as snow'
        ref = data
        with mock.patch('oslo_utils.fileutils.open',
                        mock.mock_open(read_data=data)) as mopen:
            self.assertTrue(utils.file_has_content('foo', ref))
            mopen.assert_called_once_with('foo', 'rb')

    def test_file_has_content_equal_not_binary(self):
        data = ('Mary had a little lamb, its fleece as white as '
                'sno\u0449').encode('utf-8')
        ref = data
        with mock.patch('oslo_utils.fileutils.open',
                        mock.mock_open(read_data=data)) as mopen:
            self.assertTrue(utils.file_has_content('foo', ref))
            mopen.assert_called_once_with('foo', 'rb')

    def test_file_has_content_differ(self):
        data = b'Mary had a little lamb, its fleece as white as snow'
        ref = data + b'!'
        with mock.patch('oslo_utils.fileutils.open',
                        mock.mock_open(read_data=data)) as mopen:
            self.assertFalse(utils.file_has_content('foo', ref))
            mopen.assert_called_once_with('foo', 'rb')

    def test_is_valid_datapath_id(self):
        self.assertTrue(utils.is_valid_datapath_id("525400cf2d319fdf"))
        self.assertTrue(utils.is_valid_datapath_id("525400CF2D319FDF"))
        self.assertFalse(utils.is_valid_datapath_id("52"))
        self.assertFalse(utils.is_valid_datapath_id("52:54:00:cf:2d:31"))
        self.assertFalse(utils.is_valid_datapath_id("notadatapathid00"))
        self.assertFalse(utils.is_valid_datapath_id("5525400CF2D319FDF"))

    def test_is_hostname_safe(self):
        self.assertTrue(utils.is_hostname_safe('spam'))
        self.assertFalse(utils.is_hostname_safe('spAm'))
        self.assertFalse(utils.is_hostname_safe('SPAM'))
        self.assertFalse(utils.is_hostname_safe('-spam'))
        self.assertFalse(utils.is_hostname_safe('spam-'))
        self.assertTrue(utils.is_hostname_safe('spam-eggs'))
        self.assertFalse(utils.is_hostname_safe('spam_eggs'))
        self.assertFalse(utils.is_hostname_safe('spam eggs'))
        self.assertTrue(utils.is_hostname_safe('spam.eggs'))
        self.assertTrue(utils.is_hostname_safe('9spam'))
        self.assertTrue(utils.is_hostname_safe('spam7'))
        self.assertTrue(utils.is_hostname_safe('br34kf4st'))
        self.assertFalse(utils.is_hostname_safe('$pam'))
        self.assertFalse(utils.is_hostname_safe('egg$'))
        self.assertFalse(utils.is_hostname_safe('spam#eggs'))
        self.assertFalse(utils.is_hostname_safe(' eggs'))
        self.assertFalse(utils.is_hostname_safe('spam '))
        self.assertTrue(utils.is_hostname_safe('s'))
        self.assertTrue(utils.is_hostname_safe('s' * 63))
        self.assertFalse(utils.is_hostname_safe('s' * 64))
        self.assertFalse(utils.is_hostname_safe(''))
        self.assertFalse(utils.is_hostname_safe(None))
        # Need to ensure a binary response for success or fail
        self.assertIsNotNone(utils.is_hostname_safe('spam'))
        self.assertIsNotNone(utils.is_hostname_safe('-spam'))
        self.assertTrue(utils.is_hostname_safe('www.rackspace.com'))
        self.assertTrue(utils.is_hostname_safe('www.rackspace.com.'))
        self.assertTrue(utils.is_hostname_safe('http._sctp.www.example.com'))
        self.assertTrue(utils.is_hostname_safe('mail.pets_r_us.net'))
        self.assertTrue(utils.is_hostname_safe('mail-server-15.my_host.org'))
        self.assertFalse(utils.is_hostname_safe('www.nothere.com_'))
        self.assertFalse(utils.is_hostname_safe('www.nothere_.com'))
        self.assertFalse(utils.is_hostname_safe('www..nothere.com'))
        long_str = 'a' * 63 + '.' + 'b' * 63 + '.' + 'c' * 63 + '.' + 'd' * 63
        self.assertTrue(utils.is_hostname_safe(long_str))
        self.assertFalse(utils.is_hostname_safe(long_str + '.'))
        self.assertFalse(utils.is_hostname_safe('a' * 255))

    def test_is_valid_logical_name(self):
        valid = (
            'spam', 'spAm', 'SPAM', 'spam-eggs', 'spam.eggs', 'spam_eggs',
            'spam~eggs', '9spam', 'spam7', '~spam', '.spam', '.~-_', '~',
            'br34kf4st', 's', 's' * 63, 's' * 255)
        invalid = (
            ' ', 'spam eggs', '$pam', 'egg$', 'spam#eggs',
            ' eggs', 'spam ', '', None, 'spam%20')

        for hostname in valid:
            result = utils.is_valid_logical_name(hostname)
            # Need to ensure a binary response for success. assertTrue
            # is too generous, and would pass this test if, for
            # instance, a regex Match object were returned.
            self.assertIs(result, True,
                          "%s is unexpectedly invalid" % hostname)

        for hostname in invalid:
            result = utils.is_valid_logical_name(hostname)
            # Need to ensure a binary response for
            # success. assertFalse is too generous and would pass this
            # test if None were returned.
            self.assertIs(result, False,
                          "%s is unexpectedly valid" % hostname)

    def test_validate_and_normalize_mac(self):
        mac = 'AA:BB:CC:DD:EE:FF'
        with mock.patch.object(netutils, 'is_valid_mac',
                               autospec=True) as m_mock:
            m_mock.return_value = True
            self.assertEqual(mac.lower(),
                             utils.validate_and_normalize_mac(mac))

    def test_validate_and_normalize_datapath_id(self):
        datapath_id = 'AA:BB:CC:DD:EE:FF'
        with mock.patch.object(utils, 'is_valid_datapath_id',
                               autospec=True) as m_mock:
            m_mock.return_value = True
            self.assertEqual(datapath_id.lower(),
                             utils.validate_and_normalize_datapath_id(
                                 datapath_id))

    def test_validate_and_normalize_mac_invalid_format(self):
        with mock.patch.object(netutils, 'is_valid_mac',
                               autospec=True) as m_mock:
            m_mock.return_value = False
            self.assertRaises(exception.InvalidMAC,
                              utils.validate_and_normalize_mac, 'invalid-mac')

    def test_safe_rstrip(self):
        value = '/test/'
        rstripped_value = '/test'
        not_rstripped = '/'

        self.assertEqual(rstripped_value, utils.safe_rstrip(value, '/'))
        self.assertEqual(not_rstripped, utils.safe_rstrip(not_rstripped, '/'))

    def test_safe_rstrip_not_raises_exceptions(self):
        # Supplying an integer should normally raise an exception because it
        # does not save the rstrip() method.
        value = 10

        # In the case of raising an exception safe_rstrip() should return the
        # original value.
        self.assertEqual(value, utils.safe_rstrip(value))

    @mock.patch.object(os.path, 'getmtime', return_value=1439465889.4964755,
                       autospec=True)
    def test_unix_file_modification_datetime(self, mtime_mock):
        expected = datetime.datetime(2015, 8, 13, 11, 38, 9, 496475)
        self.assertEqual(expected,
                         utils.unix_file_modification_datetime('foo'))
        mtime_mock.assert_called_once_with('foo')

    def test_is_valid_no_proxy(self):

        # Valid values for 'no_proxy'
        valid_no_proxy = [
            ('a' * 63 + '.' + '0' * 63 + '.c.' + 'd' * 61 + '.' + 'e' * 61),
            ('A' * 63 + '.' + '0' * 63 + '.C.' + 'D' * 61 + '.' + 'E' * 61),
            ('.' + 'a' * 62 + '.' + '0' * 62 + '.c.' + 'd' * 61 + '.'
             + 'e' * 61),
            ',,example.com:3128,',
            '192.168.1.1',  # IP should be valid
        ]
        # Test each one individually, so if failure easier to determine which
        # one failed.
        for no_proxy in valid_no_proxy:
            self.assertTrue(
                utils.is_valid_no_proxy(no_proxy),
                msg="'no_proxy' value should be valid: {}".format(no_proxy))
        # Test valid when joined together
        self.assertTrue(utils.is_valid_no_proxy(','.join(valid_no_proxy)))
        # Test valid when joined together with whitespace
        self.assertTrue(utils.is_valid_no_proxy(' , '.join(valid_no_proxy)))
        # empty string should also be valid
        self.assertTrue(utils.is_valid_no_proxy(''))

        # Invalid values for 'no_proxy'
        invalid_no_proxy = [
            ('A' * 64 + '.' + '0' * 63 + '.C.' + 'D' * 61 + '.'
             + 'E' * 61),  # too long (> 253)
            ('a' * 100),
            'a..com',
            ('.' + 'a' * 63 + '.' + '0' * 62 + '.c.' + 'd' * 61 + '.'
             + 'e' * 61),  # too long (> 251 after deleting .)
            ('*.' + 'a' * 60 + '.' + '0' * 60 + '.c.' + 'd' * 61 + '.'
             + 'e' * 61),  # starts with *.
            'c.-a.com',
            'c.a-.com',
        ]

        for no_proxy in invalid_no_proxy:
            self.assertFalse(
                utils.is_valid_no_proxy(no_proxy),
                msg="'no_proxy' value should be invalid: {}".format(no_proxy))

    def test_is_fips_enabled(self):
        with mock.patch('builtins.open', mock.mock_open(read_data='1\n')) as m:
            self.assertTrue(utils.is_fips_enabled())
            m.assert_called_once_with('/proc/sys/crypto/fips_enabled', 'r')

        with mock.patch('builtins.open', mock.mock_open(read_data='0\n')) as m:
            self.assertFalse(utils.is_fips_enabled())
            m.assert_called_once_with('/proc/sys/crypto/fips_enabled', 'r')

        mock_open = mock.mock_open()
        mock_open.side_effect = FileNotFoundError
        with mock.patch('builtins.open', mock_open) as m:
            self.assertFalse(utils.is_fips_enabled())
            m.assert_called_once_with('/proc/sys/crypto/fips_enabled', 'r')

    def test_wrap_ipv6(self):
        self.assertEqual('[2001:DB8::1]', utils.wrap_ipv6('2001:DB8::1'))
        self.assertEqual('example.com', utils.wrap_ipv6('example.com'))
        self.assertEqual('192.168.24.1', utils.wrap_ipv6('192.168.24.1'))
        self.assertEqual('[2001:DB8::1]', utils.wrap_ipv6('[2001:DB8::1]'))


class TempFilesTestCase(base.TestCase):

    def test_tempdir(self):

        dirname = None
        with utils.tempdir() as tempdir:
            self.assertTrue(os.path.isdir(tempdir))
            dirname = tempdir
        self.assertFalse(os.path.exists(dirname))

    @mock.patch.object(shutil, 'rmtree', autospec=True)
    @mock.patch.object(tempfile, 'mkdtemp', autospec=True)
    def test_tempdir_mocked(self, mkdtemp_mock, rmtree_mock):

        self.config(tempdir='abc')
        mkdtemp_mock.return_value = 'temp-dir'
        kwargs = {'dir': 'b'}

        with utils.tempdir(**kwargs) as tempdir:
            self.assertEqual('temp-dir', tempdir)
            tempdir_created = tempdir

        mkdtemp_mock.assert_called_once_with(**kwargs)
        rmtree_mock.assert_called_once_with(tempdir_created)

    @mock.patch.object(utils, 'LOG', autospec=True)
    @mock.patch.object(shutil, 'rmtree', autospec=True)
    @mock.patch.object(tempfile, 'mkdtemp', autospec=True)
    def test_tempdir_mocked_error_on_rmtree(self, mkdtemp_mock, rmtree_mock,
                                            log_mock):

        self.config(tempdir='abc')
        mkdtemp_mock.return_value = 'temp-dir'
        rmtree_mock.side_effect = OSError

        with utils.tempdir() as tempdir:
            self.assertEqual('temp-dir', tempdir)
            tempdir_created = tempdir

        rmtree_mock.assert_called_once_with(tempdir_created)
        self.assertTrue(log_mock.error.called)

    @mock.patch.object(os.path, 'exists', autospec=True)
    @mock.patch.object(utils, '_check_dir_writable', autospec=True)
    @mock.patch.object(utils, '_check_dir_free_space', autospec=True)
    def test_check_dir_with_pass_in(self, mock_free_space, mock_dir_writable,
                                    mock_exists):
        mock_exists.return_value = True
        # test passing in a directory and size
        utils.check_dir(directory_to_check='/fake/path', required_space=5)
        mock_exists.assert_called_once_with('/fake/path')
        mock_dir_writable.assert_called_once_with('/fake/path')
        mock_free_space.assert_called_once_with('/fake/path', 5)

    @mock.patch.object(utils, '_check_dir_writable', autospec=True)
    @mock.patch.object(utils, '_check_dir_free_space', autospec=True)
    def test_check_dir_no_dir(self, mock_free_space, mock_dir_writable):
        self.config(tempdir='/fake/path')
        # NOTE(dtantsur): self.config uses os.path.exists, so we cannot mock
        # on the method level.
        with mock.patch.object(os.path, 'exists',
                               autospec=True) as mock_exists:
            mock_exists.return_value = False
            self.assertRaises(exception.PathNotFound, utils.check_dir)
            mock_exists.assert_called_once_with(CONF.tempdir)
        self.assertFalse(mock_free_space.called)
        self.assertFalse(mock_dir_writable.called)

    @mock.patch.object(utils, '_check_dir_writable', autospec=True)
    @mock.patch.object(utils, '_check_dir_free_space', autospec=True)
    def test_check_dir_ok(self, mock_free_space, mock_dir_writable):
        self.config(tempdir='/fake/path')
        # NOTE(dtantsur): self.config uses os.path.exists, so we cannot mock
        # on the method level.
        with mock.patch.object(os.path, 'exists',
                               autospec=True) as mock_exists:
            mock_exists.return_value = True
            utils.check_dir()
            mock_exists.assert_called_once_with(CONF.tempdir)
        mock_dir_writable.assert_called_once_with(CONF.tempdir)
        mock_free_space.assert_called_once_with(CONF.tempdir, 1)

    @mock.patch.object(os, 'access', autospec=True)
    def test__check_dir_writable_ok(self, mock_access):
        mock_access.return_value = True
        self.assertIsNone(utils._check_dir_writable("/fake/path"))
        mock_access.assert_called_once_with("/fake/path", os.W_OK)

    @mock.patch.object(os, 'access', autospec=True)
    def test__check_dir_writable_not_writable(self, mock_access):
        mock_access.return_value = False

        self.assertRaises(exception.DirectoryNotWritable,
                          utils._check_dir_writable, "/fake/path")
        mock_access.assert_called_once_with("/fake/path", os.W_OK)

    @mock.patch.object(os, 'statvfs', autospec=True)
    def test__check_dir_free_space_ok(self, mock_stat):
        statvfs_mock_return = mock.MagicMock()
        statvfs_mock_return.f_bsize = 5
        statvfs_mock_return.f_frsize = 0
        statvfs_mock_return.f_blocks = 0
        statvfs_mock_return.f_bfree = 0
        statvfs_mock_return.f_bavail = 1024 * 1024
        statvfs_mock_return.f_files = 0
        statvfs_mock_return.f_ffree = 0
        statvfs_mock_return.f_favail = 0
        statvfs_mock_return.f_flag = 0
        statvfs_mock_return.f_namemax = 0
        mock_stat.return_value = statvfs_mock_return
        utils._check_dir_free_space("/fake/path")
        mock_stat.assert_called_once_with("/fake/path")

    @mock.patch.object(os, 'statvfs', autospec=True)
    def test_check_dir_free_space_raises(self, mock_stat):
        statvfs_mock_return = mock.MagicMock()
        statvfs_mock_return.f_bsize = 1
        statvfs_mock_return.f_frsize = 0
        statvfs_mock_return.f_blocks = 0
        statvfs_mock_return.f_bfree = 0
        statvfs_mock_return.f_bavail = 1024
        statvfs_mock_return.f_files = 0
        statvfs_mock_return.f_ffree = 0
        statvfs_mock_return.f_favail = 0
        statvfs_mock_return.f_flag = 0
        statvfs_mock_return.f_namemax = 0
        mock_stat.return_value = statvfs_mock_return

        self.assertRaises(exception.InsufficientDiskSpace,
                          utils._check_dir_free_space, "/fake/path")
        mock_stat.assert_called_once_with("/fake/path")

    @mock.patch.object(time, 'sleep', autospec=True)
    @mock.patch.object(psutil, 'virtual_memory', autospec=True)
    def test_is_memory_insufficient(self, mock_vm_check, mock_sleep):

        class vm_check(object):
            available = 1000000000

        mock_vm_check.return_value = vm_check
        self.assertTrue(utils.is_memory_insufficient())
        self.assertEqual(14, mock_vm_check.call_count)

    @mock.patch.object(time, 'sleep', autospec=True)
    @mock.patch.object(psutil, 'virtual_memory', autospec=True)
    def test_is_memory_insufficient_good(self, mock_vm_check,
                                         mock_sleep):

        class vm_check(object):
            available = 3276700000

        mock_vm_check.return_value = vm_check
        self.assertFalse(utils.is_memory_insufficient())
        self.assertEqual(1, mock_vm_check.call_count)

    @mock.patch.object(time, 'sleep', autospec=True)
    @mock.patch.object(psutil, 'virtual_memory', autospec=True)
    def test_is_memory_insufficient_recovers(self, mock_vm_check,
                                             mock_sleep):

        class vm_check_bad(object):
            available = 1023000000

        class vm_check_good(object):
            available = 3276700000

        self.config(minimum_memory_warning_only=False)
        mock_vm_check.side_effect = iter([vm_check_bad,
                                          vm_check_bad,
                                          vm_check_good])
        self.assertFalse(utils.is_memory_insufficient())
        self.assertEqual(3, mock_vm_check.call_count)

    @mock.patch.object(time, 'sleep', autospec=True)
    @mock.patch.object(psutil, 'virtual_memory', autospec=True)
    def test_is_memory_insufficient_warning_only(self, mock_vm_check,
                                                 mock_sleep):
        self.config(minimum_memory_warning_only=True)

        class vm_check_bad(object):
            available = 1023000000

        mock_vm_check.side_effect = vm_check_bad
        self.assertFalse(utils.is_memory_insufficient())
        self.assertEqual(2, mock_vm_check.call_count)


class GetUpdatedCapabilitiesTestCase(base.TestCase):

    def test_get_updated_capabilities(self):
        capabilities = {'ilo_firmware_version': 'xyz'}
        cap_string = 'ilo_firmware_version:xyz'
        cap_returned = utils.get_updated_capabilities(None, capabilities)
        self.assertEqual(cap_string, cap_returned)
        self.assertIsInstance(cap_returned, str)

    def test_get_updated_capabilities_multiple_keys(self):
        capabilities = {'ilo_firmware_version': 'xyz',
                        'foo': 'bar', 'somekey': 'value'}
        cap_string = 'ilo_firmware_version:xyz,foo:bar,somekey:value'
        cap_returned = utils.get_updated_capabilities(None, capabilities)
        set1 = set(cap_string.split(','))
        set2 = set(cap_returned.split(','))
        self.assertEqual(set1, set2)
        self.assertIsInstance(cap_returned, str)

    def test_get_updated_capabilities_invalid_capabilities(self):
        capabilities = 'ilo_firmware_version'
        self.assertRaises(ValueError,
                          utils.get_updated_capabilities,
                          capabilities, {})

    def test_get_updated_capabilities_capabilities_not_dict(self):
        capabilities = ['ilo_firmware_version:xyz', 'foo:bar']
        self.assertRaises(ValueError,
                          utils.get_updated_capabilities,
                          None, capabilities)

    def test_get_updated_capabilities_add_to_existing_capabilities(self):
        new_capabilities = {'BootMode': 'uefi'}
        expected_capabilities = 'BootMode:uefi,foo:bar'
        cap_returned = utils.get_updated_capabilities('foo:bar',
                                                      new_capabilities)
        set1 = set(expected_capabilities.split(','))
        set2 = set(cap_returned.split(','))
        self.assertEqual(set1, set2)
        self.assertIsInstance(cap_returned, str)

    def test_get_updated_capabilities_replace_to_existing_capabilities(self):
        new_capabilities = {'BootMode': 'bios'}
        expected_capabilities = 'BootMode:bios'
        cap_returned = utils.get_updated_capabilities('BootMode:uefi',
                                                      new_capabilities)
        set1 = set(expected_capabilities.split(','))
        set2 = set(cap_returned.split(','))
        self.assertEqual(set1, set2)
        self.assertIsInstance(cap_returned, str)

    def test_validate_network_port(self):
        port = utils.validate_network_port('0', 'message')
        self.assertEqual(0, port)
        port = utils.validate_network_port('65535')
        self.assertEqual(65535, port)

    def test_validate_network_port_fail(self):
        self.assertRaisesRegex(exception.InvalidParameterValue,
                               'Port "65536" is not a valid port.',
                               utils.validate_network_port,
                               '65536')
        self.assertRaisesRegex(exception.InvalidParameterValue,
                               'fake_port "-1" is not a valid port.',
                               utils.validate_network_port,
                               '-1',
                               'fake_port')
        self.assertRaisesRegex(exception.InvalidParameterValue,
                               'Port "invalid" is not a valid port.',
                               utils.validate_network_port,
                               'invalid')


class JinjaTemplatingTestCase(base.TestCase):

    def setUp(self):
        super(JinjaTemplatingTestCase, self).setUp()
        self.template = '{{ foo }} {{ bar }}'
        self.params = {'foo': 'spam', 'bar': 'ham'}
        self.expected = 'spam ham'

    def test_render_string(self):
        self.assertEqual(self.expected,
                         utils.render_template(self.template,
                                               self.params,
                                               is_file=False))

    def test_render_with_quotes(self):
        """test jinja2 autoescaping for everything is disabled """
        self.expected = '"spam" ham'
        self.params = {'foo': '"spam"', 'bar': 'ham'}
        self.assertEqual(self.expected,
                         utils.render_template(self.template,
                                               self.params,
                                               is_file=False))

    @mock.patch('ironic.common.utils.jinja2.FileSystemLoader', autospec=True)
    def test_render_file(self, jinja_fsl_mock):
        path = '/path/to/template.j2'
        jinja_fsl_mock.return_value = jinja2.DictLoader(
            {'template.j2': self.template})
        self.assertEqual(self.expected,
                         utils.render_template(path,
                                               self.params))
        jinja_fsl_mock.assert_called_once_with('/path/to')


class ValidateConductorGroupTestCase(base.TestCase):
    def test_validate_conductor_group_success(self):
        self.assertIsNone(utils.validate_conductor_group('foo'))
        self.assertIsNone(utils.validate_conductor_group('group1'))
        self.assertIsNone(utils.validate_conductor_group('group1.with.dot'))
        self.assertIsNone(utils.validate_conductor_group('group1_with_under'))
        self.assertIsNone(utils.validate_conductor_group('group1-with-dash'))

    def test_validate_conductor_group_fail(self):
        self.assertRaises(exception.InvalidConductorGroup,
                          utils.validate_conductor_group, 'foo:bar')
        self.assertRaises(exception.InvalidConductorGroup,
                          utils.validate_conductor_group, 'foo*bar')
        self.assertRaises(exception.InvalidConductorGroup,
                          utils.validate_conductor_group, 'foo$bar')
        self.assertRaises(exception.InvalidConductorGroup,
                          utils.validate_conductor_group, object())
        self.assertRaises(exception.InvalidConductorGroup,
                          utils.validate_conductor_group, None)


class UnlinkTestCase(base.TestCase):

    def test_unlink(self):
        with mock.patch.object(os, "unlink", autospec=True) as unlink_mock:
            unlink_mock.return_value = None
            utils.unlink_without_raise("/fake/path")
            unlink_mock.assert_called_once_with("/fake/path")

    def test_unlink_ENOENT(self):
        with mock.patch.object(os, "unlink", autospec=True) as unlink_mock:
            unlink_mock.side_effect = OSError(errno.ENOENT)
            utils.unlink_without_raise("/fake/path")
            unlink_mock.assert_called_once_with("/fake/path")


class ExecuteTestCase(base.TestCase):
    # Allow calls to utils.execute() and related functions
    block_execute = False

    @mock.patch.object(processutils, 'execute', autospec=True)
    @mock.patch.object(os.environ, 'copy', return_value={}, autospec=True)
    def test_execute_use_standard_locale_no_env_variables(self, env_mock,
                                                          execute_mock):
        utils.execute('foo', use_standard_locale=True)
        execute_mock.assert_called_once_with('foo',
                                             env_variables={'LC_ALL': 'C'})

    @mock.patch.object(processutils, 'execute', autospec=True)
    def test_execute_use_standard_locale_with_env_variables(self,
                                                            execute_mock):
        utils.execute('foo', use_standard_locale=True,
                      env_variables={'foo': 'bar'})
        execute_mock.assert_called_once_with('foo',
                                             env_variables={'LC_ALL': 'C',
                                                            'foo': 'bar'})

    @mock.patch.object(processutils, 'execute', autospec=True)
    def test_execute_not_use_standard_locale(self, execute_mock):
        utils.execute('foo', use_standard_locale=False,
                      env_variables={'foo': 'bar'})
        execute_mock.assert_called_once_with('foo',
                                             env_variables={'foo': 'bar'})

    @mock.patch.object(utils, 'LOG', autospec=True)
    def _test_execute_with_log_stdout(self, log_mock, log_stdout=None):
        with mock.patch.object(
                processutils, 'execute', autospec=True) as execute_mock:
            execute_mock.return_value = ('stdout', 'stderr')
            if log_stdout is not None:
                utils.execute('foo', log_stdout=log_stdout)
            else:
                utils.execute('foo')
            execute_mock.assert_called_once_with('foo')
            name, args, kwargs = log_mock.debug.mock_calls[0]
            if log_stdout is False:
                self.assertEqual(1, log_mock.debug.call_count)
                self.assertNotIn('stdout', args[0])
            else:
                self.assertEqual(2, log_mock.debug.call_count)
                self.assertIn('stdout', args[0])

    def test_execute_with_log_stdout_default(self):
        self._test_execute_with_log_stdout()

    def test_execute_with_log_stdout_true(self):
        self._test_execute_with_log_stdout(log_stdout=True)

    def test_execute_with_log_stdout_false(self):
        self._test_execute_with_log_stdout(log_stdout=False)

    @mock.patch.object(utils, 'LOG', autospec=True)
    @mock.patch.object(processutils, 'execute', autospec=True)
    def test_execute_command_not_found(self, execute_mock, log_mock):
        execute_mock.side_effect = FileNotFoundError
        self.assertRaises(FileNotFoundError, utils.execute, 'foo')
        execute_mock.assert_called_once_with('foo')
        name, args, kwargs = log_mock.debug.mock_calls[0]
        self.assertEqual(1, log_mock.debug.call_count)
        self.assertIn('not found', args[0])


class MkfsTestCase(base.TestCase):

    @mock.patch.object(utils, 'execute', autospec=True)
    def test_mkfs(self, execute_mock):
        utils.mkfs('ext4', '/my/block/dev')
        utils.mkfs('msdos', '/my/msdos/block/dev')
        utils.mkfs('swap', '/my/swap/block/dev')

        expected = [mock.call('mkfs', '-t', 'ext4', '-F', '/my/block/dev',
                              use_standard_locale=True),
                    mock.call('mkfs', '-t', 'msdos', '/my/msdos/block/dev',
                              use_standard_locale=True),
                    mock.call('mkswap', '/my/swap/block/dev',
                              use_standard_locale=True)]
        self.assertEqual(expected, execute_mock.call_args_list)

    @mock.patch.object(utils, 'execute', autospec=True)
    def test_mkfs_with_label(self, execute_mock):
        utils.mkfs('ext4', '/my/block/dev', 'ext4-vol')
        utils.mkfs('msdos', '/my/msdos/block/dev', 'msdos-vol')
        utils.mkfs('swap', '/my/swap/block/dev', 'swap-vol')

        expected = [mock.call('mkfs', '-t', 'ext4', '-F', '-L', 'ext4-vol',
                              '/my/block/dev',
                              use_standard_locale=True),
                    mock.call('mkfs', '-t', 'msdos', '-n', 'msdos-vol',
                              '/my/msdos/block/dev',
                              use_standard_locale=True),
                    mock.call('mkswap', '-L', 'swap-vol',
                              '/my/swap/block/dev',
                              use_standard_locale=True)]
        self.assertEqual(expected, execute_mock.call_args_list)

    @mock.patch.object(utils, 'execute', autospec=True,
                       side_effect=processutils.ProcessExecutionError(
                           stderr=os.strerror(errno.ENOENT)))
    def test_mkfs_with_unsupported_fs(self, execute_mock):
        self.assertRaises(exception.FileSystemNotSupported,
                          utils.mkfs, 'foo', '/my/block/dev')

    @mock.patch.object(utils, 'execute', autospec=True,
                       side_effect=processutils.ProcessExecutionError(
                           stderr='fake'))
    def test_mkfs_with_unexpected_error(self, execute_mock):
        self.assertRaises(processutils.ProcessExecutionError, utils.mkfs,
                          'ext4', '/my/block/dev', 'ext4-vol')


class IsHttpUrlTestCase(base.TestCase):

    def test_is_http_url(self):
        self.assertTrue(utils.is_http_url('http://127.0.0.1'))
        self.assertTrue(utils.is_http_url('https://127.0.0.1'))
        self.assertTrue(utils.is_http_url('HTTP://127.1.2.3'))
        self.assertTrue(utils.is_http_url('HTTPS://127.3.2.1'))
        self.assertFalse(utils.is_http_url('Zm9vYmFy'))
        self.assertFalse(utils.is_http_url('11111111'))


class ParseRootDeviceTestCase(base.TestCase):

    def test_parse_root_device_hints_without_operators(self):
        root_device = {
            'wwn': '123456', 'model': 'FOO model', 'size': 12345,
            'serial': 'foo-serial', 'vendor': 'foo VENDOR with space',
            'name': '/dev/sda', 'wwn_with_extension': '123456111',
            'wwn_vendor_extension': '111', 'rotational': True,
            'hctl': '1:0:0:0', 'by_path': '/dev/disk/by-path/1:0:0:0'}
        result = utils.parse_root_device_hints(root_device)
        expected = {
            'wwn': 's== 123456', 'model': 's== foo%20model',
            'size': '== 12345', 'serial': 's== foo-serial',
            'vendor': 's== foo%20vendor%20with%20space',
            'name': 's== /dev/sda', 'wwn_with_extension': 's== 123456111',
            'wwn_vendor_extension': 's== 111', 'rotational': True,
            'hctl': 's== 1%3A0%3A0%3A0',
            'by_path': 's== /dev/disk/by-path/1%3A0%3A0%3A0'}
        self.assertEqual(expected, result)

    def test_parse_root_device_hints_with_operators(self):
        root_device = {
            'wwn': 's== 123456', 'model': 's== foo MODEL', 'size': '>= 12345',
            'serial': 's!= foo-serial', 'vendor': 's== foo VENDOR with space',
            'name': '<or> /dev/sda <or> /dev/sdb',
            'wwn_with_extension': 's!= 123456111',
            'wwn_vendor_extension': 's== 111', 'rotational': True,
            'hctl': 's== 1:0:0:0', 'by_path': 's== /dev/disk/by-path/1:0:0:0'}

        # Validate strings being normalized
        expected = copy.deepcopy(root_device)
        expected['model'] = 's== foo%20model'
        expected['vendor'] = 's== foo%20vendor%20with%20space'
        expected['hctl'] = 's== 1%3A0%3A0%3A0'
        expected['by_path'] = 's== /dev/disk/by-path/1%3A0%3A0%3A0'

        result = utils.parse_root_device_hints(root_device)
        # The hints already contain the operators, make sure we keep it
        self.assertEqual(expected, result)

    def test_parse_root_device_hints_string_compare_operator_name(self):
        root_device = {'name': 's== /dev/sdb'}
        # Validate strings being normalized
        expected = copy.deepcopy(root_device)
        result = utils.parse_root_device_hints(root_device)
        # The hints already contain the operators, make sure we keep it
        self.assertEqual(expected, result)

    def test_parse_root_device_hints_no_hints(self):
        result = utils.parse_root_device_hints({})
        self.assertIsNone(result)

    def test_parse_root_device_hints_convert_size(self):
        for size in (12345, '12345'):
            result = utils.parse_root_device_hints({'size': size})
            self.assertEqual({'size': '== 12345'}, result)

    def test_parse_root_device_hints_invalid_size(self):
        for value in ('not-int', -123, 0):
            self.assertRaises(ValueError, utils.parse_root_device_hints,
                              {'size': value})

    def test_parse_root_device_hints_int_or(self):
        expr = '<or> 123 <or> 456 <or> 789'
        result = utils.parse_root_device_hints({'size': expr})
        self.assertEqual({'size': expr}, result)

    def test_parse_root_device_hints_int_or_invalid(self):
        expr = '<or> 123 <or> non-int <or> 789'
        self.assertRaises(ValueError, utils.parse_root_device_hints,
                          {'size': expr})

    def test_parse_root_device_hints_string_or_space(self):
        expr = '<or> foo <or> foo bar <or> bar'
        expected = '<or> foo <or> foo%20bar <or> bar'
        result = utils.parse_root_device_hints({'model': expr})
        self.assertEqual({'model': expected}, result)

    def _parse_root_device_hints_convert_rotational(self, values,
                                                    expected_value):
        for value in values:
            result = utils.parse_root_device_hints({'rotational': value})
            self.assertEqual({'rotational': expected_value}, result)

    def test_parse_root_device_hints_convert_rotational(self):
        self._parse_root_device_hints_convert_rotational(
            (True, 'true', 'on', 'y', 'yes'), True)

        self._parse_root_device_hints_convert_rotational(
            (False, 'false', 'off', 'n', 'no'), False)

    def test_parse_root_device_hints_invalid_rotational(self):
        self.assertRaises(ValueError, utils.parse_root_device_hints,
                          {'rotational': 'not-bool'})

    def test_parse_root_device_hints_invalid_wwn(self):
        self.assertRaises(ValueError, utils.parse_root_device_hints,
                          {'wwn': 123})

    def test_parse_root_device_hints_invalid_wwn_with_extension(self):
        self.assertRaises(ValueError, utils.parse_root_device_hints,
                          {'wwn_with_extension': 123})

    def test_parse_root_device_hints_invalid_wwn_vendor_extension(self):
        self.assertRaises(ValueError, utils.parse_root_device_hints,
                          {'wwn_vendor_extension': 123})

    def test_parse_root_device_hints_invalid_model(self):
        self.assertRaises(ValueError, utils.parse_root_device_hints,
                          {'model': 123})

    def test_parse_root_device_hints_invalid_serial(self):
        self.assertRaises(ValueError, utils.parse_root_device_hints,
                          {'serial': 123})

    def test_parse_root_device_hints_invalid_vendor(self):
        self.assertRaises(ValueError, utils.parse_root_device_hints,
                          {'vendor': 123})

    def test_parse_root_device_hints_invalid_name(self):
        self.assertRaises(ValueError, utils.parse_root_device_hints,
                          {'name': 123})

    def test_parse_root_device_hints_invalid_hctl(self):
        self.assertRaises(ValueError, utils.parse_root_device_hints,
                          {'hctl': 123})

    def test_parse_root_device_hints_invalid_by_path(self):
        self.assertRaises(ValueError, utils.parse_root_device_hints,
                          {'by_path': 123})

    def test_parse_root_device_hints_non_existent_hint(self):
        self.assertRaises(ValueError, utils.parse_root_device_hints,
                          {'non-existent': 'foo'})

    def test_extract_hint_operator_and_values_single_value(self):
        expected = {'op': '>=', 'values': ['123']}
        self.assertEqual(
            expected, utils._extract_hint_operator_and_values(
                '>= 123', 'size'))

    def test_extract_hint_operator_and_values_multiple_values(self):
        expected = {'op': '<or>', 'values': ['123', '456', '789']}
        expr = '<or> 123 <or> 456 <or> 789'
        self.assertEqual(
            expected, utils._extract_hint_operator_and_values(expr, 'size'))

    def test_extract_hint_operator_and_values_multiple_values_space(self):
        expected = {'op': '<or>', 'values': ['foo', 'foo bar', 'bar']}
        expr = '<or> foo <or> foo bar <or> bar'
        self.assertEqual(
            expected, utils._extract_hint_operator_and_values(expr, 'model'))

    def test_extract_hint_operator_and_values_no_operator(self):
        expected = {'op': '', 'values': ['123']}
        self.assertEqual(
            expected, utils._extract_hint_operator_and_values('123', 'size'))

    def test_extract_hint_operator_and_values_empty_value(self):
        self.assertRaises(
            ValueError, utils._extract_hint_operator_and_values, '', 'size')

    def test_extract_hint_operator_and_values_integer(self):
        expected = {'op': '', 'values': ['123']}
        self.assertEqual(
            expected, utils._extract_hint_operator_and_values(123, 'size'))

    def test__append_operator_to_hints(self):
        root_device = {'serial': 'foo', 'size': 12345,
                       'model': 'foo model', 'rotational': True}
        expected = {'serial': 's== foo', 'size': '== 12345',
                    'model': 's== foo model', 'rotational': True}

        result = utils._append_operator_to_hints(root_device)
        self.assertEqual(expected, result)

    def test_normalize_hint_expression_or(self):
        expr = '<or> foo <or> foo bar <or> bar'
        expected = '<or> foo <or> foo%20bar <or> bar'
        result = utils._normalize_hint_expression(expr, 'model')
        self.assertEqual(expected, result)

    def test_normalize_hint_expression_in(self):
        expr = '<in> foo <in> foo bar <in> bar'
        expected = '<in> foo <in> foo%20bar <in> bar'
        result = utils._normalize_hint_expression(expr, 'model')
        self.assertEqual(expected, result)

    def test_normalize_hint_expression_op_space(self):
        expr = 's== test string with space'
        expected = 's== test%20string%20with%20space'
        result = utils._normalize_hint_expression(expr, 'model')
        self.assertEqual(expected, result)

    def test_normalize_hint_expression_op_no_space(self):
        expr = 's!= SpongeBob'
        expected = 's!= spongebob'
        result = utils._normalize_hint_expression(expr, 'model')
        self.assertEqual(expected, result)

    def test_normalize_hint_expression_no_op_space(self):
        expr = 'no operators'
        expected = 'no%20operators'
        result = utils._normalize_hint_expression(expr, 'model')
        self.assertEqual(expected, result)

    def test_normalize_hint_expression_no_op_no_space(self):
        expr = 'NoSpace'
        expected = 'nospace'
        result = utils._normalize_hint_expression(expr, 'model')
        self.assertEqual(expected, result)

    def test_normalize_hint_expression_empty_value(self):
        self.assertRaises(
            ValueError, utils._normalize_hint_expression, '', 'size')


class MatchRootDeviceTestCase(base.TestCase):

    def setUp(self):
        super(MatchRootDeviceTestCase, self).setUp()
        self.devices = [
            {'name': '/dev/sda', 'size': 64424509440, 'model': 'ok model',
             'serial': 'fakeserial'},
            {'name': '/dev/sdb', 'size': 128849018880, 'model': 'big model',
             'serial': 'veryfakeserial', 'rotational': 'yes'},
            {'name': '/dev/sdc', 'size': 10737418240, 'model': 'small model',
             'serial': 'veryveryfakeserial', 'rotational': False},
        ]

    def test_match_root_device_hints_one_hint(self):
        root_device_hints = {'size': '>= 70'}
        dev = utils.match_root_device_hints(self.devices, root_device_hints)
        self.assertEqual('/dev/sdb', dev['name'])

    def test_match_root_device_hints_rotational(self):
        root_device_hints = {'rotational': False}
        dev = utils.match_root_device_hints(self.devices, root_device_hints)
        self.assertEqual('/dev/sdc', dev['name'])

    def test_match_root_device_hints_rotational_convert_devices_bool(self):
        root_device_hints = {'size': '>=100', 'rotational': True}
        dev = utils.match_root_device_hints(self.devices, root_device_hints)
        self.assertEqual('/dev/sdb', dev['name'])

    def test_match_root_device_hints_multiple_hints(self):
        root_device_hints = {'size': '>= 50', 'model': 's==big model',
                             'serial': 's==veryfakeserial'}
        dev = utils.match_root_device_hints(self.devices, root_device_hints)
        self.assertEqual('/dev/sdb', dev['name'])

    def test_match_root_device_hints_multiple_hints2(self):
        root_device_hints = {
            'size': '<= 20',
            'model': '<or> model 5 <or> foomodel <or> small model <or>',
            'serial': 's== veryveryfakeserial'}
        dev = utils.match_root_device_hints(self.devices, root_device_hints)
        self.assertEqual('/dev/sdc', dev['name'])

    def test_match_root_device_hints_multiple_hints3(self):
        root_device_hints = {'rotational': False, 'model': '<in> small'}
        dev = utils.match_root_device_hints(self.devices, root_device_hints)
        self.assertEqual('/dev/sdc', dev['name'])

    def test_match_root_device_hints_no_operators(self):
        root_device_hints = {'size': '120', 'model': 'big model',
                             'serial': 'veryfakeserial'}
        dev = utils.match_root_device_hints(self.devices, root_device_hints)
        self.assertEqual('/dev/sdb', dev['name'])

    def test_match_root_device_hints_no_device_found(self):
        root_device_hints = {'size': '>=50', 'model': 's==foo'}
        dev = utils.match_root_device_hints(self.devices, root_device_hints)
        self.assertIsNone(dev)

    @mock.patch.object(utils.LOG, 'warning', autospec=True)
    def test_match_root_device_hints_empty_device_attribute(self, mock_warn):
        empty_dev = [{'name': '/dev/sda', 'model': ' '}]
        dev = utils.match_root_device_hints(empty_dev, {'model': 'foo'})
        self.assertIsNone(dev)
        self.assertTrue(mock_warn.called)

    def test_find_devices_all(self):
        root_device_hints = {'size': '>= 10'}
        devs = list(utils.find_devices_by_hints(self.devices,
                                                root_device_hints))
        self.assertEqual(self.devices, devs)

    def test_find_devices_none(self):
        root_device_hints = {'size': '>= 100500'}
        devs = list(utils.find_devices_by_hints(self.devices,
                                                root_device_hints))
        self.assertEqual([], devs)

    def test_find_devices_name(self):
        root_device_hints = {'name': 's== /dev/sda'}
        devs = list(utils.find_devices_by_hints(self.devices,
                                                root_device_hints))
        self.assertEqual([self.devices[0]], devs)


@mock.patch.object(utils, 'execute', autospec=True)
class GetRouteSourceTestCase(base.TestCase):

    def test_get_route_source_ipv4(self, mock_execute):
        mock_execute.return_value = ('XXX src 1.2.3.4 XXX\n    cache', None)

        source = utils.get_route_source('XXX')
        self.assertEqual('1.2.3.4', source)

    def test_get_route_source_ipv6(self, mock_execute):
        mock_execute.return_value = ('XXX src 1:2::3:4 metric XXX\n    cache',
                                     None)

        source = utils.get_route_source('XXX')
        self.assertEqual('1:2::3:4', source)

    def test_get_route_source_ipv6_linklocal(self, mock_execute):
        mock_execute.return_value = (
            'XXX src fe80::1234:1234:1234:1234 metric XXX\n    cache', None)

        source = utils.get_route_source('XXX')
        self.assertIsNone(source)

    def test_get_route_source_ipv6_linklocal_allowed(self, mock_execute):
        mock_execute.return_value = (
            'XXX src fe80::1234:1234:1234:1234 metric XXX\n    cache', None)

        source = utils.get_route_source('XXX', ignore_link_local=False)
        self.assertEqual('fe80::1234:1234:1234:1234', source)

    def test_get_route_source_indexerror(self, mock_execute):
        mock_execute.return_value = ('XXX src \n    cache', None)

        source = utils.get_route_source('XXX')
        self.assertIsNone(source)
