
from hydra_agent.store import *
from hydra_agent import shell
import simplejson as json
import errno
import os
import shlex

LIBDIR = "/var/lib/hydra"

def create_libdir():
    try:
        os.makedirs(LIBDIR)
    except OSError, e:
        if e.errno == errno.EEXIST:
            pass
        else:
            raise e

def cibadmin(command_args):
    from time import sleep

    # try at most, 100 times
    n = 100
    rc = 10

    while rc == 10 and n > 0:
        rc, stdout, stderr = shell.run(shlex.split("cibadmin " + command_args))
        if rc == 0:
            break
        sleep(1)
        n -= 1

    if rc != 0:
        raise RuntimeError("Error (%s) running 'cibadmin %s': '%s' '%s'" % \
                           (rc, command_args, stdout, stderr))

    return rc, stdout, stderr

def format_target(args):
    from hydra_agent.cmds import lustre

    kwargs = json.loads(args.args)
    cmdline = lustre.mkfs(**kwargs)

    shell.try_run(shlex.split(cmdline))

    blkid_output = shell.try_run(["blkid", "-o", "value", "-s", "UUID", kwargs['device']])

    uuid = blkid_output.strip()

    return {'uuid': uuid}

def register_target(args):
    try:
        os.makedirs(args.mountpoint)
    except OSError, e:
        if e.errno == errno.EEXIST:
            pass
        else:
            raise e

    shell.try_run(["mount", "-t", "lustre", args.device, args.mountpoint])
    shell.try_run(["umount", args.mountpoint])
    blkid_output = shell.try_run(["blkid", "-o", "value", "-s", "LABEL", args.device])
    if blkid_output.find("ffff") != -1:
        # Oh hey, we reproduced HYD-268, see if the tunefs output is any different from the blkid output
        import subprocess
        tunefs_text = subprocess.Popen(["tunefs.lustre", "--dryrun", args.device], stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.read()
        name = re.search("Target:\\s+(.*)\n", tunefs_text).group(1)
        # Now let's see if we get a different answer after 5 seconds 
        import time
        time.sleep(5)
        blkid_later = shell.try_run(["blkid", "-o", "value", "-s", "LABEL", args.device])
        raise RuntimeError("HYD-268 (%s, %s, %s)" % (blkid_output.strip(), name, blkid_later.strip()))

    return {'label': blkid_output.strip()}

def unconfigure_ha(args):
    _unconfigure_ha(args.primary, args.label)

def _unconfigure_ha(primary, label):
    if primary:
        rc, stdout, stderr = cibadmin("-D -X '<rsc_location id=\"%s-primary\">'" %  label)
        rc, stdout, stderr = cibadmin("-D -X '<primitive id=\"%s\">'" %  label)
    else:
        rc, stdout, stderr = cibadmin("-D -X '<rsc_location id=\"%s-secondary\">'" %  label)

    store_remove_target_info(label)

def configure_ha(args):
    if args.primary:
        # now configure pacemaker for this target
        from tempfile import mkstemp
        tmp_f, tmp_name = mkstemp()
        os.write(tmp_f, "<primitive class=\"ocf\" provider=\"hydra\" type=\"Target\" id=\"%s\">\
  <meta_attributes id=\"%s-meta_attributes\">\
    <nvpair name=\"target-role\" id=\"%s-meta_attributes-target-role\" value=\"Stopped\"/>\
  </meta_attributes>\
  <operations id=\"%s-operations\">\
    <op id=\"%s-monitor-120\" interval=\"120\" name=\"monitor\" timeout=\"60\"/>\
    <op id=\"%s-start-0\" interval=\"0\" name=\"start\" timeout=\"300\"/>\
    <op id=\"%s-stop-0\" interval=\"0\" name=\"stop\" timeout=\"300\"/>\
  </operations>\
  <instance_attributes id=\"%s-instance_attributes\">\
    <nvpair id=\"%s-instance_attributes-target\" name=\"target\" value=\"%s\"/>\
  </instance_attributes>\
</primitive>" % (args.label, args.label, args.label, args.label, args.label,
            args.label, args.label, args.label, args.label, args.label))
        os.close(tmp_f)

        rc, stdout, stderr = cibadmin("-o resources -C -x %s" % tmp_name)
        score = 20
        preference = "primary"
    else:
        score = 10
        preference = "secondary"

    rc, stdout, stderr = cibadmin("-o constraints -C -X '<rsc_location id=\"%s-%s\" node=\"%s\" rsc=\"%s\" score=\"%s\"/>'" % (args.label,
                                                       preference,
                                                       os.uname()[1],
                                                       args.label, score))

    create_libdir()

    try:
        os.makedirs(args.mountpoint)
    except OSError, e:
        if e.errno == errno.EEXIST:
            pass
        else:
            raise e

    store_write_target_info(args.label, {"bdev": args.device, "mntpt": args.mountpoint})

def mount_target(args):
    info = store_get_target_info(args.label)
    shell.try_run(['mount', '-t', 'lustre', info['bdev'], info['mntpt']])

def unmount_target(args):
    info = store_get_target_info(args.label)
    shell.try_run(["umount", info['bdev']])

def start_target(args):
    shell.try_run(["crm", "resource", "start", args.label])

    # now wait for it
    # FIXME: this may break on non-english systems or new versions of pacemaker
    shell.try_run("while ! crm resource status %s 2>&1 | grep -q \"is running\"; do sleep 1; done" % \
            args.label, shell=True)

def stop_target(args):
    _stop_target(args.label)

def _stop_target(label):
    shell.try_run(["crm", "resource", "stop", label])

    # now wait for it
    # FIXME: this may break on non-english systems or new versions of pacemaker
    shell.try_run("while ! crm resource status %s 2>&1 | grep -q \"is NOT running\"; do sleep 1; done" % \
            label, shell=True)

def migrate_target(args):
    # a migration scores at 500 to force it higher than stickiness
    score = 500
    shell.try_run(shlex.split("crm configure location %s-migrated %s %s: %s" % \
                        (args.label, args.label, score, args.node)))

def unmigrate_target(args):
    # just remove the migration constraint
    shell.try_run("crm configure delete %s-migrated && (sleep 1; crm resource stop %s && crm resource start %s)" % \
                        (args.label, args.label, args.label), shell = True)


