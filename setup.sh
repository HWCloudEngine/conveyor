#!/bin/sh
###########################################
####  conveyor project init shell file    ###
####  create db keystone register       ###
####  2016/1/14                         ###
###########################################


#v2v api service IP
API_SERVICE_IP=162.3.253.60
API_SERVICE_PORT=9999
 
LOG_DIR=/var/log/fusionsphere/component/conveyor 
LOG_FILE=${LOG_DIR}/install.log

TEMPLATE_DIR=/opt/HUAWEI/image/plans

#source code file directory
CODE_DIR=/usr/lib64/python2.6/site-packages
CONFIG_DIR=/etc/conveyor
BIN_DIR=/usr/bin

#conveyor service register user name
API_REGISTER_USER_NAME=conveyor

#conveyor service register user password
API_REGISTER_USER_PASSWD=FusionSphere123

#conveyor register relation role name
API_REGISTER_ROLE_NAME=admin

#conveyor register relation tenant name
API_REGISTER_TENANT_NAME=service

#conveyor service register service name
API_REGISTER_SERVICE_NAME=conveyor

#conveyor service register service type
API_REGISTER_SERVICE_TYPE=conveyor


#conveyor config service register user name
CONFIG_REGISTER_USER_NAME=conveyorConfig

#conveyor config service register service name
CONFIG_REGISTER_SERVICE_NAME=conveyorConfig

#conveyor config service register service type
CONFIG_REGISTER_SERVICE_TYPE=conveyorConfig

TIME_CMD=`date '+%Y-%m-%d %H:%M:%S'`
BOOL_TRUE_INT=0
BOOL_FALSE_INT=1
ERROR_INT=2

database_ip="$(awk -F'[:@]' '/^connection/&&$0=$(NF-1)' /etc/nova/nova-api.conf)"

export_openstack_evn() {
	export OS_AUTH_URL=https://identity.$(cps localdomain-get | awk '{A[$2]=$4} END{ print A["localaz"]"."A["localdc"]"."A["domainpostfix"]}'):443/identity/v2.0
	export OS_USERNAME=cloud_admin
	export OS_TENANT_NAME=admin
	export OS_REGION_NAME=$(cps localdomain-get | awk '{A[$2]=$4} END{ print A["localaz"]"."A["localdc"]}')
	export NOVA_ENDPOINT_TYPE=publicURL
	export CINDER_ENDPOINT_TYPE=publicURL
	export OS_ENDPOINT_TYPE=publicURL
	export OS_VOLUME_API_VERSION=2
	export OS_PASSWORD=FusionSphere123
}

export_openstack_evn

clean_config_register_info()
{
   #clean  service register info
   keystone user-delete ${CONFIG_REGISTER_USER_NAME}
   keystone user-role-remove --user=${CONFIG_REGISTER_USER_NAME} --role=${API_REGISTER_ROLE_NAME} --tenant=${API_REGISTER_TENANT_NAME}
   
   #remove endpoint
   for api_service_id in $(keystone service-list | awk '/ '${CONFIG_REGISTER_SERVICE_NAME}' / {print $2}') ; do 
       api_endpoint_id=$(keystone endpoint-list | awk '/ '$api_service_id' /{print $2}')
       api_endpoint_id=$(keystone endpoint-list | awk '/ '$api_service_id' /{print $2}')
       [ -n "$api_endpoint_id" ] && keystone endpoint-delete $api_endpoint_id
       #remove service
       keystone service-delete $api_service_id
   done
}

clean_register_info()
{
   
   #clean  service register info
   keystone user-delete ${API_REGISTER_USER_NAME}
   keystone user-role-remove --user=${API_REGISTER_USER_NAME} --role=${API_REGISTER_ROLE_NAME} --tenant=${API_REGISTER_TENANT_NAME}
   
   #remove endpoint
   for api_service_id in $(keystone service-list | awk '/ '${API_REGISTER_SERVICE_NAME}' / {print $2}') ; do 
       api_endpoint_id=$(keystone endpoint-list | awk '/ '$api_service_id' /{print $2}')
       api_endpoint_id=$(keystone endpoint-list | awk '/ '$api_service_id' /{print $2}')
       [ -n "$api_endpoint_id" ] && keystone endpoint-delete $api_endpoint_id
       #remove service
       keystone service-delete $api_service_id
   done
   
   # clean config register info
   clean_config_register_info
   
}

 

#######################################################################
check_register_user_exist()
{
    user_name=$0
    user=$(keystone user-list | awk '/ '${user_name}' / {print $2}')
	
	if [ $? -ne 0 ]; then
	   echo ${TIME_CMD} "check v2v api register user error."
	   keystone user-list | awk '/ '${user_name}' / {print $2}'
	   return ${ERROR_INT}
	fi
	
	#check is null
	if [ -z $user ]; then
	    #is null
		echo ${TIME_CMD} "check v2v api register user is null"
	    return ${BOOL_TRUE_INT}
	else
	    #other
		echo ${TIME_CMD} "check v2v api register user is " "${user}"
	   return ${BOOL_FALSE_INT}
	fi
}

