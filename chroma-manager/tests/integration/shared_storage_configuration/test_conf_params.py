from testconfig import config

from tests.integration.core.chroma_integration_testcase import ChromaIntegrationTestCase


class TestConfParams(ChromaIntegrationTestCase):
    def _create_with_params(self):
        self.hosts = self.add_hosts([
            config['lustre_servers'][0]['address'],
            config['lustre_servers'][1]['address'],
        ])

        # Since the test code seems to rely on this ordering, we should
        # check for it right away and blow up if it's not as we expect.
        self.assertEqual([h['address'] for h in self.hosts],
                         [config['lustre_servers'][0]['address'],
                          config['lustre_servers'][1]['address']])

        volumes = self.get_usable_volumes()
        self.assertGreaterEqual(len(volumes), 4)

        mgt_volume = volumes[0]
        mdt_volume = volumes[1]
        ost_volume = volumes[2]
        self.set_volume_mounts(mgt_volume, self.hosts[0]['id'], self.hosts[1]['id'])
        self.set_volume_mounts(mdt_volume, self.hosts[0]['id'], self.hosts[1]['id'])
        self.set_volume_mounts(ost_volume, self.hosts[0]['id'], self.hosts[1]['id'])

        self.filesystem_id = self.create_filesystem(
                {
                'name': 'testfs',
                'mgt': {'volume_id': mgt_volume['id']},
                'mdt': {
                    'volume_id': mdt_volume['id'],
                    'conf_params': {'lov.stripesize': '2097152'}

                },
                'osts': [{
                    'volume_id': ost_volume['id'],
                    'conf_params': {'ost.writethrough_cache_enable': '0'}
                }],
                'conf_params': {'llite.max_cached_mb': '16'}
            }
        )

    def _test_params(self):
        # Mount the filesystem
        response = self.chroma_manager.get(
            '/api/filesystem/',
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json['objects']), 1)
        filesystem = response.json['objects'][0]
        client = config['lustre_clients'][0]['address']
        self.remote_operations.mount_filesystem(client, filesystem)

        try:
            self.assertIn("max_cached_mb: 16", self.remote_operations.read_proc(client, "/proc/fs/lustre/llite/*/max_cached_mb"))

            server_address = self.hosts[0]['address']
            self.wait_until_true(lambda: "2097152" == self.remote_operations.read_proc(server_address, "/proc/fs/lustre/lov/testfs-MDT0000-mdtlov/stripesize"))
            self.wait_until_true(lambda: "0" == self.remote_operations.read_proc(server_address, "/proc/fs/lustre/obdfilter/testfs-OST0000/writethrough_cache_enable"))
        finally:
            self.remote_operations.unmount_filesystem(client, filesystem)

    def test_creation_conf_params(self):
        self._create_with_params()
        self._test_params()
        self.graceful_teardown(self.chroma_manager)

    def test_writeconf_conf_params(self):
        self._create_with_params()
        self._test_params()

        # Check that conf params are preserved across a writeconf
        command = self.chroma_manager.post("/api/command/", body = {
            'jobs': [{'class_name': 'UpdateNidsJob', 'args': {}}],
            'message': "Test writeconf"
        }).json
        self.wait_for_command(self.chroma_manager, command['id'])

        fs_uri = "/api/filesystem/%s/" % self.filesystem_id
        response = self.chroma_manager.get(fs_uri)
        self.assertEqual(response.status_code, 200)
        fs = response.json

        # FIXME: HYD-1133: have to manually ensure the MGT comes up first
        # after a writeconf
        self.set_state(fs['mgt']['resource_uri'], 'mounted')
        self.set_state(fs['mdts'][0]['resource_uri'], 'mounted')
        self.set_state(fs['resource_uri'], 'available')

        self._test_params()

        self.graceful_teardown(self.chroma_manager)

    def test_update_conf_params(self):
        self.add_hosts([config['lustre_servers'][0]['address']])

        ha_volumes = self.get_usable_volumes()
        self.assertGreaterEqual(len(ha_volumes), 4)

        mgt_volume = ha_volumes[0]
        mdt_volume = ha_volumes[1]
        ost_volumes = [ha_volumes[2]]
        filesystem_id = self.create_filesystem({
                'name': 'testfs',
                'mgt': {'volume_id': mgt_volume['id']},
                'mdt': {
                    'volume_id': mdt_volume['id'],
                    'conf_params': {}
                },
                'osts': [{
                    'volume_id': v['id'],
                    'conf_params': {}
                } for v in ost_volumes],
                'conf_params': {}
            }
        )

        # Mount the filesystem
        response = self.chroma_manager.get(
            '/api/filesystem/%s/' % filesystem_id,
        )
        self.assertEqual(response.successful, True, response.text)
        filesystem = response.json
        client = config['lustre_clients'][0]['address']

        # Mount and check that the existing value is different to what we will set
        self.remote_operations.mount_filesystem(client, filesystem)
        new_conf_params = {'llite.max_cached_mb': '16'}
        try:
            self.assertNotIn(
                "max_cached_mb: %s" % new_conf_params['llite.max_cached_mb'],
                self.remote_operations.read_proc(client, "/proc/fs/lustre/llite/*/max_cached_mb"))
        finally:
            self.remote_operations.unmount_filesystem(client, filesystem)

        # Set our new conf param
        filesystem = self.chroma_manager.get("/api/filesystem/" + filesystem_id + "/").json
        for k, v in new_conf_params.items():
            filesystem['conf_params'][k] = v
        response = self.chroma_manager.put(filesystem['resource_uri'], filesystem)
        self.assertEqual(response.status_code, 202, response.content)
        command = response.json['command']
        filesystem = response.json['filesystem']
        self.assertDictContainsSubset(new_conf_params, filesystem['conf_params'])
        self.wait_for_command(self.chroma_manager, command['id'])

        # Mount and check that the new value has made it through
        self.remote_operations.mount_filesystem(client, filesystem)
        try:
            self.assertIn(
                "max_cached_mb: %s" % new_conf_params['llite.max_cached_mb'],
                self.remote_operations.read_proc(client, "/proc/fs/lustre/llite/*/max_cached_mb"))
        finally:
            self.remote_operations.unmount_filesystem(client, filesystem)

        self.graceful_teardown(self.chroma_manager)
