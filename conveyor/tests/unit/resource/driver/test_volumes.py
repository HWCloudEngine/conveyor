# Copyright (c) 2017 Huawei, Inc.
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
import mock

from conveyor import context
from conveyor import exception
from conveyor.resource.driver import volumes
from conveyor.resource import resource
from conveyor.tests import test
from conveyor.volume import cinder

fake_volume_dict = {
    "migration_status": None,
    "attachments": [],
    "availability_zone": "az01.dc1--fusionsphere",
    "os-vol-host-attr:host": "az01.dc1--fusionsphere#LVM_ISCSI",
    "replication_status": "disabled",
    "snapshot_id": None,
    "id": "c49b5354-d49b-443f-93c3-770e7f18c81d",
    "size": 5,
    "status": "available",
    "display_description": None,
    "multiattach": False,
    "os-vol-mig-status-attr:name_id": None,
    "display_name": "vol-az01-vol2",
    "bootable": "false",
    "created_at": "2017-04-25T12:02:58.374266",
    "volume_type": None
}

fake_volume_type_dict = {
    "name": "standard",
    "qos_specs_id": None,
    "extra_specs": {"availability-zone": "az02.ap-southeast-2--aws"},
    "os-volume-type-access:is_public": True,
    "is_public": True,
    "id": "f45c9720-c75a-4483-b0dd-a285d3e6734c",
    "description": None
}


