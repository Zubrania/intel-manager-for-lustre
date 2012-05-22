from chroma_core.lib.state_manager import DepCache, LockCache
from chroma_core.lib.util import dbperf
from chroma_core.models.filesystem import ManagedFilesystem
from chroma_core.models.host import ManagedHost
from chroma_core.models.jobs import Command, Job
from chroma_core.models.target import ManagedMdt, ManagedMgs, ManagedOst
import settings
from tests.unit.chroma_core.helper import JobTestCaseWithHost, freshen, JobTestCase
from django.db import connection


class TestBigFilesystem(JobTestCase):
    mock_servers = {}

    def setUp(self):
        super(TestBigFilesystem, self).setUp()
        connection.use_debug_cursor = True

    def test_big_filesystem(self):
        OSS_COUNT = 4
        OST_COUNT = 32

        assert OST_COUNT % OSS_COUNT == 0

        for i, address in enumerate(["oss%d" % i for i in range(0, OSS_COUNT)] + ['mds0', 'mds1', 'mgs0', 'mgs1']):
            self.mock_servers[address] = {
                'fqdn': address,
                'nodename': address,
                'nids': ["192.168.0.%d@tcp0" % i]
            }

        settings.DEBUG = True
        with dbperf("object creation"):
            self.mgs0, command = ManagedHost.create_from_string('mgs0')
            self.mgs1, command = ManagedHost.create_from_string('mgs1')
            self.mds0, command = ManagedHost.create_from_string('mds0')
            self.mds1, command = ManagedHost.create_from_string('mds1')
            self.osss = {}
            for i in range(0, OSS_COUNT):
                oss, command = ManagedHost.create_from_string('oss%d' % i)
                self.osss[i] = oss

            self.mgt = ManagedMgs.create_for_volume(self._test_lun(self.mgs0, self.mgs1).id, name = "MGS")
            self.fs = ManagedFilesystem.objects.create(mgs = self.mgt, name = "testfs")
            self.mdt = ManagedMdt.create_for_volume(self._test_lun(self.mds0, self.mds1).id, filesystem = self.fs)

            self.osts = {}
            for i in range(0, OST_COUNT):
                primary_oss_i = (i * OSS_COUNT) / OST_COUNT
                if primary_oss_i % 2 == 1:
                    secondary_oss_i = primary_oss_i - 1
                else:
                    secondary_oss_i = primary_oss_i + 1
                primary_oss = self.osss[primary_oss_i]
                secondary_oss = self.osss[secondary_oss_i]
                self.osts[i] = ManagedOst.create_for_volume(self._test_lun(primary_oss, secondary_oss).id, filesystem = self.fs)

                #GOOD MORNING, IT DOESN'T WORK WHEN DEPCACHE IS ENABLED, WHY IS THAT?
                #GET THAT WORKING, THEN MAKE IT FASTER AGAIN:
                # * WOULD IT HELP IF JOBS WEREN'T USING MTI?
                # * WOULD IT HELP IF WE DID BULK INSERTS FOR THE LOCKS, DEP LINKS?
                # * WOULD IT HELP TO PROVIDE GET_DEPS METHODS WITH A CACHE OF STATEFULOBJECTS?

        dbperf.enabled = True

        with dbperf("set_state"):
            Command.set_state([(self.fs, 'available')], "Unit test transition", run = False)

        # Imagine we're now running in a job worker instead of the serialize
        # worker, so the cache isn't going to be primed any more
        dc = DepCache.getInstance()
        print "DepCache: %d, %d" % (dc.hits, dc.misses)

        if False:
            DepCache.clear()
            LockCache.clear()

            with dbperf("job execution"):
                Job.run_next()

            dc = DepCache.getInstance()
            print "DepCache: %d, %d" % (dc.hits, dc.misses)

            self.assertEqual(freshen(self.fs).state, 'available')


