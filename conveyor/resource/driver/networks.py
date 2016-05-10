'''
@author: g00357909
'''
from conveyor import network
from conveyor import exception

from conveyor.resource import resource
from conveyor.resource.driver import base

from conveyor.common import log as logging
LOG = logging.getLogger(__name__)

class NetworkResource(base.resource):
    
    def __init__(self, context, collected_resources=None,
                collected_parameters=None, collected_dependencies=None):
        self.context = context
        self._tenant_id = self.context.project_id
        self.neutron_api = network.API()
        self._collected_resources = collected_resources or {}
        self._collected_parameters = collected_parameters or {}
        self._collected_dependencies = collected_dependencies or {}

    def extract_nets(self, net_ids, with_subnets=False):
        
        net_objs = []
        netResources = []
            
        if not net_ids:
            LOG.info('Extract resources of all networks.')
            net_objs = filter(self._tenant_filter, 
                            self.neutron_api.network_list(self.context))
        else:
            LOG.info('Extract resources of networks: %s', net_ids)
            #remove duplicate nets
            net_ids = {}.fromkeys(net_ids).keys()
            for net_id in net_ids:
                try:
                    net = self.neutron_api.get_network(self.context, net_id)
                    net_objs.append(net)
                except Exception as e:
                    msg = "Network resource <%s> could not be found. %s" \
                            % (net_id, unicode(e))
                    LOG.error(msg)
                    raise exception.ResourceNotFound(message=msg)
                
        #every net_obj is a dict  
        for net in net_objs:
            net_id = net.get('id')
            net_res = self._collected_resources.get(net_id)
            if net_res:
                netResources.append(net_res)
                continue
            
            properties = {
                'name': net.get('name'),
                'admin_state_up': net.get('admin_state_up'),
                'shared': net.get('shared')
            }
            
            value_specs = {}
            if net.get('provider:physical_network') is not None:
                value_specs['provider:physical_network'] = net.get('provider:physical_network')
            if net.get('provider:network_type') is not None:
                value_specs['provider:network_type'] = net.get('provider:network_type')
            if net.get('provider:segmentation_id') is not None:
                value_specs['provider:segmentation_id'] = net.get('provider:segmentation_id')
            if net.get('router:external') is not None:
                value_specs['router:external'] = net.get('router:external')
                               
            if value_specs:
                properties['value_specs'] = value_specs
            
            resource_type = "OS::Neutron::Net"
            resource_name = 'network_%d' % self._get_resource_num(resource_type)
            
            if with_subnets:
                self.extract_subnets_of_network(resource_name, net.get('subnets'))
                
            net_res = resource.Resource(resource_name, resource_type,
                                        net_id, properties=properties)
             
            net_dep = resource.ResourceDependency(net_id, net.get('name'), 
                                                       resource_name, resource_type)
             
            self._collected_resources[net_id] = net_res
            self._collected_dependencies[net_id] = net_dep
            netResources.append(net_res)
        
        if net_ids and not netResources:
            msg = "Network resource extracted failed, \
                    can't find the network with id of %s." % net_ids
            LOG.error(msg)
            raise exception.ResourceNotFound(message=msg)
            
        return netResources

    def extract_subnets(self, subnet_ids):
        
        subnet_objs = []
        subnetResources = []
            
        if not subnet_ids:
            LOG.debug('Extract resources of all subnets.')
            subnet_objs = filter(self._tenant_filter, 
                              self.neutron_api.subnet_list(self.context))
        else:
            LOG.debug('Extract resources of subnets: %s', subnet_ids)
            #remove duplicate nets
            subnet_ids = {}.fromkeys(subnet_ids).keys()
            for subnet_id in subnet_ids:
                try:
                    subnet = self.neutron_api.get_subnet(self.context, subnet_id)
                    subnet_objs.append(subnet)
                except Exception as e:
                    msg = "Subnet resource <%s> could not be found. %s" \
                            % (subnet_id, unicode(e))
                    LOG.error(msg)
                    raise exception.ResourceNotFound(message=msg)
        
        for subnet in subnet_objs:
            subnet_id = subnet.get('id')
            subnet_res = self._collected_resources.get(subnet_id)
            if subnet_res:
                subnetResources.append(subnet_res)
                continue
            
            properties = {
                'name': subnet.get('name', ''),
                'allocation_pools': subnet.get('allocation_pools', []),
                'cidr': subnet.get('cidr', ''),
                'gateway_ip': subnet.get('gateway_ip', ''),
                'enable_dhcp': subnet.get('enable_dhcp', False),
                'ip_version': subnet.get('ip_version'),
            }
            
            if subnet.get('dns_nameservers'):
                properties['dns_nameservers'] = subnet.get('dns_nameservers')
            if subnet.get('host_routes'):
                properties['host_routes'] = subnet.get('host_routes')
            
            net_id = subnet.get('network_id')
            network_res = None
            if net_id:
                network_res = self.extract_nets([net_id])
            if not network_res:
                LOG.error("Network resource %s could not be found.", net_id)
                raise exception.ResourceNotFound(resource_type='Network', resource_id=net_id)
            properties['network_id'] = {'get_resource': network_res[0].name}
            
            resource_type = "OS::Neutron::Subnet"
            resource_name = 'subnet_%d' % self._get_resource_num(resource_type)
            subnet_res = resource.Resource(resource_name, resource_type,
                                subnet_id, properties=properties)
             
            subnet_dep = resource.ResourceDependency(subnet_id, subnet.get('name'), 
                                                       resource_name, resource_type, 
                                                       dependencies=[network_res[0].name])
             
            self._collected_resources[subnet_id] = subnet_res
            self._collected_dependencies[subnet_id] = subnet_dep
            subnetResources.append(subnet_res)
            
        if subnet_ids and not subnetResources:
            msg = "Subnet resource extracted failed, \
                    can't find the subnet with id of %s." % subnet_ids
            LOG.error(msg)
            raise exception.ResourceNotFound(message=msg)
        
        return subnetResources

        
    def extract_subnets_of_network(self, network_resource_name, subnet_ids):
        
        LOG.debug('Extract resources of subnets %s ', subnet_ids)
        
        if not network_resource_name or not subnet_ids:
            return
        
        #remove duplicate subnets
        subnet_ids = {}.fromkeys(subnet_ids).keys()
        
        for subnet_id in subnet_ids:
            try:
                subnet = self.neutron_api.get_subnet(self.context, subnet_id)
            except Exception as e:
                msg = "Subnet resource <%s> could not be found. %s" \
                        % (subnet_id, unicode(e))
                LOG.error(msg)
                raise exception.ResourceNotFound(message=msg)
            
            subnet_id = subnet.get('id')
            properties = {
                'name': subnet.get('name', ''),
                'allocation_pools': subnet.get('allocation_pools', []),
                'cidr': subnet.get('cidr', ''),
                'gateway_ip': subnet.get('gateway_ip', ''),
                'enable_dhcp': subnet.get('enable_dhcp', False),
                'ip_version': subnet.get('ip_version'),
                'network_id': {'get_resource': network_resource_name}
            }
            
            if subnet.get('dns_nameservers'):
                properties['dns_nameservers'] = subnet.get('dns_nameservers')
            if subnet.get('host_routes'):
                properties['host_routes'] = subnet.get('host_routes')
            
            resource_type = "OS::Neutron::Subnet"
            resource_name = 'subnet_%d' % self._get_resource_num(resource_type)
            subnet_res = resource.Resource(resource_name, resource_type,
                                subnet_id, properties=properties)
             
            subnet_dep = resource.ResourceDependency(subnet_id, subnet.get('name'), 
                                                       resource_name, resource_type, 
                                                       dependencies=[network_resource_name])
             
            self._collected_resources[subnet_id] = subnet_res
            self._collected_dependencies[subnet_id] = subnet_dep


    def extract_ports(self, port_ids):
        
        port_objs = []
        portResources = []
            
        if not port_ids:
            LOG.debug('Extract resources of all ports.')
            port_objs = filter(self._tenant_filter, 
                                self.neutron_api.port_list(self.context))
        else:
            LOG.debug('Extract resources of ports: %s', port_ids)
            #remove duplicate ports
            port_ids = {}.fromkeys(port_ids).keys()
            for port_id in port_ids:
                try:
                    port = self.neutron_api.get_port(self.context, port_id)
                    port_objs.append(port)
                except Exception as e:
                    msg = "Port resource <%s> could not be found. %s" \
                            % (port_id, unicode(e))
                    LOG.error(msg)
                    raise exception.ResourceNotFound(message=msg)
                
        #every port_obj is a dict  
        for port in port_objs:
            port_id = port.get('id')
            port_res = self._collected_resources.get(port_id)
            if port_res:
                portResources.append(port_res)
                continue
            
            properties = {
                'name': port.get('name', ''),
                'mac_address': port.get('mac_address', ''),
                'admin_state_up': port.get('admin_state_up', True),
            }
            dependencies = []
            
            if port.get('allowed_address_pairs'):
                properties['allowed_address_pairs'] = port.get('allowed_address_pairs')
            
            value_specs = {}
            if port.get('binding:profile') is not None:
                value_specs['binding:profile'] = port.get('binding:profile')
            if port.get('binding:vnic_type') is not None:
                value_specs['binding:vnic_type'] = port.get('binding:vnic_type')
                               
            #if value_specs:
            #    properties['value_specs'] = value_specs
            
            
            if port.get('security_groups'):
                secgroup_ids = port.get('security_groups')
                secgroup_res = self.extract_secgroups(secgroup_ids)
                secgroup_properties = []
                for sec in secgroup_res:
                    secgroup_properties.append({'get_resource': sec.name})
                    dependencies.append(sec.name)
                properties['security_groups'] = secgroup_properties
            
            fixed_ips_properties = []
            fixed_ips = port.get('fixed_ips', [])
            for opt in fixed_ips:
                subnet_id = opt.get('subnet_id')
                ip_address = opt.get('ip_address')
                if not subnet_id or not ip_address:
                    msg = "Port information is abnormal. \
                            'subnet_id' or 'ip_address' attribute is None"
                    LOG.error(msg)
                    raise exception.ResourceAttributesException(message=msg)
                
                subnet_res = self.extract_subnets([subnet_id])
                if not subnet_res:
                    LOG.error("Subnet resource %s could not be found.", subnet_id)
                    raise exception.ResourceNotFound(resource_type='Subnet', 
                                                     resource_id=subnet_id)
                
                fixed_ips_properties.append({'subnet_id': 
                                             {'get_resource': subnet_res[0].name}, 
                                             'ip_address': ip_address})
                
                network_name = subnet_res[0].properties.get('network_id').get('get_resource')
                properties['network_id'] = {"get_resource": network_name}
                dependencies.append(network_name)
                dependencies.append(subnet_res[0].name)
                
            properties['fixed_ips'] = fixed_ips_properties
            
            resource_type = "OS::Neutron::Port"
            resource_name = 'port_%d' % self._get_resource_num(resource_type)
            
            port_res = resource.Resource(resource_name, resource_type,
                                        port_id, properties=properties)
            
            #remove duplicate dependencies
            dependencies = {}.fromkeys(dependencies).keys()
            port_dep = resource.ResourceDependency(port_id, 
                                                   port.get('name'), 
                                                   resource_name, 
                                                   resource_type,
                                                   dependencies=dependencies)
            
            self._collected_resources[port_id] = port_res
            self._collected_dependencies[port_id] = port_dep
            portResources.append(port_res)
            
        if port_ids and not portResources:
            msg = "Port resource extracted failed, \
                    can't find the port with id of %s." % port_ids
            LOG.error(msg)
            raise exception.ResourceNotFound(message=msg)
        
        return portResources


    def extract_floatingips(self, floatingip_ids):
        
        floatingip_objs = []
        floatingipResources = []
            
        if not floatingip_ids:
            LOG.debug('Extract resources of floating ips.')
            floatingip_objs = filter(self._tenant_filter, 
                                     self.neutron_api.floatingip_list(self.context))
                
        else:
            LOG.debug('Extract resources of floating ips: %s', floatingip_ids)
            #remove duplicate floatingips
            floatingip_ids = {}.fromkeys(floatingip_ids).keys()
            for floatingip_id in floatingip_ids:
                try:
                    floatingip = self.neutron_api.get_floatingip(self.context, floatingip_id)
                    floatingip_objs.append(floatingip)
                except Exception as e:
                    msg = "FloatingIp resource <%s> could not be found. %s" \
                            % (floatingip_id, unicode(e))
                    LOG.error(msg)
                    raise exception.ResourceNotFound(message=msg)
            
        for floatingip in floatingip_objs:
            floatingip_id = floatingip.get('id')
            floatingip_res = self._collected_resources.get(floatingip_id)
            if floatingip_res:
                floatingipResources.append(floatingip_res)
                continue
                
            properties = {}
            dependencies = []
            
            floating_network_id = floatingip.get('floating_network_id')
            floating_ip_address = floatingip.get('floating_ip_address')
            
            if not floating_network_id or not floating_ip_address:
                msg = "FloatingIp information is abnormal. \
                        'floating_network_id' or 'floating_ip_address' attribute is None"
                LOG.error(msg)
                raise exception.ResourceAttributesException(message=msg)
            
            net_res = self.extract_nets([floating_network_id], with_subnets=True)
            properties['floating_network_id'] = {'get_resource': net_res[0].name}
            dependencies.append(net_res[0].name)

            router_id = floatingip.get('router_id')
            router_res = None
            if router_id:
                router_res = self.extract_routers([router_id])
                #dependencies.append(router_res[0].name)
             
            port_id = floatingip.get('port_id')
            port_res = None
            if port_id:
                port_res = self.extract_ports([port_id])
                properties['port_id'] = {'get_resource': port_res[0].name}
                dependencies.append(port_res[0].name) 

            fixed_id_addr = floatingip.get('fixed_ip_address')
            if router_res and port_res and fixed_id_addr:
                fixed_ips = port_res[0].properties.get('fixed_ips')
                subnet_res_name = None
                
                if len(fixed_ips) == 1:
                    subnet_res_name = fixed_ips[0].get('subnet_id', {}).get('get_resource')
                elif len(fixed_ips) >= 2:
                    for f in fixed_ips:
                        if f.get('ip_address', '') == fixed_id_addr:
                            subnet_res_name = f.get('subnet_id', {}).get('get_resource')
                            #If port has multiple fixed ips, 
                            #we have to specify the ip addr in floatingip properties
                            ip_index = fixed_ips.index(f)
                            properties['fixed_ip_address'] = {'get_attr': 
                                                              [port_res[0].name, 
                                                                'fixed_ips', 
                                                                ip_index, 
                                                                'ip_address']}
                            
                            break
                
                #build router interface
                if subnet_res_name:
                    subnet_res = self._get_resource_by_name(subnet_res_name)
                    if subnet_res:
                        self._extract_router_interface(router_res[0], subnet_res)
                
            resource_type = "OS::Neutron::FloatingIP"
            resource_name = 'floatingip_%d' % self._get_resource_num(resource_type)
            floatingip_res = resource.Resource(resource_name, resource_type,
                                               floatingip_id, properties=properties)

            #remove duplicate dependencies
            dependencies = {}.fromkeys(dependencies).keys()
            floatingip_dep = resource.ResourceDependency(floatingip_id, '', 
                                                       resource_name, resource_type,
                                                       dependencies=dependencies)
            
            self._collected_resources[floatingip_id] = floatingip_res
            self._collected_dependencies[floatingip_id] = floatingip_dep
            floatingipResources.append(floatingip_res)
            
        if floatingip_ids and not floatingipResources:
            msg = "FloatingIp resource extracted failed, \
                    can't find the floatingip with id of %s." % floatingip_ids
            LOG.error(msg)
            raise exception.ResourceNotFound(message=msg)
        
        return floatingipResources

    def _extract_router_interface(self, router_res, subnet_res):
        LOG.debug("Extract resources of router interface connecting %s and %s.", 
                        router_res.name, subnet_res.name)
        
        #step 1: judge whether the interface exists
        interfaces = self.neutron_api.port_list(self.context, 
                                                device_owner="network:router_interface",
                                                device_id=router_res.id)
        
        interface = None
        
        for infa in interfaces:
            if interface:
                break
            fixed_ips = infa.get("fixed_ips", [])
            for fip in fixed_ips:
                if fip.get("subnet_id", "") == subnet_res.id:
                    interface = infa
                    break
        
        if not interface:
            return
           
        #step 2: build interface
        properties = {
                'router_id': {'get_resource': router_res.name},
                'subnet_id': {'get_resource': subnet_res.name}
            }
        dependencies = [router_res.name, subnet_res.name]
            
        interface_id = interface.get('id', '')
        
        resource_type = "OS::Neutron::RouterInterface"
        resource_name = '%s_interface_0' % router_res.name
        interface_res = resource.Resource(resource_name, resource_type,
                            interface_id, properties=properties)
         
        interface_dep = resource.ResourceDependency(interface_id, interface.get('name', ''), 
                                                   resource_name, resource_type,
                                                   dependencies=dependencies)
         
        self._collected_resources[interface_id] = interface_res
        self._collected_dependencies[interface_id] = interface_dep
            
        return interface_res
    

    def extract_routers(self, router_ids):
        
        router_objs = []
        routerResources = []

        if not router_ids:
            LOG.info('Extract resources of routers.')
            router_objs = filter(self._tenant_filter, 
                                self.neutron_api.router_list(self.context))
        else:
            LOG.debug('Extract resources of routers: %s', router_ids)
            #remove duplicate routers
            router_ids = {}.fromkeys(router_ids).keys()
            for router_id in router_ids:
                try:
                    router = self.neutron_api.get_router(self.context, router_id)
                    router_objs.append(router)
                except Exception as e:
                    msg = "Router resource <%s> could not be found. %s" \
                            % (router_id, unicode(e))
                    LOG.error(msg)
                    raise exception.ResourceNotFound(message=msg)
                    
        #every router_obj is a dict
        for router in router_objs:
            router_id = router.get('id')
            router_res = self._collected_resources.get(router_id)
            if router_res:
                routerResources.append(router_res)
                continue
            
            properties = {
                'name': router.get('name'),
                'admin_state_up': router.get('admin_state_up')
            }
            dependencies = []
            
            external_gateway_info = router.get('external_gateway_info')
            
            if external_gateway_info:
                network = external_gateway_info.get('network_id')
                if network:
                    net_res = self.extract_nets([network], with_subnets=True)
                    if net_res:
                        properties['external_gateway_info'] = {'network': {'get_resource': net_res[0].name},
                                                               'enable_snat': external_gateway_info.get('enable_snat')}
                        dependencies.append(net_res[0].name)
            
            resource_type = "OS::Neutron::Router"
            resource_name = 'router_%d' % self._get_resource_num(resource_type)
            router_res = resource.Resource(resource_name, resource_type,
                                router_id, properties=properties)

            #remove duplicate dependencies
            dependencies = {}.fromkeys(dependencies).keys()
            router_dep = resource.ResourceDependency(router_id, router.get('name'), 
                                                       resource_name, resource_type,
                                                       dependencies=dependencies)
             
            self._collected_resources[router_id] = router_res
            self._collected_dependencies[router_id] = router_dep
            
            routerResources.append(router_res)
            
        if router_ids and not routerResources:
            msg = "Router resource extracted failed, \
                    can't find the router with id of %s." % router_ids
            LOG.error(msg)
            raise exception.ResourceNotFound(message=msg)
        
        return routerResources

    def extract_secgroups(self, secgroup_ids):
        
        secgroup_objs = []
        secgroupResources = []
            
        if not secgroup_ids:
            LOG.debug('Extract resources of security groups')
            secgroup_objs = filter(self._tenant_filter, 
                                    self.neutron_api.secgroup_list(self.context))
        else:
            LOG.debug('Extract resources of security groups: %s', secgroup_ids)
            #remove duplicate secgroups
            secgroup_ids = {}.fromkeys(secgroup_ids).keys()
            for sec_id in secgroup_ids:
                try:
                    sec = self.neutron_api.get_security_group(self.context, sec_id)
                    secgroup_objs.append(sec)
                except Exception as e:
                    msg = "SecurityGroup resource <%s> could not be found. %s" \
                            % (sec_id, unicode(e))
                    LOG.error(msg)
                    raise exception.ResourceNotFound(message=msg)
            
        for sec in secgroup_objs:
            sec_id = sec.get('id')
            sec_res = self._collected_resources.get(sec_id)
            if sec_res:
                secgroupResources.append(sec_res)
                continue
            
            if sec.get('name') == 'default':
                sec['name'] = '_default'
            
            properties = {
                'description': sec.get('description'),
                'name': sec.get('name'),
            }
            
            resource_type = "OS::Neutron::SecurityGroup"
            resource_name = 'security_group_%d' % self._get_resource_num(resource_type)
            sec_res = resource.Resource(resource_name, resource_type,
                                        sec_id, properties=properties)

            #Put secgroup into collected_resources first before extracting rules to
            #avoid recycle dependencies.
            self._collected_resources[sec_id] = sec_res

            #Extract secgroup rules.
            rules, dependencies = self._build_rules(sec.get('security_group_rules'))
            self._collected_resources[sec_id].add_property('rules', rules)
            
            #remove duplicate dependencies
            dependencies = {}.fromkeys(dependencies).keys()
            sec_dep = resource.ResourceDependency(sec_id, sec.get('name'), 
                                                  resource_name, resource_type,
                                                  dependencies=dependencies)
            
            self._collected_dependencies[sec_id] = sec_dep
            secgroupResources.append(sec_res)

        if secgroup_ids and not secgroupResources:
            msg = "Security group resource extracted failed, \
                    can't find the Security group with id of %s." % secgroup_ids
            LOG.error(msg)
            raise exception.ResourceNotFound(message=msg)
        
        return secgroupResources

    def _build_rules(self, rules):
        brules = []
        dependencies = []
        for rule in rules:
            if rule.get('protocol') == 'any':
                del rule['protocol']
            #Only extract secgroups in first level, ignore the dependent secgroup.
            rg_id = rule.get('remote_group_id')
            if rg_id is not None:
                rule['remote_mode'] = "remote_group_id"
                if rg_id == rule.get('security_group_id'):
                    del rule['remote_group_id']
#                 else:
#                     res = self.extract_secgroups([rg_id])
#                     if res:
#                         rule['remote_group_id'] = {'get_resource': res[0].name}
#                         dependencies.append(res[0].name)
#                     else:
#                         del rule['remote_group_id']
                        
            del rule['tenant_id']
            del rule['id']
            del rule['security_group_id']
            rule = dict((k, v) for k, v in rule.items() if v is not None)
            brules.append(rule)
        return brules, dependencies

    def _tenant_filter(self, res):
        tenant_id = res.get('tenant_id')
        if not tenant_id:
            raise "%s object has no attribute 'tenant_id' " % res.__class__
        return tenant_id == self._tenant_id

