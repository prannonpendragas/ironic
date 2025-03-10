.. _troubleshooting:

======================
Troubleshooting Ironic
======================

Nova returns "No valid host was found" Error
============================================

Sometimes Nova Conductor log file "nova-conductor.log" or a message returned
from Nova API contains the following error::

    NoValidHost: No valid host was found. There are not enough hosts available.

"No valid host was found" means that the Nova Scheduler could not find a bare
metal node suitable for booting the new instance.

This in turn usually means some mismatch between resources that Nova expects
to find and resources that Ironic advertised to Nova.

A few things should be checked in this case:

#. Make sure that enough nodes are in ``available`` state, not in
   maintenance mode and not already used by an existing instance.
   Check with the following command::

       baremetal node list --provision-state available --no-maintenance --unassociated

   If this command does not show enough nodes, use generic ``baremetal
   node list`` to check other nodes. For example, nodes in ``manageable`` state
   should be made available::

       baremetal node provide <IRONIC NODE>

   The Bare metal service automatically puts a node in maintenance mode if
   there are issues with accessing its management interface. See
   :ref:`power-fault` for details.

   The ``node validate`` command can be used to verify that all required fields
   are present. The following command should not return anything::

       baremetal node validate <IRONIC NODE> | grep -E '(power|management)\W*False'

   Maintenance mode will be also set on a node if automated cleaning has
   failed for it previously.

#. Make sure that you have Compute services running and enabled::

       $ openstack compute service list --service nova-compute
       +----+--------------+-------------+------+---------+-------+----------------------------+
       | ID | Binary       | Host        | Zone | Status  | State | Updated At                 |
       +----+--------------+-------------+------+---------+-------+----------------------------+
       |  7 | nova-compute | example.com | nova | enabled | up    | 2017-09-04T13:14:03.000000 |
       +----+--------------+-------------+------+---------+-------+----------------------------+

   By default, a Compute service is disabled after 10 consecutive build
   failures on it. This is to ensure that new build requests are not routed to
   a broken Compute service. If it is the case, make sure to fix the source of
   the failures, then re-enable it::

       openstack compute service set --enable <COMPUTE HOST> nova-compute

#. Starting with the Pike release, check that all your nodes have the
   ``resource_class`` field set using the following command::

      baremetal node list --fields uuid name resource_class

   Then check that the flavor(s) are configured to request these resource
   classes via their properties::

       openstack flavor show <FLAVOR NAME> -f value -c properties

   For example, if your node has resource class ``baremetal-large``, it will
   be matched by a flavor with property ``resources:CUSTOM_BAREMETAL_LARGE``
   set to ``1``. See :doc:`/install/configure-nova-flavors` for more
   details on the correct configuration.

#. Upon scheduling, Nova will query the Placement API service for the
   available resource providers (in the case of Ironic: nodes with a given
   resource class). If placement does not have any allocation candidates for the
   requested resource class, the request will result in a "No valid host
   was found" error. It is hence sensible to check if Placement is aware of
   resource providers (nodes) for the requested resource class with::

       $ openstack allocation candidate list --resource CUSTOM_BAREMETAL_LARGE='1'
       +---+-----------------------------+--------------------------------------+-------------------------------+
       | # | allocation                  | resource provider                    | inventory used/capacity       |
       +---+-----------------------------+--------------------------------------+-------------------------------+
       | 1 | CUSTOM_BAREMETAL_LARGE=1    | 2f7b9c69-c1df-4e40-b94e-5821a4ea0453 | CUSTOM_BAREMETAL_LARGE=0/1    |
       +---+-----------------------------+--------------------------------------+-------------------------------+

   For Ironic, the resource provider is the UUID of the available Ironic node.
   If this command returns an empty list (or does not contain the targeted
   resource provider), the operator needs to understand first, why the resource
   tracker has not reported this provider to placement. Potential explanations
   include:

   * the resource tracker cycle has not finished yet and the resource provider
     will appear once it has (the time to finish the cycle scales linearly with
     the number of nodes the corresponding ``nova-compute`` service manages);

   * the node is in a state where the resource tracker does not consider it to
     be eligible for scheduling, e.g. when the node has ``maintenance`` set to
     ``True``; make sure the target nodes are in ``available`` and
     ``maintenance`` is ``False``;

#. The Nova flavor that you are using does not match any properties of the
   available Ironic nodes. Use
   ::

        openstack flavor show <FLAVOR NAME>

   to compare. The extra specs in your flavor starting with ``capability:``
   should match ones in ``node.properties['capabilities']``.

   .. note::
      The format of capabilities is different in Nova and Ironic.
      E.g. in Nova flavor::

        $ openstack flavor show <FLAVOR NAME> -c properties
        +------------+----------------------------------+
        | Field      | Value                            |
        +------------+----------------------------------+
        | properties | capabilities:boot_mode='uefi'    |
        +------------+----------------------------------+

      But in Ironic node::

        $ baremetal node show <IRONIC NODE> --fields properties
        +------------+-----------------------------------------+
        | Property   | Value                                   |
        +------------+-----------------------------------------+
        | properties | {u'capabilities': u'boot_mode:uefi'}    |
        +------------+-----------------------------------------+

#. After making changes to nodes in Ironic, it takes time for those changes
   to propagate from Ironic to Nova. Check that
   ::

        openstack hypervisor stats show

   correctly shows total amount of resources in your system. You can also
   check ``openstack hypervisor show <IRONIC NODE>`` to see the status of
   individual Ironic nodes as reported to Nova.

#. Figure out which Nova Scheduler filter ruled out your nodes. Check the
   ``nova-scheduler`` logs for lines containing something like::

        Filter ComputeCapabilitiesFilter returned 0 hosts

   The name of the filter that removed the last hosts may give some hints on
   what exactly was not matched. See
   :nova-doc:`Nova filters documentation <filter_scheduler.html>`
   for more details.

#. If none of the above helped, check Ironic conductor log carefully to see
   if there are any conductor-related errors which are the root cause for
   "No valid host was found". If there are any "Error in deploy of node
   <IRONIC-NODE-UUID>: [Errno 28] ..." error messages in Ironic conductor
   log, it means the conductor run into a special error during deployment.
   So you can check the log carefully to fix or work around and then try
   again.

Patching the Deploy Ramdisk
===========================