class TestFSTransitions(JobTestCaseWithHost):
    def setUp(self):
        super(TestFSTransitions, self).setUp()

        from chroma_core.models import ManagedMgs, ManagedMdt, ManagedOst, ManagedFilesystem
        self.mgt = ManagedMgs.create_for_volume(self._test_lun(self.host).id, name = "MGS")
        self.fs = ManagedFilesystem.objects.create(mgs = self.mgt, name = "testfs")
        self.mdt = ManagedMdt.create_for_volume(self._test_lun(self.host).id, filesystem = self.fs)
        self.ost = ManagedOst.create_for_volume(self._test_lun(self.host).id, filesystem = self.fs)

        self.assertEqual(ManagedMgs.objects.get(pk = self.mgt.pk).state, 'unformatted')
        self.assertEqual(ManagedMdt.objects.get(pk = self.mdt.pk).state, 'unformatted')
        self.assertEqual(ManagedOst.objects.get(pk = self.ost.pk).state, 'unformatted')

        self.set_state(self.fs, 'available')

        self.assertEqual(ManagedMgs.objects.get(pk = self.mgt.pk).state, 'mounted')
        self.assertEqual(ManagedMdt.objects.get(pk = self.mdt.pk).state, 'mounted')
        self.assertEqual(ManagedOst.objects.get(pk = self.ost.pk).state, 'mounted')
        self.assertEqual(ManagedFilesystem.objects.get(pk = self.fs.pk).state, 'available')

    def test_mgs_removal(self):
        """Test that removing an MGS takes the filesystems with it"""
        self.set_state(self.mgt, 'removed')

    def test_fs_removal(self):
        """Test that removing a filesystem takes its targets with it"""
        from chroma_core.models import ManagedMdt, ManagedOst, ManagedFilesystem
        self.set_state(self.fs, 'removed')

        with self.assertRaises(ManagedMdt.DoesNotExist):
            ManagedMdt.objects.get(pk = self.mdt.pk)
        self.assertEqual(ManagedMdt._base_manager.get(pk = self.mdt.pk).state, 'removed')
        with self.assertRaises(ManagedOst.DoesNotExist):
            ManagedOst.objects.get(pk = self.ost.pk)
        self.assertEqual(ManagedOst._base_manager.get(pk = self.ost.pk).state, 'removed')
        with self.assertRaises(ManagedFilesystem.DoesNotExist):
            ManagedFilesystem.objects.get(pk = self.fs.pk)

    def test_target_stop(self):
        from chroma_core.models import ManagedMdt, ManagedFilesystem
        self.set_state(self.mdt, 'unmounted')
        self.assertEqual(ManagedMdt.objects.get(pk = self.mdt.pk).state, 'unmounted')
        self.assertEqual(ManagedFilesystem.objects.get(pk = self.fs.pk).state, 'unavailable')

    def test_target_start(self):
        from chroma_core.models import ManagedMdt, ManagedOst, ManagedFilesystem

        self.set_state(self.fs, 'stopped')
        self.set_state(self.mdt, 'mounted')

        self.assertEqual(ManagedMdt.objects.get(pk = self.mdt.pk).state, 'mounted')
        self.assertEqual(ManagedOst.objects.get(pk = self.ost.pk).state, 'unmounted')
        self.assertEqual(ManagedFilesystem.objects.get(pk = self.fs.pk).state, 'stopped')

    def test_stop_start(self):
        from chroma_core.models import ManagedMdt, ManagedOst, ManagedFilesystem
        self.set_state(self.fs, 'stopped')

        self.assertEqual(ManagedMdt.objects.get(pk = self.mdt.pk).state, 'unmounted')
        self.assertEqual(ManagedOst.objects.get(pk = self.ost.pk).state, 'unmounted')
        self.assertEqual(ManagedFilesystem.objects.get(pk = self.fs.pk).state, 'stopped')

        self.set_state(self.fs, 'available')

        self.assertEqual(ManagedMdt.objects.get(pk = self.mdt.pk).state, 'mounted')
        self.assertEqual(ManagedOst.objects.get(pk = self.ost.pk).state, 'mounted')
        self.assertEqual(ManagedFilesystem.objects.get(pk = self.fs.pk).state, 'available')


class TestDetectedFSTransitions(JobTestCaseWithHost):
    def setUp(self):
        super(TestDetectedFSTransitions, self).setUp()

        from chroma_core.models import ManagedMgs, ManagedMdt, ManagedOst, ManagedFilesystem
        self.mgt = ManagedMgs.create_for_volume(self._test_lun(self.host).id, name = "MGS")
        self.fs = ManagedFilesystem.objects.create(mgs = self.mgt, name = "testfs")
        self.mdt = ManagedMdt.create_for_volume(self._test_lun(self.host).id, filesystem = self.fs)
        self.ost = ManagedOst.create_for_volume(self._test_lun(self.host).id, filesystem = self.fs)

        self.assertEqual(ManagedMgs.objects.get(pk = self.mgt.pk).state, 'unformatted')
        self.assertEqual(ManagedMdt.objects.get(pk = self.mdt.pk).state, 'unformatted')
        self.assertEqual(ManagedOst.objects.get(pk = self.ost.pk).state, 'unformatted')

        self.set_state(self.fs, 'available')

        for obj in [self.mgt, self.mdt, self.ost, self.fs]:
            obj = freshen(obj)
            obj.immutable_state = True
            obj.save()

    def test_remove(self):
        from chroma_core.models import ManagedMgs, ManagedFilesystem, ManagedMdt, ManagedOst

        self.set_state(self.mgt, 'removed')
        with self.assertRaises(ManagedMgs.DoesNotExist):
            freshen(self.mgt)
        with self.assertRaises(ManagedFilesystem.DoesNotExist):
            freshen(self.fs)
        with self.assertRaises(ManagedMdt.DoesNotExist):
            freshen(self.mdt)
        with self.assertRaises(ManagedOst.DoesNotExist):
            freshen(self.ost)