copy_files_to_dir()
{
    #copy  running file to /usr/bin
    
    for bin in api clone manager all resource rootwrap ; do
        if [ -f ${BIN_DIR}/conveyor-$bin ]; then
	     rm -f ${BIN_DIR}/conveyor-$bin
	fi
		
    cp ./tools/conveyor-$bin ${BIN_DIR}
		
	if [ ! -x ${BIN_DIR}/conveyor-$bin ]; then
	    chmod +x ${BIN_DIR}/conveyor-$bin
	fi	 
    done 

    #copy source code to /usr/lib64/python2.7/dist-packages
	if [ -d ${CODE_DIR}/conveyor ]; then
	   rm -rf ${CODE_DIR}/conveyor
	fi
    cp -r ./conveyor ${CODE_DIR}

    #make config file directory
	if [ -d ${CONFIG_DIR} ]; then
	   rm -rf ${CONFIG_DIR}
	fi
	
    mkdir ${CONFIG_DIR}

    #copy config file to /etc/conveyor
    cp -r ./etc/conveyor/* ${CONFIG_DIR}
    chown -R openstack:openstack ${CONFIG_DIR}
}

#####################################################################
# Function: register_config_service
# Description: register api services info to keystone
# Parameter:
# input:
# $1 -- NA 
# $2 -- NA
# output: NA
# Return:
# RET_OK
# Since: 
#
# Others:NA
#######################################################################
register_config_service()
{
    #check user is register or not
    user_name=${CONFIG_REGISTER_USER_NAME}
	check_register_user_exist ${user_name}
	ret=$?
	if [ $ret -eq ${ERROR_INT} ]; then
	   echo  ${TIME_CMD} "error: v2v api register user"
	   return ${ERROR_INT}	   
	fi
	if [ $ret -eq ${BOOL_TRUE_INT} ]; then
        #register the user of v2v service 
        keystone user-create --name=${CONFIG_REGISTER_USER_NAME} --pass=${API_REGISTER_USER_PASSWD} --email=admin@example.com

        #register v2v user and tenant relation (eg: service Tenant / admin Role)
        keystone user-role-add --user=${CONFIG_REGISTER_USER_NAME} --tenant=${API_REGISTER_TENANT_NAME} --role=${API_REGISTER_ROLE_NAME}
	else
	   echo  ${TIME_CMD} "warning: v2v api register user exist. there not register. user name: " "${API_REGISTER_USER_NAME}"
	fi
	
	keystone service-list | grep -w ${CONFIG_REGISTER_USER_NAME} >/dev/null || {
	    #register v2v service 
	    keystone service-create --name=${CONFIG_REGISTER_SERVICE_NAME} --type=${CONFIG_REGISTER_SERVICE_TYPE} --description="Hybrid conveyor service"
	        
	    #register v2v endpoint
	    serviceId=$(keystone service-list | awk '/ '${CONFIG_REGISTER_SERVICE_NAME}' / {print $2}')

            echo ${TIME_CMD} "begin create endpoint"
	    keystone endpoint-create --region=$OS_REGION_NAME --service-id=${serviceId} \
		--publicurl=http://${API_SERVICE_IP}:${API_SERVICE_PORT}/v1/config/$\(tenant_id\)s \
		--adminurl=http://${API_SERVICE_IP}:${API_SERVICE_PORT}/v1/config/$\(tenant_id\)s \
		--internalurl=http://${API_SERVICE_IP}:${API_SERVICE_PORT}/v1/config/$\(tenant_id\)s
		
		if [ $? -ne 0 ]; then
		   echo "create config endpoint failed"
		   return ${ERROR_INT}
		fi 
	}
}
#####################################################################
# Function: register_api_services
# Description: register api services info to keystone
# Parameter:
# input:
# $1 -- NA 
# $2 -- NA
# output: NA
# Return:
# RET_OK
# Since: 
#
# Others:NA
#######################################################################
register_services()
{
     
    #check user is register or not
        user_name=${API_REGISTER_USER_NAME}
	check_register_user_exist ${user_name}
	ret=$?
	if [ $ret -eq ${ERROR_INT} ]; then
	   echo  ${TIME_CMD} "error: v2v api register user"
	   return ${ERROR_INT}	   
	fi
	if [ $ret -eq ${BOOL_TRUE_INT} ]; then
        #register the user of v2v service 
        keystone user-create --name=${API_REGISTER_USER_NAME} --pass=${API_REGISTER_USER_PASSWD} --email=admin@example.com

        #register v2v user and tenant relation (eg: service Tenant / admin Role)
        keystone user-role-add --user=${API_REGISTER_USER_NAME} --tenant=${API_REGISTER_TENANT_NAME} --role=${API_REGISTER_ROLE_NAME}
	else
	   echo  ${TIME_CMD} "warning: v2v api register user exist. there not register. user name: " "${API_REGISTER_USER_NAME}"
	fi
	
	keystone service-list | grep -w conveyor >/dev/null || {
	    #register v2v service 
	    keystone service-create --name=${API_REGISTER_SERVICE_NAME} --type=${API_REGISTER_SERVICE_TYPE} --description="Hybrid v2v service"
	        
	    #register v2v endpoint
	    serviceId=$(keystone service-list | awk '/ '${API_REGISTER_SERVICE_NAME}' / {print $2}')

            echo ${TIME_CMD} "begin create endpoint"
	    keystone endpoint-create --region=$OS_REGION_NAME --service-id=${serviceId} \
		--publicurl=http://${API_SERVICE_IP}:${API_SERVICE_PORT}/v1/$\(tenant_id\)s \
		--adminurl=http://${API_SERVICE_IP}:${API_SERVICE_PORT}/v1/$\(tenant_id\)s \
		--internalurl=http://${API_SERVICE_IP}:${API_SERVICE_PORT}/v1/$\(tenant_id\)s
		
		if [ $? -ne 0 ]; then
		   echo "create endpoint failed"
		   return ${ERROR_INT}
		fi 
	}
	
	# register config info
	register_config_service
	
	if [ $? -ne 0 ]; then
	   echo "create config endpoint failed"
	   return ${ERROR_INT}
	fi
}

clear_files()
{
     for bin in api clone manager all resource rootwrap; do
        if [ -f ${BIN_DIR}/conveyor-$bin ]; then
	     rm -f ${BIN_DIR}/conveyor-$bin
	    fi
	 done
   
	#remove source code files
	rm -rf ${CODE_DIR}/conveyor
	
	#remove config files
	rm -rf ${CONFIG_DIR}
	
	#remove template_dir
	rm -rf ${TEMPLATE_DIR}
	
	#remove init config
	if [ -f /etc/init.d/conveyored ]; then
	     rm -f /etc/init.d/conveyored
	fi
}

create_db()
{
   /opt/gaussdb/app/bin/gsql -U openstack -W FusionSphere123  -h "$database_ip" POSTGRES -c 'CREATE DATABASE conveyor OWNER openstack;'
}

copy_init_script()
{
    cp ./tools/conveyored /etc/init.d/	
	if [ ! -x /etc/init.d/conveyored ]; then
	    chmod +x /etc/init.d/conveyored
	fi
	insserv conveyored	 
}

create_dir_template()
{
   if [ ! -d ${TEMPLATE_DIR} ]; then
	   mkdir -p ${TEMPLATE_DIR}
	   chown -R openstack:openstack ${TEMPLATE_DIR}
   fi
}
 # create log directory
mkdir -p ${LOG_DIR}
chown -R openstack:openstack ${LOG_DIR}
   
init() {
   #register in keystone
   echo  ${TIME_CMD} "begin register conveyor service."
   register_services
   echo  ${TIME_CMD} "end register conveyor service." 
   
   echo  ${TIME_CMD} "begin create db conveyor."
   create_db
   echo  ${TIME_CMD} "end create db conveyor."
   
   echo ${TIME_CMD} "begin create dir for store template."
   create_dir_template
   echo ${TIME_CMD} "end create dir for store template."
   
   echo ${TIME_CMD} "begin copy init script."
   copy_init_script
   echo ${TIME_CMD} "end copy init script."
}

start() {
    echo  ${TIME_CMD} "begin start conveyor service."
    for bin in ${@:-api clone resource} ; do 
        if  ! pgrep -f "/usr/bin/python /usr/bin/conveyor-$bin" >/dev/null ;
        then
           su openstack -c " /usr/bin/python /usr/bin/conveyor-$bin --config-file=/etc/conveyor/conveyor.conf > /dev/null & "
            echo "restart conveyor-$bin...  $(date)"
        fi
    done
    /usr/bin/python /usr/bin/conveyor-manager --config-file  /etc/conveyor/conveyor.conf  db sync 
    
}

# stop api
# stop api clone
stop() {
    echo  ${TIME_CMD} "begin start conveyor service."
	for bin in ${@:-api clone resource} ; do 
		pgrep -f "/usr/bin/python /usr/bin/conveyor-$bin" && {
			pkill -f "/usr/bin/python /usr/bin/conveyor-$bin"
			echo stop service $pkg_name-$bin successsfull.
		} || {
			echo service $pkg_name-$bin not started.
		}
	done
}
restart() {
	stop; sleep 1; start;
}

install() {

     echo "install conveyor..."
     
     #init the env
     init
     
     #copy_file bin source_code config_file
     copy_files_to_dir
     
     
     #start service
     start   
}

uninstall() {
     #stop service
     stop
     
     #clear source_code bin config_file
     clear_files
     
     #clean service register
     clean_register_info
     
     #clean database conveyor
     /opt/gaussdb/app/bin/gsql -U openstack -W FusionSphere123  -h "$database_ip" POSTGRES -c 'drop DATABASE conveyor;'
}


echo init uninstall install start stop restart | grep -w ${1:-NOT} >/dev/null && $@  >> "${LOG_FILE}" 2>&1