When debugging a problem with deployment and/or inspection you may want to
quickly apply a change to the ramdisk to see if it helps. Of course you can
inject your code and/or SSH keys during the ramdisk build (depends on how
exactly you've built your ramdisk). But it's also possible to quickly modify
an already built ramdisk.

Create an empty directory and unpack the ramdisk content there:

.. code-block:: bash

    $ mkdir unpack
    $ cd unpack
    $ gzip -dc /path/to/the/ramdisk | cpio -id

The last command will result in the whole Linux file system tree unpacked in
the current directory. Now you can modify any files you want. The actual
location of the files will depend on the way you've built the ramdisk.

.. note::
    On a systemd-based system you can use the ``systemd-nspawn`` tool (from
    the ``systemd-container`` package) to create a lightweight container from
    the unpacked filesystem tree::

        $ sudo systemd-nspawn --directory /path/to/unpacked/ramdisk/ /bin/bash

    This will allow you to run commands within the filesystem, e.g. use package
    manager. If the ramdisk is also systemd-based, and you have login
    credentials set up, you can even boot a real ramdisk environment with

    ::

        $ sudo systemd-nspawn --directory /path/to/unpacked/ramdisk/ --boot

After you've done the modifications, pack the whole content of the current
directory back::

    $ find . | cpio -H newc -o | gzip -c > /path/to/the/new/ramdisk

.. note:: You don't need to modify the kernel (e.g.
          ``tinyipa-master.vmlinuz``), only the ramdisk part.

API Errors
==========

The ``debug_tracebacks_in_api`` config option may be set to return tracebacks
in the API response for all 4xx and 5xx errors.

.. _retrieve_deploy_ramdisk_logs:

Retrieving logs from the deploy ramdisk
=======================================

When troubleshooting deployments (specially in case of a deploy failure)
it's important to have access to the deploy ramdisk logs to be able to
identify the source of the problem. By default, Ironic will retrieve the
logs from the deploy ramdisk when the deployment fails and save it on the
local filesystem at ``/var/log/ironic/deploy``.

To change this behavior, operators can make the following changes to
``/etc/ironic/ironic.conf`` under the ``[agent]`` group:

* ``deploy_logs_collect``:  Whether Ironic should collect the deployment
  logs on deployment. Valid values for this option are:

  * ``on_failure`` (**default**): Retrieve the deployment logs upon a
    deployment failure.

  * ``always``: Always retrieve the deployment logs, even if the
    deployment succeed.

  * ``never``: Disable retrieving the deployment logs.

* ``deploy_logs_storage_backend``: The name of the storage backend where
  the logs will be stored. Valid values for this option are:

  * ``local`` (**default**): Store the logs in the local filesystem.

  * ``swift``: Store the logs in Swift.

* ``deploy_logs_local_path``: The path to the directory where the
  logs should be stored, used when the ``deploy_logs_storage_backend``
  is configured to ``local``. By default logs will be stored at
  **/var/log/ironic/deploy**.

* ``deploy_logs_swift_container``: The name of the Swift container to
  store the logs, used when the deploy_logs_storage_backend is configured to
  "swift". By default **ironic_deploy_logs_container**.

* ``deploy_logs_swift_days_to_expire``: Number of days before a log object
  is marked as expired in Swift. If None, the logs will be kept forever
  or until manually deleted. Used when the deploy_logs_storage_backend is
  configured to "swift". By default **30** days.

When the logs are collected, Ironic will store a *tar.gz* file containing
all the logs according to the ``deploy_logs_storage_backend``
configuration option. All log objects will be named with the following
pattern::

  <node>[_<instance-uuid>]_<timestamp yyyy-mm-dd-hh:mm:ss>.tar.gz

.. note::
   The *instance_uuid* field is not required for deploying a node when
   Ironic is configured to be used in standalone mode. If present it
   will be appended to the name.


Accessing the log data
----------------------

When storing in the local filesystem
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When storing the logs in the local filesystem, the log files can
be found at the path configured in the ``deploy_logs_local_path``
configuration option. For example, to find the logs from the node
``5e9258c4-cfda-40b6-86e2-e192f523d668``:

.. code-block:: bash

   $ ls /var/log/ironic/deploy | grep 5e9258c4-cfda-40b6-86e2-e192f523d668
   5e9258c4-cfda-40b6-86e2-e192f523d668_88595d8a-6725-4471-8cd5-c0f3106b6898_2016-08-08-13:52:12.tar.gz
   5e9258c4-cfda-40b6-86e2-e192f523d668_db87f2c5-7a9a-48c2-9a76-604287257c1b_2016-08-08-14:07:25.tar.gz

.. note::
   When saving the logs to the filesystem, operators may want to enable
   some form of rotation for the logs to avoid disk space problems.


When storing in Swift
~~~~~~~~~~~~~~~~~~~~~

When using Swift, operators can associate the objects in the
container with the nodes in Ironic and search for the logs for the node
``5e9258c4-cfda-40b6-86e2-e192f523d668`` using the **prefix** parameter.
For example:

.. code-block:: bash

  $ swift list ironic_deploy_logs_container -p 5e9258c4-cfda-40b6-86e2-e192f523d668
  5e9258c4-cfda-40b6-86e2-e192f523d668_88595d8a-6725-4471-8cd5-c0f3106b6898_2016-08-08-13:52:12.tar.gz
  5e9258c4-cfda-40b6-86e2-e192f523d668_db87f2c5-7a9a-48c2-9a76-604287257c1b_2016-08-08-14:07:25.tar.gz

To download a specific log from Swift, do:

.. code-block:: bash

   $ swift download ironic_deploy_logs_container "5e9258c4-cfda-40b6-86e2-e192f523d668_db87f2c5-7a9a-48c2-9a76-604287257c1b_2016-08-08-14:07:25.tar.gz"
   5e9258c4-cfda-40b6-86e2-e192f523d668_db87f2c5-7a9a-48c2-9a76-604287257c1b_2016-08-08-14:07:25.tar.gz [auth 0.341s, headers 0.391s, total 0.391s, 0.531 MB/s]

The contents of the log file
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The log is just a ``.tar.gz`` file that can be extracted as:

.. code-block:: bash

   $ tar xvf <file path>


The contents of the file may differ slightly depending on the distribution
that the deploy ramdisk is using:

* For distributions using ``systemd`` there will be a file called
  **journal** which contains all the system logs collected via the
  ``journalctl`` command.

* For other distributions, the ramdisk will collect all the contents of
  the ``/var/log`` directory.

For all distributions, the log file will also contain the output of
the following commands (if present): ``ps``, ``df``, ``ip addr`` and
``iptables``.

Here's one example when extracting the content of a log file for a
distribution that uses ``systemd``:

.. code-block:: bash

   $ tar xvf 5e9258c4-cfda-40b6-86e2-e192f523d668_88595d8a-6725-4471-8cd5-c0f3106b6898_2016-08-08-13:52:12.tar.gz
   df
   ps
   journal
   ip_addr
   iptables

.. _troubleshooting-stp:

DHCP during PXE or iPXE is inconsistent or unreliable
=====================================================

This can be caused by the spanning tree protocol delay on some switches. The
delay prevents the switch port moving to forwarding mode during the nodes
attempts to PXE, so the packets never make it to the DHCP server. To resolve
this issue you should set the switch port that connects to your baremetal nodes
as an edge or PortFast type port. Configured in this way the switch port will
move to forwarding mode as soon as the link is established. An example on how to
do that for a Cisco Nexus switch is:

.. code-block:: bash

    $ config terminal
    $ (config) interface eth1/11
    $ (config-if) spanning-tree port type edge

Why does X issue occur when I am using LACP bonding with iPXE?
==============================================================

If you are using iPXE, an unfortunate aspect of its design and interaction
with networking is an automatic response as a Link Aggregation Control
Protocol (or LACP) peer to remote switches. iPXE does this for only the
single port which is used for network booting.

In theory, this may help establish the port link-state faster with some
switch vendors, but the official reasoning as far as the Ironic Developers
are aware is not documented for iPXE. The end result of this is that once
iPXE has stopped responding to LACP messages from the peer port, which
occurs as part of the process of booting a ramdisk and iPXE handing
over control to a full operating-system, switches typically begin a
timer to determine how to handle the failure. This is because,
depending on the mode of LACP, this can be interpreted as a switch or
network fabric failure.

This may demonstrate as any number of behaviors or issues from ramdisks
finding they are unable to acquire DHCP addresses over the network interface
to downloads abruptly stalling, to even minor issues such as LLDP port data
being unavailable in introspection.

Overall:

* Ironic's agent doesn't officially support LACP and the Ironic community
  generally believes this may cause more problems than it would solve.
  During the Victoria development cycle, we added retry logic for most
  actions in an attempt to navigate the worst-known default hold-down
  timers to help ensure a deployment does not fail due to a short-lived
  transitory network connectivity failure in the form of a switch port having
  moved to a temporary blocking state. Where applicable and possible,
  many of these patches have been backported to supported releases.
  These patches also require that the switchport has an eventual fallback to a
  non-bonded mode. If the port remains in a blocking state, then traffic will
  be unable to flow and the deployment is likely to time out.
* If you must use LACP, consider ``passive`` LACP negotiation settings
  in the network switch as opposed to ``active``. The difference being with
  passive the connected workload is likely a server where it should likely
  request the switch to establish the Link Aggregate. This is instead of
  being treated as if it's possibly another switch.
* Consult your switch vendor's support forums. Some vendors have recommended
  port settings for booting machines using iPXE with their switches.

IPMI errors
===========

When working with IPMI, several settings need to be enabled depending on vendors.

Enable IPMI over LAN
--------------------

Machines may not have IPMI access over LAN enabled by default. This could cause
the IPMI port to be unreachable through ipmitool, as shown:

.. code-block:: bash

    $ ipmitool -I lan -H ipmi_host -U ipmi_user -P ipmi_pass chassis power status
    Error: Unable to establish LAN session

To fix this, enable ``IPMI over lan`` setting using your BMC tool or web app.

Troubleshooting lanplus interface
---------------------------------

When working with lanplus interfaces, you may encounter the following error:

.. code-block:: bash

    $ ipmitool -I lanplus -H ipmi_host -U ipmi_user -P ipmi_pass power status
    Error in open session response message : insufficient resources for session
    Error: Unable to establish IPMI v2 / RMCP+ session

To fix that issue, please enable ``RMCP+ Cipher Suite3 Configuration`` setting
using your BMC tool or web app.

Why are my nodes stuck in a "-ing" state?
=========================================

The Ironic conductor uses states ending with ``ing`` as a signifier that
the conductor is actively working on something related to the node.

Often, this means there is an internal lock or ``reservation`` set on the node
and the conductor is downloading, uploading, or attempting to perform some
sort of Input/Output operation - see `Why does API return "Node is locked by
host"?`_ for details.

In the case the conductor gets stuck, these operations should timeout,
but there are cases in operating systems where operations are blocked until
completion. These sorts of operations can vary based on the specific
environment and operating configuration.

What can cause these sorts of failures?
---------------------------------------

Typical causes of such failures are going to be largely rooted in the concept
of ``iowait``, either in the form of downloading from a remote host or
reading or writing to the disk of the conductor. An operator can use the
`iostat <https://man7.org/linux/man-pages/man1/iostat.1.html>`_ tool to
identify the percentage of CPU time spent waiting on storage devices.

The fields that will be particularly important are the ``iowait``, ``await``,
and ``tps`` ones, which can be read about in the ``iostat`` manual page.

In the case of network file systems, for backing components such as image
caches or distributed ``tftpboot`` or ``httpboot`` folders, IO operations
failing on these can, depending on operating system and underlying client
settings, cause threads to be stuck in a blocking wait state, which is
realistically undetectable short the operating system logging connectivity
errors or even lock manager access errors.

For example with
`nfs <https://www.man7.org/linux/man-pages/man5/nfs.5.html>`_,
the underlying client recovery behavior, in terms of ``soft``, ``hard``,
``softreval``, ``nosoftreval``, will largely impact this behavior, but also
NFS server settings can impact this behavior. A solid sign that this is a
failure, is when an ``ls /path/to/nfs`` command hangs for a period of time.
In such cases, the Storage Administrator should be consulted and network
connectivity investigated for errors before trying to recover to
proceed.

The bad news for IO related failures
------------------------------------

If the node has a populated ``reservation`` field, and has not timed out or
proceeded to a ``fail`` state, then the conductor process will likely need to
be restarted. This is because the worker thread is hung with-in the conductor.

Manual intervention with-in Ironic's database is *not* advised to try and
"un-wedge" the machine in this state, and restarting the conductor is
encouraged.

.. note::
   Ironic's conductor, upon restart, clears reservations for nodes which
   were previously managed by the conductor before restart.

If a distributed or network file system is in use, it is highly recommended
that the operating system of the node running the conductor be rebooted as
the running conductor may not even be able to exit in the state of an IO
failure, again dependent upon site and server configuration.

File Size != Disk Size
----------------------

An easy to make misconception is that a 2.4 GB file means that only 2.4 GB
is written to disk. But if that file's virtual size is 20 GB, or 100 GB
things can become very problematic and extend the amount of time the node
spends in ``deploying`` and ``deploy wait`` states.

Again, these sorts of cases will depend upon the exact configuration of the
deployment, but hopefully these are areas where these actions can occur.

* Conversion to raw image files upon download to the conductor, from the
  :oslo.config:option:`DEFAULT.force_raw_images` option. Users using Glance may also experience
  issues here as the conductor will cache the image to be written which takes
  place when the :oslo.config:option:`agent.image_download_source` is set to ``http`` instead of
  ``swift``.

.. note::
   The QCOW2 image conversion utility does consume quite a bit of memory
   when converting images or writing them to the end storage device. This
   is because the files are not sequential in nature, and must be re-assembled
   from an internal block mapping. Internally Ironic limits this to 1GB
   of RAM. Operators performing large numbers of deployments may wish to
   disable raw images in these sorts of cases in order to minimize the
   conductor becoming a limiting factor due to memory and network IO.

Why are my nodes stuck in a "wait" state?
=========================================