class VolumeResourceTestCase(test.TestCase):

    def setUp(self):
        super(VolumeResourceTestCase, self).setUp()
        self.context = context.RequestContext('fake', 'fake', is_admin=False)
        self.volume_resource = volumes.VolumeResource(self.context)

    @mock.patch.object(cinder.API, "get_all")
    def test_extract_all_volumes(self, mock_all_volume):
        mock_all_volume.return_value = [copy.deepcopy(fake_volume_dict)]
        volume_res = self.volume_resource.extract_volumes([])
        self.assertTrue(len(volume_res))
        self.assertEqual(fake_volume_dict['id'], volume_res[0].id)
        self.assertEqual(1,
                         len(self.volume_resource.get_collected_resources()))

    @mock.patch.object(cinder.API, "get")
    def test_extract_volumes_with_ids(self, mock_volume):
        fake_volume_id = fake_volume_dict['id']
        mock_volume.return_value = copy.deepcopy(fake_volume_dict)
        volume_res = self.volume_resource.extract_volumes(fake_volume_id)
        self.assertTrue(len(volume_res))
        self.assertEqual(fake_volume_dict['id'], volume_res[0].id)
        self.assertEqual(1,
                         len(self.volume_resource.get_collected_resources()))

    @mock.patch.object(cinder.API, "get_volume_type")
    @mock.patch.object(cinder.API, "volume_type_list")
    @mock.patch.object(cinder.API, "get_all")
    def test_extract_volumes_with_volume_type(self, mock_all_volume,
                                              mock_vt_list, mock_volume_type):
        fake_volume = copy.deepcopy(fake_volume_dict)
        fake_volume.update({'volume_type': fake_volume_type_dict['name']})
        mock_all_volume.return_value = [fake_volume]
        mock_vt_list.return_value = [copy.deepcopy(fake_volume_type_dict)]
        mock_volume_type.return_value = copy.deepcopy(fake_volume_type_dict)

        volume_res = self.volume_resource.extract_volumes([])
        self.assertTrue(len(volume_res) == 1)
        self.assertEqual(2,
                         len(self.volume_resource.get_collected_resources()))

    @mock.patch.object(cinder.API, "get")
    def test_extract_volume_from_cache(self, mock_volume):
        mock_volume.return_value = copy.deepcopy(fake_volume_dict)
        fake_volume_id = fake_volume_dict['id']
        fake_volume_res = resource.Resource("volume", "OS::Cinder::Volume",
                                            fake_volume_id)
        fake_volume_dep = resource.ResourceDependency(fake_volume_id, "volume",
                                                      "volume_0",
                                                      "OS::Cinder::Volume")
        self.volume_resource = volumes.VolumeResource(
            self.context,
            collected_resources={fake_volume_id: fake_volume_res},
            collected_dependencies={fake_volume_id: fake_volume_dep})
        volume_res = self.volume_resource.extract_volumes([fake_volume_id])
        self.assertEqual(fake_volume_id, volume_res[0].id)

    @mock.patch.object(cinder.API, "get", side_effect=Exception)
    def test_extract_volumes_failed(self, mock_volume):
        self.assertRaises(exception.ResourceNotFound,
                          self.volume_resource.extract_volumes,
                          ['volume_123'])

    @mock.patch.object(cinder.API, "volume_type_list")
    def test_extract_all_volume_types(self, mock_volume_type_list):
        mock_volume_type_list.return_value = [
            copy.deepcopy(fake_volume_type_dict)]
        result = self.volume_resource.extract_volume_types([])
        self.assertTrue(len(result) == 1)
        self.assertEqual(fake_volume_type_dict["id"], result[0].id)
        self.assertTrue(len(self.volume_resource.get_collected_resources()))
        self.assertTrue(len(self.volume_resource.get_collected_dependencies()))

    @mock.patch.object(cinder.API, "get_volume_type")
    def test_extract_volume_types_with_ids(self, mock_volume_type):
        fake_vt_id = fake_volume_type_dict['id']
        mock_volume_type.return_value = copy.deepcopy(fake_volume_type_dict)
        result = self.volume_resource.extract_volume_types([fake_vt_id])
        self.assertTrue(len(result) == 1)
        self.assertEqual(fake_vt_id, result[0].id)
        self.assertTrue(len(self.volume_resource.get_collected_resources()))
        self.assertTrue(len(self.volume_resource.get_collected_dependencies()))

    @mock.patch.object(cinder.API, "get_qos_specs")
    @mock.patch.object(cinder.API, "get_volume_type")
    def test_extract_volume_types_with_qos(self, mock_volume_type,
                                           mock_qos_specs):
        fake_vt = copy.deepcopy(fake_volume_type_dict)
        fake_vt_id = fake_vt['id']
        fake_vt.update({'qos_specs_id': 'qos_123'})
        mock_volume_type.return_value = fake_vt
        mock_qos_specs.return_value = {
            "id": "qos_123",
            "name": "qos",
            "specs": {"iops": 100}
        }
        result = self.volume_resource.extract_volume_types([fake_vt_id])
        self.assertEqual(fake_vt_id, result[0].id)
        self.assertTrue(
            len(self.volume_resource.get_collected_resources()) == 2)
        self.assertTrue(
            len(self.volume_resource.get_collected_dependencies()) == 2)

    @mock.patch.object(cinder.API, "get_volume_type", side_effect=Exception)
    def test_extract_volume_types_failed(self, mock_volume_type):
        self.assertRaises(exception.ResourceNotFound,
                          self.volume_resource.extract_volume_types,
                          'volume_type_123')

    def test_extract_image(self):
        fake_image_id = "image_123"
        result = self.volume_resource.extract_image(fake_image_id)
        self.assertIsNotNone(result)
        self.assertIn(fake_image_id,
                      self.volume_resource._collected_parameters)


