#!/usr/bin/env bash

for ((i=0;i<=59;i++));
do
    for bin in api clone resource ; do 
        if  ! pgrep -f conveyor-$bin >/dev/null ;
        then
            (su openstack -c "/usr/bin/python /usr/bin/conveyor-$bin --config-file=/etc/conveyor/conveyor.conf > /dev/null 2>&1" &)
            echo "restart conveyor-$bin...  $(date)"
        fi
    done
    sleep 1s
done