The Ironic conductor uses states containing ``wait`` as a signifier that
the conductor is waiting for a callback from another component, such as
the Ironic Python Agent or the Inspector. If this feedback does not arrive,
the conductor will time out and the node will eventually move to a ``failed``
state. Depending on the configuration and the circumstances, however, a node
can stay in a ``wait`` state for a long time or even never time out. The list
of such wait states includes:

* ``clean wait`` for cleaning,
* ``inspect wait`` for introspection,
* ``rescue wait`` for rescuing, and
* ``wait call-back`` for deploying.

Communication issues between the conductor and the node
-------------------------------------------------------

One of the most common issues when nodes seem to be stuck in a wait state
occur when the node never received any instructions or does not react as
expected: the conductor moved the node to a wait state but the node will
never call back. Examples include wrong ciphers which will make ipmitool
get stuck or BMCs in a state where they accept commands, but don't do the
requested task (or only a part of it, like shutting off, but not starting).
It is useful in these cases to see via a ping or the console if and which
action the node is performing. If the node does not seem to react to the
requests sent be the conductor, it may be worthwhile to try the corresponding
action out-of-band, e.g. confirm that power on/off commands work when directly
sent to the BMC. The section on `IPMI errors`_. above gives some additional
points to check. In some situations, a BMC reset may be necessary.

Ironic Python Agent stuck
-------------------------

Nodes can also get remain in a wait state when the component the conductor is
waiting for gets stuck, e.g. when a hardware manager enters a loop or is
waiting for an event that is never happening. In these cases, it might be
helpful to connect to the IPA and inspect its logs, see the trouble shooting
guide of the :ironic-python-agent-doc:`ironic-python-agent (IPA) <>` on how
to do this.

Stopping the operation
----------------------

Cleaning, inspection and rescuing can be stopped while in ``clean wait``,
``inspect wait`` and ``rescue wait`` states using the ``abort`` command.
It will move the node to the corresponding failure state (``clean failed``,
``inspect failed`` or ``rescue failed``)::

    baremetal node abort <node>

Deploying can be aborted while in the ``wait call-back`` state  by starting an
undeploy (normally resulting in cleaning)::

    baremetal node undeploy <node>

See :doc:`/user/states` for more details.

.. note::
   Since the Bare Metal service is not doing anything actively in waiting
   states, the nodes are not moved to failed states on conductor restart.

Deployments fail with "failed to update MAC address"
====================================================

The design of the integration with the Networking service (neutron) is such
that once virtual ports have been created in the API, their MAC address must
be updated in order for the DHCP server to be able to appropriately reply.

This can sometimes result in errors being raised indicating that the MAC
address is already in use. This is because at some point in the past, a
virtual interface was orphaned either by accident or by some unexpected
glitch, and a previous entry is still present in Neutron.

This error looks something like this when reported in the ironic-conductor
log output.:

  Failed to update MAC address on Neutron port 305beda7-0dd0-4fec-b4d2-78b7aa4e8e6a.: MacAddressInUseClient: Unable to complete operation for network 1e252627-6223-4076-a2b9-6f56493c9bac. The mac address 52:54:00:7c:c4:56 is in use.

Because we have no idea about this entry, we fail the deployment process
as we can't make a number of assumptions in order to attempt to automatically
resolve the conflict.

How did I get here?
-------------------

Originally this was a fairly easy issue to encounter. The retry logic path
which resulted between the Orchestration (heat) and Compute (nova) services,
could sometimes result in additional un-necessary ports being created.

Bugs of this class have been largely resolved since the Rocky development
cycle. Since then, the way this can become encountered is due to Networking
(neutron) VIF attachments not being removed or deleted prior to deleting a
port in the Bare Metal service.

Ultimately, the key of this is that the port is being deleted. Under most
operating circumstances, there really is no need to delete the port, and
VIF attachments are stored on the port object, so deleting the port
*CAN* result in the VIF not being cleaned up from Neutron.

Under normal circumstances, when deleting ports, a node should be in a
stable state, and the node should not be provisioned. If the
``baremetal port delete`` command fails, this may indicate that
a known VIF is still attached. Generally if they are transitory from cleaning,
provisioning, rescuing, or even inspection, getting the node to the
``available`` state will unblock your delete operation, that is unless there is
a tenant VIF attahment. In that case, the vif will need to be removed from
with-in the Bare Metal service using the
``baremetal node vif detach`` command.

A port can also be checked to see if there is a VIF attachment by consulting
the port's ``internal_info`` field.

.. warning::
   The ``maintenance`` flag can be used to force the node's port to be
   deleted, however this will disable any check that would normally block
   the user from issuing a delete and accidentally orphaning the VIF attachment
   record.

How do I resolve this?
----------------------

Generally, you need to identify the port with the offending MAC address.
Example:

.. code-block:: console

  $ openstack port list --mac-address 52:54:00:7c:c4:56

From the command's output, you should be able to identify the ``id`` field.
Using that, you can delete the port. Example:

.. code-block:: console

  $ openstack port delete <id>

.. warning::
   Before deleting a port, you should always verify that it is no longer in
   use or no longer seems applicable/operable. If multiple deployments of
   the Bare Metal service with a single Neutron, the possibility that a
   inventory typo, or possibly even a duplicate MAC address exists, which
   could also produce the same basic error message.

My test VM image does not deploy -- mount point does not exist
==============================================================

What is likely occurring
------------------------

The image attempting to be deployed likely is a partition image where
the file system that the user wishes to boot from lacks the required
folders, such as ``/dev`` and ``/proc``, which are required to install
a bootloader for a Linux OS image

It should be noted that similar errors can also occur with whole disk
images where we are attempting to setup the UEFI bootloader configuration.
That being said, in this case, the image is likely invalid or contains
an unexpected internal structure.

Users performing testing may choose something that they believe
will work based on it working for virtual machines. These images are often
attractive for testing as they are generic and include basic support
for establishing networking and possibly installing user keys.
Unfortunately, these images often lack drivers and firmware required for
many different types of physical hardware which makes using them
very problematic. Additionally, images such as `Cirros <https://download.cirros-cloud.net>`_
do not have any contents in the root filesystem (i.e. an empty filesystem),
as they are designed for the ``ramdisk`` to write the contents to disk upon
boot.

How do I not encounter this issue?
----------------------------------

We generally recommend using `diskimage-builder <https://docs.openstack.org/diskimage-builder>`_
or vendor supplied images. Centos, Ubuntu, Fedora, and Debian all publish
operating system images which do generally include drivers and firmware for
physical hardware. Many of these published "cloud" images, also support
auto-configuration of networking AND population of user keys.

Issues with autoconfigured TLS
==============================