class VolumeTestCase(test.TestCase):

    def setUp(self):
        super(VolumeTestCase, self).setUp()
        self.context = context.RequestContext('fake', 'fake', is_admin=False)
        self.vol_resource = volumes.Volume(self.context)

    @mock.patch.object(cinder.API, 'get')
    def test_extract_volumes(self, mock_vol):
        fake_vol = copy.deepcopy(fake_volume_dict)
        mock_vol.return_value = fake_vol
        self.vol_resource.extract_volumes([fake_vol['id']])
        self.assertTrue(1 == len(self.vol_resource.get_collected_resources()))

    def test_extract_volumes_with_invalid_input(self):
        self.assertRaises(exception.InvalidInput,
                          self.vol_resource.extract_volumes,
                          None)

    @mock.patch.object(cinder.API, 'get')
    def test_extract_volume(self, mock_volume):
        # NOTE: for the object volumes.Volume, it does not contain method
        # extract_image, so evoking method extract_volume will cause error in
        # some switch_case.
        fake_vol = copy.deepcopy(fake_volume_dict)
        mock_volume.return_value = fake_vol
        result = self.vol_resource.extract_volume(fake_vol['id'])
        self.assertEqual(fake_vol['id'], result.id)

    @mock.patch.object(cinder.API, "get_volume_type")
    @mock.patch.object(cinder.API, "volume_type_list")
    @mock.patch.object(cinder.API, 'get')
    def test_extract_volume_with_volume_type(self, mock_volume,
                                             mock_vt_list, mock_vt):
        fake_vol = copy.deepcopy(fake_volume_dict)
        fake_vol.update({'volume_type': fake_volume_type_dict['name']})
        mock_volume.return_value = fake_vol
        mock_vt_list.return_value = [copy.deepcopy(fake_volume_type_dict)]
        mock_vt.return_value = copy.deepcopy(fake_volume_type_dict)

        result = self.vol_resource.extract_volume(fake_vol['id'])
        self.assertEqual(fake_vol['id'], result.id)
        self.assertEqual(2, len(self.vol_resource.get_collected_resources()))

    @mock.patch.object(cinder.API, 'get', side_effect=Exception)
    def test_extract_unexist_volume(self, mock_volume):
        self.assertRaises(exception.ResourceNotFound,
                          self.vol_resource.extract_volume,
                          'vol_123')

    @mock.patch.object(cinder.API, 'get')
    def test_extract_not_allowed_volume(self, mock_volume):
        fake_vol = copy.deepcopy(fake_volume_dict)
        fake_vol.update({'status': 'error'})
        mock_volume.return_value = fake_vol
        self.assertRaises(exception.PlanCreateFailed,
                          self.vol_resource.extract_volume,
                          fake_vol['id'])

    @mock.patch.object(cinder.API, 'get')
    def test_extract_volume_from_cache(self, mock_volume):
        fake_vol = copy.deepcopy(fake_volume_dict)
        fake_vol_name = fake_vol['display_name']
        fake_vol_id = fake_vol['id']
        mock_volume.return_value = fake_vol
        fake_vol_res = resource.Resource(fake_vol_name,
                                         'OS::Cinder::Volume',
                                         fake_vol_id)
        fake_vol_dep = resource.ResourceDependency(fake_vol_id,
                                                   fake_vol_name,
                                                   'volume_0',
                                                   'OS::Cinder::Volume')
        self.vol_resource = volumes.Volume(
            self.context,
            collected_resources={fake_vol_id: fake_vol_res},
            collected_dependencies={fake_vol_id: fake_vol_dep})
        result = self.vol_resource.extract_volume(fake_vol_id)
        self.assertEqual(fake_vol_id, result.id)


