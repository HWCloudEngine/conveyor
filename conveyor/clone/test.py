from conveyor.conveyoragentclient.v1 import client as conveyorclient
from conveyor.resource import api as resource_api
from conveyor.brick import base
               default=120,
               default=1,
               help='clone driver'),
    cfg.IntOpt('allocate_retries',
               default=120,
               help='clone driver'),
    cfg.IntOpt('allocate_retries_interval',
               help='clone driver'),               
        self.conveyor_cmd = base.MigrationCmd()
        
        self.resource_api = resource_api.ResourceAPI()
    def _await_port_status(self, context, port_id, ip_address):
                exit_status = self._check_connect_sucess(ip_address)
                if exit_status:
                    return attempt
                else:
                    continue
    def _check_connect_sucess(self, ip_address, times_for_check=3, interval=1):
        '''check ip can ping or not'''
        exit_status = False

        for i in range(times_for_check):
            time.sleep(interval)
            exit_status = self.conveyor_cmd.check_ip_connect(ip_address)
            if exit_status:
                break
            else:
                continue

        return exit_status
    def _await_data_trans_status(self, context, host, port, task_ids, state_map, plan_id=None):
    
        start = time.time()
        retries = CONF.instance_allocate_retries
        if retries < 0:
            LOG.warn(_LW("Treating negative config value (%(retries)s) for "
                         "'instance_create_retries' as 0."),
                     {'retries': retries})
        # (1) treat  negative config value as 0
        # (2) the configured value is 0, one attempt should be made
        # (3) the configured value is > 0, then the total number attempts
        #      is (retries + 1)
        attempts = 1
        if retries >= 1:
            attempts = retries + 1
        for attempt in range(1, attempts + 1):
            #record all volume data transformer task state
            task_states = []
            for task_id in task_ids:
                cls = conveyorclient.get_birdiegateway_client(host, port)
                status = cls.vservices.get_data_trans_status(task_id)
                task_status = status.get('body').get('task_state')
                #if one volume data transformer failed, this clone failed
                if 'DATA_TRANS_FAILED' == task_status:                    
                    plan_state = state_map.get(task_status)
                    values = {}
                    values['plan_status'] = plan_state
                    values['task_status'] = task_status
                    self.resource_api.update_plan(context, plan_id, values)
                    return attempt
                task_states.append(task_status)
            #as long as one volume data does not transformer finished, clone plan state is cloning
            if 'DATA_TRANSFORMING' in task_states:
                    plan_state = state_map.get('DATA_TRANSFORMING')
                    values = {}
                    values['plan_status'] = plan_state
                    values['task_status'] = 'DATA_TRANSFORMING'
                    self.resource_api.update_plan(context, plan_id, values)
            #otherwise, plan state is finished
            else:
                LOG.debug(_("Data transformer finished!"))
                plan_state = state_map.get('DATA_TRANS_FINISHED')
                values = {}
                values['plan_status'] = plan_state
                values['task_status'] = 'DATA_TRANS_FINISHED'
                self.resource_api.update_plan(context, plan_id, values)
                return attempt 
                
            greenthread.sleep(CONF.allocate_retries_interval)
            
        # NOTE(harlowja): Should only happen if we ran out of attempts
        raise exception.InstanceNotCreated(instance_id=task_id,
                                         seconds=int(time.time() - start),
                                         attempts=attempts)
            
            
                                               port_wait_fun=self._await_port_status,
                                               trans_data_wait_fun=self._await_data_trans_status)
            _msg='Instance clone error: %s' % e
            raise exception.V2vException(message=_msg)
    

    def start_template_migrate(self, context, resource_name, instance):
        ''' here reset template resource info if the value of key just a link '''
                            
        if not instance:
            LOG.error("Resources in template is null")
                    
        #(if the value of key links to other, here must set again)
        try: 
            self.clone_driver.start_template_migrate(context, resource_name, instance,
                                               port_wait_fun=self._await_port_status,
                                               trans_data_wait_fun=self._await_data_trans_status)
        
        except Exception as e:
            LOG.error(_LW("Migrate vm error: %s"), e)
            _msg='Instance clone error: %s' % e
            raise exception.V2vException(message=_msg)
        