These issues will manifest as an error in ``ironic-conductor`` logs looking
similar to (lines are wrapped for readability)::

    ERROR ironic.drivers.modules.agent_client [-]
    Failed to connect to the agent running on node d7c322f0-0354-4008-92b4-f49fb2201001
    for invoking command clean.get_clean_steps. Error:
    HTTPSConnectionPool(host='192.168.123.126', port=9999): Max retries exceeded with url:
    /v1/commands/?wait=true&agent_token=<token> (Caused by
    SSLError(SSLError(1, '[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed (_ssl.c:897)'),)):
    requests.exceptions.SSLError: HTTPSConnectionPool(host='192.168.123.126', port=9999):
    Max retries exceeded with url: /v1/commands/?wait=true&agent_token=<token>
    (Caused by SSLError(SSLError(1, '[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed (_ssl.c:897)'),))

The cause of the issue is that the Bare Metal service cannot access the ramdisk
with the TLS certificate provided by the ramdisk on first heartbeat. You can
inspect the stored certificate in ``/var/lib/ironic/certificates/<node>.crt``.

You can try connecting to the ramdisk using the IP address in the log message::

    curl -vL https://<IP address>:9999/v1/commands \
        --cacert /var/lib/ironic/certificates/<node UUID>.crt

You can get the detailed information about the certificate using openSSL::

    openssl x509 -text -noout -in /var/lib/ironic/certificates/<node UUID>.crt

Clock skew
----------

One possible source of the problem is a discrepancy between the hardware
clock on the node and the time on the machine with the Bare Metal service.
It can be detected by comparing the ``Not Before`` field in the ``openssl``
output with the timestamp of a log message.

The recommended solution is to enable the NTP support in ironic-python-agent by
passing the ``ipa-ntp-server`` argument with an address of an NTP server
reachable by the node.

If it is not possible, you need to ensure the correct hardware time on the
machine. Keep in mind a potential issue with timezones: an ability to store
timezone in hardware is pretty recent and may not be available. Since
ironic-python-agent is likely operating in UTC, the hardware clock should also
be set in UTC.

.. note::
   Microsoft Windows uses local time by default, so a machine that has
   previously run Windows will likely have wrong time.

I've checked the clock skew, tried syncing with NTP, and certificate reports not valid yet
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you have encountered a case where you have tried to sync the clock of
a system and deployment/cleaning operations are failing stating the
certificate is not valid yet or has expired, there could be a few different
things going on.

But first, we need to delineate an aspect. There is more than one clock in
most systems.

Specifically, a Baseboard Management Controller has its own clock, which may
or may not be syncing with the "Host" clock of the system. It is important to
ensure that the Host clock in bios firmware settings is what is checked.
The best way to do this is to, on the console, boot into firmware settings,
and check the "Date / Time Settings".

In most cases, simple clock skew can be addressed through use of the
``ipa-ntp-server`` setting, however the Ironic community has become aware
of reports where even that does not remedy this issue. Investigation has found
some hardware also allowing a timezone setting to be introduced with a UTC
offset or localized time zone. It appears that when the ramdisk boots, the
ramdisk clock does not properly calculate UTC as a result, and believes the
time to be skewed based upon the timezone setting applied in firmware
settings. The Ironic community recommends that the only timezone used
set in a system clock is UTC, as Linux generally expects the system clock
to be in UTC.

Another option is the ``auto_tls_allowed_clock_skew`` setting in the
ironic-python-agent configuration file. It defaults to 1 hour. If you
find you need to modify this setting in your deployment, please notify
Ironic community.

I changed ironic.conf, and now I can't edit my nodes.
=====================================================

Whenever a node is created in ironic, default interfaces are identified
as part of driver composition. This maybe sourced from explicit default
values which have been set in ``ironic.conf`` or by the interface order
for the enabled interfaces list. The result of this is that the
``ironic-conductor`` cannot spawn a ``task`` using the composed driver,
as a portion of the driver is no longer enabled. This makes it difficult
to edit or update the node if the settings have been changed.

For example, with networking interfaces, if you have
``default_network_interface=neutron`` or
``enabled_network_interfaces=neutron,flat``
in your ``ironic.conf``, nodes would have been created with the ``neutron``
network interface.

This is because ``default_network_interface`` overrides the setting
for new nodes, and that setting is **saved** to the database nodes table.

Similarly, the order of ``enabled_network_interfaces`` takes priority, and
the first entry in the list is generally set to the default for the node upon
creation, and that record is **saved** to the database nodes table.

The only case where driver composition does *not* calculate a default is if
an explicit value is provided upon the creation of the node.

Example failure
---------------

A node in this state, when the ``network_interface`` was saved as ``neutron``,
yet the ``neutron`` interface is no longer enabled will fail basic state
transition requests:

.. code-block:: console

  $ baremetal node manage 7164efca-37ab-1213-1112-b731cf795a5a
  Could not find the following interface in the 'ironic.hardware.interfaces.network' entrypoint: neutron. Valid interfaces are ['flat']. (HTTP 400)

How to fix this?
----------------

Revert the changes you made to ``ironic.conf``.

This applies to any changes to any ``default_*_interface`` options or the
order of interfaces in the for the ``enabled_*_interfaces`` options.

Once the conductor has been restarted with the updated configuration, you
should now be able to update the interface using the ``baremetal node set``
command. In this example we use the ``network_interface`` as this is most
commonly where it is encountered:

.. code-block:: console

  $ baremetal node set $NAME_OR_UUID --network-interface flat

.. note:: There are additional paths one can take to remedy this sort of
   issue, however we encourage operators to be mindful of operational
   consistency when making major configuration changes.

Once you have updated the saved interfaces, you should be able to safely
return the ``ironic.conf`` configuration change in changing what interfaces
are enabled by the conductor.

I'm getting Out of Memory errors
================================

This issue, also known as the "the OOMKiller got my conductor" case,
is where your OS system memory reaches a point where the operating
system engages measures to shed active memory consumption in order
to prevent a complete failure of the machine. Unfortunately this
can cause unpredictable behavior.

How did I get here?
-------------------

One of the major consumers of memory in a host running an ironic-conductor is
transformation of disk images using the ``qemu-img`` tool. This tool, because
the disk images it works with are both compressed and out of linear block
order, requires a considerable amount of memory to efficiently re-assemble
and write-out a disk to a device, or to simply convert the format such as
to a ``raw`` image.

By default, ironic's configuration limits this conversion to 1 GB of RAM
for the process, but each conversion does cause additional buffer memory
to be used, which increases overall system memory pressure. Generally
memory pressure alone from buffers will not cause an out of memory condition,
but the multiple conversions or deployments running at the same time
CAN cause extreme memory pressure and risk the system running out of memory.

How do I resolve this?
----------------------

This can be addressed a few different ways:

* Use raw images, however these images can be substantially larger
  and require more data to be transmitted "over the wire".
* Add more physical memory.
* Add swap space.
* Reduce concurrency, possibly via another conductor or changing the
  nova-compute.conf ``max_concurrent_builds`` parameter.
* Or finally, adjust the :oslo.config:option:`DEFAULT.minimum_required_memory` parameter
  in your ironic.conf file. The default should be considered a "default
  of last resort" and you may need to reserve additional memory. You may
  also wish to adjust the :oslo.config:option:`DEFAULT.minimum_memory_wait_retries` and
  :oslo.config:option:`DEFAULT.minimum_memory_wait_time` parameters.

