# Copyright 2010 Jacob Kaplan-Moss

# Copyright (c) 2011 OpenStack Foundation
# All Rights Reserved.
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

"""
Base utilities to build API operation managers and objects on top of.
"""


# Python 2.4 compat
try:
    all
except NameError:
    def all(iterable):
        return True not in (not x for x in iterable)


def getid(obj):
    """
    Abstracts the common pattern of allowing both an object or an object's ID
    as a parameter when dealing with relationships.
    """
    try:
        return obj.id
    except AttributeError:
        return obj


class Manager(object):
    """
    Managers interact with a particular type of API (servers, flavors, images,
    etc.) and provide CRUD operations for them.
    """

    def __init__(self, client, url):
        
        self.client = client
        self.url = url
        

    def _list(self, url, response_key, obj_class=None, body=None):
        
        url = self.url + url
        resp = None
        if body:
            resp, body = self.client.post(url, body=body)
        else:
            resp, body = self.client.get(url)

    def _get(self, url, response_key=None):
        url = self.url + url
        resp, body = self.client.get(url)
        return body

    def _create(self, url, body, response_key, return_raw=False, **kwargs):
        url = self.url + url
        resp, body = self.client.post(url, body=body)
        return body
   

    def _delete(self, url):
        url = self.url + url
        resp, body = self.client.delete(url)
        return body

    def _update(self, url, body, **kwargs):
        url = self.url + url
        resp, body = self.client.put(url, body=body)
        return body
    
    def _clone_volume(self, url, body, **kwargs):
        url = self.url + url
        resp, body = self.client.post(url, body=body)
        return body

    def _mount_disk(self, url, body, **kwargs):
        url = self.url + url
        resp, body = self.client.post(url, body=body)
        return body

    def _get_disk_format(self, url, body, **kwargs):
        url = self.url + url
        resp, body = self.client.post(url, body=body)
        return body

    def _get_disk_mount_point(self, url, body, **kwargs):
        url = self.url + url
        resp, body = self.client.post(url, body=body)
        return body
    
    def _get_disk_name(self, url, body, **kwargs):
        url = self.url + url
        resp, body = self.client.post(url, body=body)
        return body
    
    def _post(self, url, body, **kwargs):
        url = self.url + url
        resp, body = self.client.post(url, body=body)
        return body
