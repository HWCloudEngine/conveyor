# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# Copyright 2012 Red Hat, Inc.
# Copyright 2013 NTT corp.
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

"""Command-line flag library.

Emulates gflags by wrapping cfg.ConfigOpts.

The idea is to move fully to cfg eventually, and this wrapper is a
stepping stone.

"""

from oslo_config import cfg

from conveyor.i18n import _


CONF = cfg.CONF

core_opts = [
    cfg.StrOpt('api_paste_config',
               default="api-paste.ini",
               help='File name for the paste.deploy config for conveyor-api'),
    cfg.StrOpt('state_path',
               default='/var/lib/conveyor',
               deprecated_name='pybasedir',
               help="Top-level directory for maintaining conveyor's state"), ]

debug_opts = [
]

CONF.register_cli_opts(core_opts)
CONF.register_cli_opts(debug_opts)

global_opts = [
    cfg.StrOpt('my_ip',
               default="",
               help='IP address of this host'),
    cfg.StrOpt('glance_host',
               default='$my_ip',
               help='Default glance host name or IP'),
    cfg.IntOpt('glance_port',
               default=9292,
               help='Default glance port'),
    cfg.ListOpt('glance_api_servers',
                default=['$glance_host:$glance_port'],
                help='A list of the glance API servers available to conveyor '
                     '([hostname|ip]:port)'),
    cfg.IntOpt('glance_api_version',
               default=1,
               help='Version of the glance API to use'),
    cfg.IntOpt('glance_num_retries',
               default=0,
               help='Number retries when downloading an image from glance'),
    cfg.BoolOpt('glance_api_insecure',
                default=False,
                help='Allow to perform insecure SSL (https) requests to '
                     'glance'),
    cfg.BoolOpt('glance_api_ssl_compression',
                default=False,
                help='Enables or disables negotiation of SSL layer '
                     'compression. In some cases disabling compression '
                     'can improve data throughput, such as when high '
                     'network bandwidth is available and you use '
                     'compressed image formats like qcow2.'),
    cfg.StrOpt('glance_ca_certificates_file',
               help='Location of ca certificates file to use for glance '
                    'client requests.'),
    cfg.IntOpt('glance_request_timeout',
               default=None,
               help='http/https timeout value for glance operations. If no '
                    'value (None) is supplied here, the glanceclient default '
                    'value is used.'),
    cfg.StrOpt('scheduler_topic',
               default='conveyor-scheduler',
               help='The topic that scheduler nodes listen on'),
    cfg.StrOpt('birdie_topic',
               default='conveyor-clone',
               help='The topic that clone resources listen on'),
    cfg.StrOpt('clone_manager',
               default="conveyor.clone.manager.CloneManager",
               help='Number of workers for OpenStack Volume API service. '
                    'The default is equal to the number of CPUs available.'),
    cfg.StrOpt('resource_manager',
               default="conveyor.resource.manager.ResourceManager",
               help='Number of workers for OpenStack Volume API service. '
                    'The default is equal to the number of CPUs available.'),
    cfg.BoolOpt('enable_v1_api',
                default=True,
                help=_("DEPRECATED: Deploy v1 of the Cinder API.")),
    cfg.BoolOpt('api_rate_limit',
                default=True,
                help='Enables or disables rate limit of the API.'),
    cfg.ListOpt('osapi_birdie_ext_list',
                default=[],
                help='Specify list of extensions to load when using osapi_'
                     'volume_extension option with conveyor.api.contrib.'
                     'select_extensions'),
    cfg.MultiStrOpt('osapi_birdie_extension',
                    default=['conveyor.api.contrib.standard_extensions'],
                    help='osapi conveyor extension to load'),
    # NOTE(vish): default to nova for compatibility with nova installs
    cfg.StrOpt('storage_availability_zone',
               default='nova',
               help='Availability zone of this node'),
    cfg.StrOpt('default_availability_zone',
               default=None,
               help='Default availability zone for new volumes. If not set, '
                    'the storage_availability_zone option value is used as '
                    'the default for new volumes.'),
    cfg.StrOpt('default_volume_type',
               default=None,
               help='Default volume type to use'),
    cfg.StrOpt('volume_usage_audit_period',
               default='month',
               help='Time period for which to generate volume usages. '
                    'The options are hour, day, month, or year.'),
    cfg.StrOpt('rootwrap_config',
               default='/etc/conveyor/rootwrap.conf',
               help='Path to the rootwrap configuration file to use for '
                    'running commands as root'),
    cfg.BoolOpt('monkey_patch',
                default=False,
                help='Enable monkey patching'),
    cfg.ListOpt('monkey_patch_modules',
                default=[],
                help='List of modules/decorators to monkey patch'),
    cfg.IntOpt('service_down_time',
               default=60,
               help='Maximum time since last check-in for a service to be '
                    'considered up'),
    cfg.StrOpt('volume_api_class',
               default='conveyor.volume.cinder.API',
               help='The full class name of the volume API class to use'),
    cfg.StrOpt('backup_api_class',
               default='conveyor.backup.api.API',
               help='The full class name of the volume backup API class'),
    cfg.StrOpt('auth_strategy',
               default='noauth',
               choices=['noauth', 'keystone', 'deprecated'],
               help='The strategy to use for auth. Supports noauth, keystone, '
                    'and deprecated.'),
    cfg.ListOpt('enabled_backends',
                default=None,
                help='A list of backend names to use. These backend names '
                     'should be backed by a unique [CONFIG] group '
                     'with its options'),
    cfg.BoolOpt('no_snapshot_gb_quota',
                default=False,
                help='Whether snapshots count against gigabyte quota'),
    cfg.StrOpt('transfer_api_class',
               default='conveyor.transfer.api.API',
               help='The full class name of the volume transfer API class'),
    cfg.StrOpt('replication_api_class',
               default='conveyor.replication.api.API',
               help='The full class name of the volume replication API class'),
    cfg.StrOpt('consistencygroup_api_class',
               default='conveyor.consistencygroup.api.API',
               help='The full class name of the consistencygroup API class'),
    cfg.StrOpt('os_privileged_user_name',
               default=None,
               help='OpenStack privileged account username. Used for requests '
                    'to other services (such as Nova) that require an account '
                    'with special rights.'),
    cfg.StrOpt('os_privileged_user_password',
               default=None,
               help='Password associated with the OpenStack privileged '
                    'account.',
               secret=True),
    cfg.StrOpt('os_privileged_user_tenant',
               default=None,
               help='Tenant name associated with the OpenStack privileged '
                    'account.'),
    cfg.StrOpt('plan_file_path',
               default='/opt/HUAWEI/image/plans/',
               help='The directory to store the resources files of plans.'),
    cfg.IntOpt('plan_expire_time',
               default=60,
               help='If a plan still was not be cloned or migrated after '
                    'plan_expire_time minutes, the plan will be expired.'),
    cfg.IntOpt('clear_expired_plan_interval',
               default=300,
               help='Interval in seconds for clearing expired plans.'),
    cfg.StrOpt('os_region_name',
               default='cloud.hybrid',
               help='Region name of this node'),
    cfg.StrOpt('config_path',
               default='/etc/conveyor/conveyor.conf',
               help='Region name of this node'),
    cfg.DictOpt('migrate_net_map',
                default={},
                help='map of migrate net id of different az'),
    cfg.StrOpt('vgw_info',
               default="",
               help='ip and id of vgw host for different az'),
    cfg.StrOpt('data_transformer_procotol',
               default="ftp",
               help='protocol for data to transformer'),
    cfg.ListOpt('trans_ports',
                default=[12389],
                help='A list of backend names to use. These backend names '
                     'should be backed by a unique [CONFIG] group '
                     'with its options'),
    cfg.StrOpt('clone_migrate_type',
               default='live',
               help='code or live clone(migrate)'),
    cfg.BoolOpt('is_active_detach_volume',
                default=False,
                help='Provide cloud can detach volume '
                'in instance active or not.'),
    cfg.StrOpt('sys_image',
               default='',
               help='Provide cloud can detach volume '
               'in instance active or not.')
]
birdie_opts = [
    cfg.IntOpt('v2vgateway_api_listen_port',
               default=8899,
               help='Host port for v2v gateway api'),
    cfg.IntOpt('check_timeout',
               default=360,
               help='Host port for v2v gateway api'),
    cfg.IntOpt('check_interval',
               default=1,
               help='Host port for v2v gateway api'),
    ]

keystone_auth_opts = [
    cfg.StrOpt('password',
               secret=True,
               help='Keystone account password'),
    cfg.StrOpt('conveyor_admin_user',
               default='cloud_admin',
               help='Keystone admin user'),
    cfg.StrOpt('conveyor_admin_tenant_name',
               default='admin',
               help='keystone tenant name'),
    cfg.StrOpt('auth_url',
               default='',
               help='keystone auth url'),
    ]


CONF.register_opts(birdie_opts)
CONF.register_opts(global_opts)
CONF.register_opts(keystone_auth_opts, group='keystone_authtoken')