Why does API return "Node is locked by host"?
=============================================

This error usually manifests as HTTP error 409 on the client side:

    Node d7e2aed8-50a9-4427-baaa-f8f595e2ceb3 is locked by host 192.168.122.1,
    please retry after the current operation is completed.

It happens, because an operation that modifies a node is requested, while
another such operation is running. The conflicting operation may be user
requested (e.g. a provisioning action) or related to the internal processes
(e.g. changing power state during :doc:`power-sync`). The reported host name
corresponds to the conductor instance that holds the lock.

Normally, these errors are transient and safe to retry after a few seconds. If
the lock is held for significant time, these are the steps you can take.

First of all, check the current ``provision_state`` of the node:

``verifying``
    means that the conductor is trying to access the node's BMC.
    If it happens for minutes, it means that the BMC is either unreachable or
    misbehaving. Double-check the information in ``driver_info``, especially
    the BMC address and credentials.

    If the access details seem correct, try resetting the BMC using, for
    example, its web UI.

``deploying``/``inspecting``/``cleaning``
    means that the conductor is doing some active work. It may include
    downloading or converting images, executing synchronous out-of-band deploy
    or clean steps, etc. A node can stay in this state for minutes, depending
    on various factors. Consult the conductor logs.

``available``/``manageable``/``wait call-back``/``clean wait``
    means that some background process is holding the lock. Most commonly it's
    the power synchronization loop. Similarly to the ``verifying`` state,
    it may mean that the BMC access is broken or too slow. The conductor logs
    will provide you insights on what is happening.

To trace the process using conductor logs:

#. Isolate the relevant log parts. Lock messages come from the
   ``ironic.conductor.task_manager`` module. You can also check the
   ``ironic.common.states`` module for any state transitions:

   .. code-block:: console

    $ grep -E '(ironic.conductor.task_manager|ironic.common.states|NodeLocked)' \
        conductor.log > state.log

#. Find the first instance of ``NodeLocked``. It may look like this (stripping
   timestamps and request IDs here and below for readability)::

    DEBUG ironic.conductor.task_manager [-] Attempting to get exclusive lock on node d7e2aed8-50a9-4427-baaa-f8f595e2ceb3 (for node update) __init__ /usr/lib/python3.6/site-packages/ironic/conductor/task_manager.py:233
    DEBUG ironic_lib.json_rpc.server [-] RPC error NodeLocked: Node d7e2aed8-50a9-4427-baaa-f8f595e2ceb3 is locked by host 192.168.57.53, please retry after the current operation is completed. _handle_error /usr/lib/python3.6/site-packages/ironic_lib/json_rpc/server.py:179

   The events right before this failure will provide you a clue on why the lock
   is held.

#. Find the last successful **exclusive** locking event before the failure, for
   example::

    DEBUG ironic.conductor.task_manager [-] Attempting to get exclusive lock on node d7e2aed8-50a9-4427-baaa-f8f595e2ceb3 (for provision action manage) __init__ /usr/lib/python3.6/site-packages/ironic/conductor/task_manager.py:233
    DEBUG ironic.conductor.task_manager [-] Node d7e2aed8-50a9-4427-baaa-f8f595e2ceb3 successfully reserved for provision action manage (took 0.01 seconds) reserve_node /usr/lib/python3.6/site-packages/ironic/conductor/task_manager.py:350
    DEBUG ironic.common.states [-] Exiting old state 'enroll' in response to event 'manage' on_exit /usr/lib/python3.6/site-packages/ironic/common/states.py:307
    DEBUG ironic.common.states [-] Entering new state 'verifying' in response to event 'manage' on_enter /usr/lib/python3.6/site-packages/ironic/common/states.py:313

   This is your root cause, the lock is held because of the BMC credentials
   verification.

#. Find when the lock is released (if at all). The messages look like this::

    DEBUG ironic.conductor.task_manager [-] Successfully released exclusive lock for provision action manage on node d7e2aed8-50a9-4427-baaa-f8f595e2ceb3 (lock was held 60.02 sec) release_resources /usr/lib/python3.6/site-packages/ironic/conductor/task_manager.py:447

   The message tells you the reason the lock was held (``for provision action
   manage``) and the amount of time it was held (60.02 seconds, which is way
   too much for accessing a BMC).

Unfortunately, due to the way the conductor is designed, it is not possible to
gracefully break a stuck lock held in ``*-ing`` states. As the last resort, you
may need to restart the affected conductor. See `Why are my nodes stuck in a
"-ing" state?`_.

What is ConcurrentActionLimit?
==============================

ConcurrentActionLimit is an exception which is raised to clients when an
operation is requested, but cannot be serviced at that moment because the
overall threshold of nodes in concurrent "Deployment" or "Cleaning"
operations has been reached.

These limits exist for two distinct reasons.

The first is they allow an operator to tune a deployment such that too many
concurrent deployments cannot be triggered at any given time, as a single
conductor has an internal limit to the number of overall concurrent tasks,
this restricts only the number of running concurrent actions. As such, this
accounts for the number of nodes in ``deploy`` and ``deploy wait`` states.
In the case of deployments, the default value is relatively high and should
be suitable for *most* larger operators.

The second is to help slow down the ability in which an entire population of
baremetal nodes can be moved into and through cleaning, in order to help
guard against authenticated malicious users, or accidental script driven
operations. In this case, the total number of nodes in ``deleting``,
``cleaning``, and ``clean wait`` are evaluated. The default maximum limit
for cleaning operations is *50* and should be suitable for the majority of
baremetal operators.

These settings can be modified by using the
:oslo.config:option:`conductor.max_concurrent_deploy` and :oslo.config:option:`conductor.max_concurrent_clean`
settings from the ironic.conf file supporting the ``ironic-conductor``
service. Neither setting can be explicitly disabled, however there is also no
upper limit to the setting.

.. note::
   This was an infrastructure operator requested feature from actual lessons
   learned in the operation of Ironic in large scale production. The defaults
   may not be suitable for the largest scale operators.

Why do I have an error that an NVMe Partition is not a block device?
====================================================================

In some cases, you can encounter an error that suggests a partition that has
been created on an NVMe block device, is not a block device.

Example:

  lsblk: /dev/nvme0n1p2: not a block device

What has happened is the partition contains a partition table inside of it
which is confusing the NVMe device interaction. While basically valid in
some cases to have nested partition tables, for example, with software
raid, in the NVMe case the driver and possibly the underlying device gets
quite confused. This is in part because partitions in NVMe devices are higher
level abstracts.

The way this occurs is you likely had a ``whole-disk`` image, and it was
configured as a partition image. If using glance, your image properties
may have a ``img_type`` field, which should be ``whole-disk``, or you
have a ``kernel_id`` and ``ramdisk_id`` value in the glance image
``properties`` field. Definition of a kernel and ramdisk value also
indicates that the image is of a ``partition`` image type. This is because
a ``whole-disk`` image is bootable from the contents within the image,
and partition images are unable to be booted without a kernel, and ramdisk.