class VolumeTypeTestCase(test.TestCase):

    def setUp(self):
        super(VolumeTypeTestCase, self).setUp()
        self.context = context.RequestContext('fake', 'fake', is_admin=False)
        self.vt_resource = volumes.VolumeType(self.context)

    @mock.patch.object(cinder.API, 'get_volume_type')
    def test_extract_volume_types(self, mock_vt):
        fake_vt = copy.deepcopy(fake_volume_type_dict)
        mock_vt.return_value = fake_vt
        result = self.vt_resource.extract_volume_types([fake_vt['id']])
        self.assertEqual(1, len(result))
        self.assertEqual(fake_vt['id'], result[0].id)

    def test_extract_volume_types_without_input(self):
        self.assertRaises(exception.InvalidInput,
                          self.vt_resource.extract_volume_types,
                          [])

    @mock.patch.object(cinder.API, 'get_volume_type')
    def test_extract_volume_type(self, mock_vt):
        fake_vt = copy.deepcopy(fake_volume_type_dict)
        mock_vt.return_value = fake_vt
        fake_vt_id = fake_vt['id']
        result = self.vt_resource.extract_volume_type(fake_vt_id)
        self.assertEqual(fake_vt_id, result.id)

    @mock.patch.object(cinder.API, "get_qos_specs")
    @mock.patch.object(cinder.API, 'get_volume_type')
    def test_extract_volume_type_with_qos(self, mock_vt, mock_qos):
        fake_vt = copy.deepcopy(fake_volume_type_dict)
        fake_qos_id = "qos_123"
        fake_vt.update({'qos_specs_id': fake_qos_id})
        mock_vt.return_value = fake_vt
        mock_qos.return_value = {
            "id": fake_qos_id,
            "name": "qos",
            "specs": {"iops": 100}
        }
        fake_vt_id = fake_vt['id']
        result = self.vt_resource.extract_volume_type(fake_vt_id)
        self.assertEqual(fake_vt_id, result.id)
        self.assertEqual(2, len(self.vt_resource.get_collected_resources()))

    @mock.patch.object(cinder.API, 'get_volume_type')
    def test_extract_volume_type_from_cache(self, mock_vt):
        fake_vt = copy.deepcopy(fake_volume_type_dict)
        mock_vt.return_value = fake_vt
        fake_vt_id = fake_vt['id']
        fake_vt_name = fake_vt['name']

        fake_vt_res = resource.Resource(fake_vt_name, 'OS::Cinder::VolumeType',
                                        fake_vt_id)
        fake_vt_dep = resource.ResourceDependency(fake_vt_id, fake_vt_name,
                                                  'vt_0',
                                                  'OS::Cinder::VolumeType')
        self.vt_resource = volumes.VolumeType(
            self.context,
            collected_resources={fake_vt_id: fake_vt_res},
            collected_dependencies={fake_vt_id: fake_vt_dep})
        result = self.vt_resource.extract_volume_type(fake_vt_id)
        self.assertEqual(fake_vt_id, result.id)

    @mock.patch.object(cinder.API, 'get_volume_type', side_effect=Exception)
    def test_extract_unexist_volume_type(self, mock_vt):
        self.assertRaises(exception.ResourceNotFound,
                          self.vt_resource.extract_volume_type,
                          'vt_123')


class QosResourceTestCase(test.TestCase):

    def setUp(self):
        super(QosResourceTestCase, self).setUp()
        self.context = context.RequestContext('fake', 'fake', is_admin=False)
        self.qos_resource = volumes.QosResource(self.context)

    @mock.patch.object(cinder.API, "get_qos_specs")
    def test_extract_qos(self, mock_qos_specs):
        fake_qos_id = "qos_123"
        mock_qos_specs.return_value = {
            "id": fake_qos_id,
            "name": "qos",
            "specs": {"iops": 100}
        }
        qos_res = self.qos_resource.extract_qos(fake_qos_id)
        self.assertEqual("qos_123", qos_res.id)
        self.assertTrue(len(self.qos_resource.get_collected_resources()))
        self.assertTrue(len(self.qos_resource.get_collected_dependencies()))

    def test_extract_qos_from_cache(self):
        fake_qos_id = "qos_123"
        fake_qos_res = resource.Resource("qos", "OS::Cinder::Qos", fake_qos_id)
        fake_qos_dep = resource.ResourceDependency(fake_qos_id, "qos",
                                                   "CinderQos_0",
                                                   "OS::Cinder::Qos")
        self.qos_resource = volumes.QosResource(
            self.context,
            collected_resources={fake_qos_id: fake_qos_res},
            collected_dependencies={fake_qos_id: fake_qos_dep})
        qos_res = self.qos_resource.extract_qos(fake_qos_id)
        self.assertEqual(fake_qos_id, qos_res.id)

    @mock.patch.object(cinder.API, "get_qos_specs", side_effect=Exception)
    def test_extract_qos_failed(self, mock_qos_specs):
        self.assertRaises(exception.ResourceExtractFailed,
                          self.qos_resource.extract_qos,
                          'qos_123')