If you are using Ironic in standalone mode, the optional
``instance_info/image_type`` setting may be advisable to be checked.
Very similar to Glance usage above, if you have set Ironic's node level
``instance_info/kernel`` and ``instance_info/ramdisk`` parameters, Ironic
will proceed with deploying an image as if it is a partition image, and
create a partition table on the new block device, and then write the
contents of the image into the newly created partition.

.. NOTE::
   As a general reminder, the Ironic community recommends the use of
   whole disk images over the use of partition images.

Why can't I use Secure Erase/Wipe with RAID controllers?
========================================================

Situations have been reported where an infrastructure operator is expecting
particular device types to be Secure Erased or Wiped when they are behind a
RAID controller.

For example, the server may have NVMe devices attached to a RAID controller
which could be in pass-through or single disk volume mode. The same scenario
exists basically regardless of the disk/storage medium/type.

The basic reason why is that RAID controllers essentially act as command
translators with a buffer cache. They tend to offer a simplified protocol
to the Operating System, and interact with the storage device in whatever
protocol is native to the device. This is the root of the underlying
problem.

Protocols such as SCSI are rooted in quite a bit of computing history,
but never evolved to include primitives like Secure Erase which evolved in
the `ATA protocol <https://en.wikipedia.org/wiki/Parallel_ATA#HDD_passwords_and_security>`_.

The closest primitives in SCSI to ATA Secure Erase is the ``FORMAT UNIT``
and ``UNMAP`` commands.

``FORMAT UNIT`` might be a viable solution, and a tool named
`sg_format <https://linux.die.net/man/8/sg_format>`_ exists,
but there has not been a sufficient call upstream to implement this and
test it sufficiently that the Ironic community would be comfortable
shipping such a capability. The possibility also exists that a RAID
controller might not translate this command through to an end device,
just as some RAID controllers know how to handle and pass through
ATA commands to disk devices which support them. It is entirely dependent
upon the hardware configuration scenario.

The ``UNMAP`` command is similar to the ATA ``TRIM`` command. Unfortunately
the SCSI protocol requires this be performed at block level, and similar to
``FORMAT UNIT``, it may not be supported or just passed through.

If your interested in working on this area, or are willing to help test,
please feel free to contact the
:doc:`Ironic development community </contributor/community>`.
An additional option is the creation of your own
`custom Hardware Manager <https://opendev.org/openstack/ironic-python-agent/src/branch/master/examples/custom-disk-erase>`_
which can contain your preferred logic, however this does require some Python
development experience.

One last item of note, depending on the RAID controller, the BMC, and a number
of other variables, you may be able to leverage the `RAID <raid>`_
configuration interface to delete volumes/disks, and recreate them. This may
have the same effect as a clean disk, however that too is RAID controller
dependent behavior.

I'm in "clean failed" state, what do I do?
==========================================

There is only one way to exit the ``clean failed`` state. But before we visit
the answer as to **how**, we need to stress the importance of attempting to
understand **why** cleaning failed. On the simple side of things, this may be
as simple as a DHCP failure, but on a complex side of things, it could be that
a cleaning action failed against the underlying hardware, possibly due to
a hardware failure.

As such, we encourage everyone to attempt to understand **why** before exiting
the ``clean failed`` state, because you could potentially make things worse
for yourself. For example if firmware updates were being performed, you may
need to perform a rollback operation against the physical server, depending on
what, and how the firmware was being updated. Unfortunately this also borders
the territory of "no simple answer".

This can be counter balanced with sometimes there is a transient networking
failure and a DHCP address was not obtained. An example of this would be
suggested by the ``last_error`` field indicating something about "Timeout
reached while cleaning the node", however we recommend following several
basic troubleshooting steps:

* Consult the ``last_error`` field on the node, utilizing the
  ``baremetal node show <uuid>`` command.
* If the version of ironic supports the feature, consult the node history
  log, ``baremetal node history list`` and
  ``baremetal node history get <uuid>``.
* Consult the actual console screen of the physical machine. *If* the ramdisk
  booted, you will generally want to investigate the controller logs and see
  if an uploaded agent log is being stored on the conductor responsible for
  the baremetal node. Consult `Retrieving logs from the deploy ramdisk`_.
  If the node did not boot for some reason, you can typically just retry
  at this point and move on.

How to get out of the state, once you've understood **why** you reached it
in the first place, is to utilize the ``baremetal node manage <node_id>``
command. This returns the node to ``manageable`` state, from where you can
retry "cleaning" through automated cleaning with the ``provide`` command,
or manual cleaning with ``clean`` command. or the next appropriate action
in the workflow process you are attempting to follow, which may be
ultimately be decommissioning the node because it could have failed and is
being removed or replaced.

I can't seem to introspect newly added nodes in a large cluster
===============================================================

With larger clusters, the act of synchronizing DHCP for introspection and
hardware discovery can take quite a bit of time because of the operational
overhead. What happens is we spend so much time trying to perform
the update that the processes stay continuously busy, which can have a side
effect such as impacting the ability to successfully introspect nodes
which were very recently added to the cluster.

To remedy this, try setting ``[pxe_filter]sync_period`` to be less frequent,
i.e. a larger value to enable conductors to have time between running syncs.

.. note::
   It is anticipated that as part of the 2024.1 release, Ironic will have
   this functionality also merged into Ironic directly as part of the
   merge of the ``ironic-inspector`` service into ``ironic`` itself. This
   merger will result in a slightly more performant implementation, which may
   necessitate re-evaluation and tuning of the ``[pxe_filter]sync_period``
   parameter.

Some or all of my baremetal nodes disappeared! Help?!
=====================================================

If you just upgraded, and this has occurred:

#) Don't Panic
#) Don't try to re-enroll the nodes. They should still be there,
   you just can't see them at the moment.

Over the past few years, Ironic and OpenStack project as a whole has been
working to improve the model of Role Based Access Control. For users of
Ironic, this means an extended role based access control model allowing
delineation of nodes and the ability for projects to both self-manage.

The result is that users inside of a project are only permitted to see
baremetal nodes, through the ``owner`` and ``lessee`` field, which has
been granted access to the project.

However, as with any complex effort, there can be hiccups, and you have
encountered one. Specifically that based upon large scale operator feedback,
Ironic kept logic behind System scoped user usage, which OpenStack largely
avoided due to concerns over effort.

As such, you have a couple different paths you can take, and your ideal
path is also going to vary upon your model of usage and comfort level.
We recommend reading the rest of this answer section before taking any
further action.

A good starting point is obtaining a ``system`` scoped account with an
``admin`` or ``member`` role. Either of those roles will permit a node's
``owner`` or ``lessee`` fields to be changed. Executing
``baremetal node list`` commands with this account should show you all
baremetal nodes across all projects. Alternatively, if you just want to
enable the legacy RBAC policies temporarily to change the fields, that is also
an option, although not encouraged, and can be done utilizing the
``[oslo_policy] enforce_scope`` and ``[oslo_policy] enforce_new_defaults``
settings.

System Scoped Accounts
----------------------

A ``system`` scoped account is one which has access and authority over the
whole of the of an OpenStack deployment. A simplified way to think of
this is when deployed, a username and password is utilized to "bootstrap"
keystone. The rights granted to that user are inherently a system scoped
``admin`` role level of access. You can use this level of access to
check the status, or run additional commands.

In this example below, which if successful, should return a list of all
baremetal nodes known to Ironic, once the executing user supplies the
valid password. In this case the "admin" account keystone was
bootstrapped with. As a minor note, you will not be able to have
any "OS_*" environment variables loaded into your current
command shell, including "OS_CLOUD" for this command to be successful.

.. code-block:: console

    $ openstack --os-username=admin --os-user-domain-name=default --os-system-scope all baremetal node list

You can alternatively issue a `system-scoped token <https://docs.openstack.org/keystone/latest/admin/tokens-overview.html#operation_create_system_token>`_
and reuse further commands with that token, or even generate a new system
scoped account with a role of ``member``.

Changing/Assigning an Owner
---------------------------

Ironic performs matching based upon Project ID. The owner field can be set
to a project's ID value, which allows baremetal nodes to be visible.

.. code-block:: console

    $ PROJECT_ID=$(openstack project show -c id -f value $PROJECT_NAME)
    $ baremetal node set --owner $PROJECT_ID $NODE_UUID_OR_NAME

Why am I only seeing *some* of the nodes?
-----------------------------------------

During the Zed development cycle of Ironic, Ironic added an option which
defaulted to True, which enabled project scoped ``admin`` users to be able
to create their own baremetal nodes without needing higher level access.
This default enabled option, ``[api] project_admin_can_manage_own_nodes``,
automatically stamps the requestor's project ID on to a baremetal node if an
``owner`` is not otherwise specified upon creation. Obviously, this can
create a mixed perception if an operator never paid attention to the ``owner``
field before now.

If your bare metal management processes require that full machine management
is made using a project scoped account, please configure an appropriate
node ``owner`` for the nodes which need to be managed. Ironic recognizes
this is going to vary based upon processes and preferences.

Config Drives in Swift, but rebuilds fails?
===========================================

When deploying instances, Ironic can be configured such that configuration
drives are stored in Swift. The pointer to the configuration drive is saved
in Ironic as a Temporary URL which has a time expiration.

When you issue the rebuild request for a node, Ironic expects that you will
supply new configuration drive contents with your request, however this is
also optional.

Because Swift has been set as the optional configuration drive storage
location, a rebuild can fail if the prior configuration drive file is no
longer accessible and no new configuration drive has been supplied to Ironic.

To resolve this case, you can either supply new configuration drive contents
with your request, or disable configuration from being stored in Swift for
new baremetal node deployments by changing setting
:oslo.config:option:`deploy.configdrive_use_object_store` to ``false``.

Ironic says my Image is Invalid
===============================

As a result of security fixes which were added to Ironic, resulting from the
security posture of the ``qemu-img`` utility, Ironic enforces certain aspects
related to image files.

* Enforces that the file format of a disk image matches what Ironic is
  told by an API user. Any mismatch will result in the image being declared
  as invalid. A mismatch with the file contents and what is stored in the
  Image service will necessitate uploading a new image as that property
  cannot be changed in the image service *after* creation of an image.
* Enforces that the input file format to be written is ``qcow2`` or ``raw``.
  This can be extended by modifying ``[conductor]permitted_image_formats`` in
  ``ironic.conf``.
* Performs safety and sanity check assessment against the file, which can be
  disabled by modifying ``[conductor]disable_deep_image_inspection`` and
  setting it to ``True``. Doing so is not considered safe and should only
  be done by operators accepting the inherent risk that the image they
  are attempting to use may have a bad or malicious structure.
  Image safety checks are generally performed as the deployment process begins
  and stages artifacts, however a late stage check is performed when
  needed by the ironic-python-agent.

Using /dev/sda does not write to the first disk
===============================================

Alternative name: I chose /dev/sda but I found it as /dev/sdb after rebooting.

Historically, Linux users have grown accustom to a context where /dev/sda is
the first device in a physical machine. Meaning, if you look at the device
by_path information or the HCTL, or device LUN, the device ends with a zero.

For example, assuming 3 disks, two controllers, with a single disk on the
second controller would look something like this:

* /dev/sda maps to a device with lun 0, HCTL 0:0:0:0
* /dev/sdb maps to a device with lun 1, HCTL 0:0:1:0
* /dev/sdc maps to a device with lun 2, HCTL 0:1:0:0

However, this was a pattern we grew accustom to because the order of device
discovery was sequential *and* synchronous. In other words the kernel stepped
through all possible devices one at a time. Where this breaks is when the
kernel is operating in a mode where device initialization is asynchronous as
some distributions have decided to adopt.

The result of a move to an asynchronous initialization is /dev/sda has always
been the *first* device to initialize, *not* the first device in the system.
As a result, we can end up with something looking like:

* /dev/sda maps to a device with lun 1, HCTL 0:0:1:0
* /dev/sdb maps to a device with lun 2, HCTL 0:1:0:0
* /dev/sdc maps to a device with lun 0, HCTL 0:0:0:0

Generally, most operators might then consider referencing the
/dev/disk/by-path structure to match disk devices because that seems to imply
a static order, *however* a kernel operating with asynchronous device
initialization will order *everything*, including PCI devices the same way,
meaning by-path can also be unreliable. Furthermore, if your server hardware
is using multipath IO, you should be operating with multipath enabled such
that the device is used.

The net result is the best criteria to match on is:

* Serial Number
* World Wide Name
* Device HCTL, which *does* appear to be static in these cases, but is not
  applicable for hosts using multipathing. It may, ultimately, not be static
  enough, just depending on the hardware in use.

.. NOTE: Some RAID controllers will generate fake WWN and Serial numbers for
   "disks" being supplied by the RAID controller. Some may also use the same
   WWN for *all* devices, which is a valid approach as the device Logical Unit
   Numbers or Device identifier number would be different. Ultimately this
   means labels on disks may not be able to be matched to volumes through a
   RAID controller, and operators will need to simply "know their hardware"
   to navigate the best path depending on the configuration and behavior of
   their hardware.

.. NOTE: Centos Stream-9 appears to have a probe_type="sync" option which
   reverts this behavior. For more information please see
   this `centos stream-9 changeset <https://gitlab.com/redhat/centos-stream/src/kernel/centos-stream-9/-/merge_requests/2819/diffs?commit_id=a93f405246083f0c2e81d0e6c37ba31c6c1b29c3>`_.
