# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
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

"""Cinder base exception handling.

Includes decorator for re-raising Cinder-type exceptions.

SHOULD include dedicated exception logging.

"""

import sys

from oslo.config import cfg
import six
import webob.exc

from conveyor.common import log as logging

from conveyor.i18n import _, _LE


LOG = logging.getLogger(__name__)

exc_log_opts = [
    cfg.BoolOpt('fatal_exception_format_errors',
                default=False,
                help='Make exception message format errors fatal.'),
]

CONF = cfg.CONF
CONF.register_opts(exc_log_opts)


class ConvertedException(webob.exc.WSGIHTTPException):
    def __init__(self, code=400, title="", explanation=""):
        self.code = code
        self.title = title
        self.explanation = explanation
        super(ConvertedException, self).__init__()


class Error(Exception):
    pass


class V2vException(Exception):
    """Base Birdie Exception

    To correctly use this class, inherit from it and define
    a 'message' property. That message will get printf'd
    with the keyword arguments provided to the constructor.

    """
    message = _("An unknown exception occurred.")
    code = 500
    headers = {}
    safe = False

    def __init__(self, message=None, **kwargs):
        self.kwargs = kwargs
        self.kwargs['message'] = message

        if 'code' not in self.kwargs:
            try:
                self.kwargs['code'] = self.code
            except AttributeError:
                pass

        for k, v in self.kwargs.iteritems():
            if isinstance(v, Exception):
                self.kwargs[k] = six.text_type(v)

        if self._should_format():
            try:
                message = self.message % kwargs

            except Exception:
                exc_info = sys.exc_info()
                # kwargs doesn't match a variable in the message
                # log the issue and the kwargs
                LOG.exception(_LE('Exception in string format operation'))
                for name, value in kwargs.iteritems():
                    LOG.error(_LE("%(name)s: %(value)s"),
                              {'name': name, 'value': value})
                if CONF.fatal_exception_format_errors:
                    raise exc_info[0], exc_info[1], exc_info[2]
                # at least get the core message out if something happened
                message = self.message
        elif isinstance(message, Exception):
            message = six.text_type(message)

        # NOTE(luisg): We put the actual message in 'msg' so that we can access
        # it, because if we try to access the message via 'message' it will be
        # overshadowed by the class' message attribute
        self.msg = message
        super(V2vException, self).__init__(message)

    def _should_format(self):
        return self.kwargs['message'] is None or '%(message)' in self.message

    def __unicode__(self):
        return six.text_type(self.msg)



class NotAuthorized(V2vException):
    message = _("Not authorized.")
    code = 403


class AdminRequired(NotAuthorized):
    message = _("User does not have admin privileges")


class Invalid(V2vException):
    message = _("Unacceptable parameters.")
    code = 400


class SfJsonEncodeFailure(V2vException):
    message = _("Failed to load data into json format")


class InvalidResults(Invalid):
    message = _("The results are invalid.")


class InvalidInput(Invalid):
    message = _("Invalid input received: %(reason)s")


class InvalidContentType(Invalid):
    message = _("Invalid content type %(content_type)s.")


# Cannot be templated as the error syntax varies.
# msg needs to be constructed when raised.
class InvalidParameterValue(Invalid):
    message = _("%(err)s")


class InvalidAuthKey(Invalid):
    message = _("Invalid auth key: %(reason)s")


class InvalidConfigurationValue(Invalid):
    message = _('Value "%(value)s" is not valid for '
                'configuration option "%(option)s"')


class ServiceUnavailable(Invalid):
    message = _("Service is unavailable at this time.")


class InvalidUUID(Invalid):
    message = _("Expected a uuid but received %(uuid)s.")


class APIException(V2vException):
    message = _("Error while requesting %(service)s API.")

    def __init__(self, message=None, **kwargs):
        if 'service' not in kwargs:
            kwargs['service'] = 'unknown'
        super(APIException, self).__init__(message, **kwargs)


class APITimeout(APIException):
    message = _("Timeout while requesting %(service)s API.")


class NotFound(V2vException):
    message = _("Resource could not be found.")
    code = 404
    safe = True

class FileNotFound(NotFound):
    message = _("File %(file_path)s could not be found.")


class MalformedRequestBody(V2vException):
    message = _("Malformed message body: %(reason)s")


class ConfigNotFound(NotFound):
    message = _("Could not find config at %(path)s")


class ParameterNotFound(NotFound):
    message = _("Could not find parameter %(param)s")


class PasteAppNotFound(NotFound):
    message = _("Could not load paste app '%(name)s' from %(path)s")


class NoValidHost(V2vException):
    message = _("No valid host was found. %(reason)s")


class NoMoreTargets(V2vException):
    """No more available targets."""
    pass


class QuotaError(V2vException):
    message = _("Quota exceeded: code=%(code)s")
    code = 413
    headers = {'Retry-After': 0}
    safe = True

class EvaluatorParseException(Exception):
    message = _("Error during evaluator parsing: %(reason)s")


class ObjectActionError(V2vException):
    message = _('Object action %(action)s failed because: %(reason)s')


class ObjectFieldInvalid(V2vException):
    message = _('Field %(field)s of %(objname)s is not an instance of Field')


class UnsupportedObjectError(V2vException):
    message = _('Unsupported object type %(objtype)s')


class OrphanedObjectError(V2vException):
    message = _('Cannot call %(method)s on orphaned %(objtype)s object')


class IncompatibleObjectVersion(V2vException):
    message = _('Version %(objver)s of %(objname)s is not supported')


# ZFSSA NFS driver exception.
class WebDAVClientError(V2vException):
        message = _("The WebDAV request failed. Reason: %(msg)s, "
                    "Return code/reason: %(code)s, Source Volume: %(src)s, "
                    "Destination Volume: %(dst)s, Method: %(method)s.")


class Forbidden(V2vException):
    ec2_code = 'AuthFailure'
    message = _("Not authorized.")
    code = 403

class ReadOnlyFieldError(V2vException):
    message = _('Cannot modify readonly field %(field)s')

class VolumeNotFound(V2vException):
    message = _('Cannot found volume')
    
class CinderConnectionFailed(V2vException):
    message = _('Connect cinder service failed')

class ServerNotFound(V2vException):
    message = _('Query server  not  fount')
    
class InstanceNotCreated(V2vException):
    message = _("Instance %(instance_id)s did not finish being created"
                " even after we waited %(seconds)s seconds or %(attempts)s"
                " attempts.")

class VolumeNotCreated(V2vException):
    message = _("Volume %(volume_id)s did not finish being created"
                " even after we waited %(seconds)s seconds or %(attempts)s"
                " attempts.")

class VolumeNotAttach(V2vException):
    message = _("Volume %(volume_id)s did not finish being attached"
                " even after we waited %(seconds)s seconds or %(attempts)s"
                " attempts.")

class VolumeNotdetach(V2vException):
    message = _("Volume %(volume_id)s did not finish being detached"
                " even after we waited %(seconds)s seconds or %(attempts)s"
                " attempts.")

class PortNotattach(V2vException):
    message = _("Port %(port_id)s did not finish being detached"
                " even after we waited %(seconds)s seconds or %(attempts)s"
                " attempts.")

class BirdieTransformNetConfigError(V2vException):
    message = _("Clone or migrate network config info error.")
    

class NoMigrateNetProvided(V2vException):
    message = _('No network provided for migrating server %(server_uuid)s')
    
class AvailabilityZoneNotFound(V2vException):
    message = _('the availability_zone of  server %(server_uuid)s not found')
    
##glance exception###
class InvalidImageRef(Invalid):
    message = _("Invalid image href %(image_href)s.")
    
class ImageNotFound(NotFound):
    message = _("Image %(image_id)s could not be found.")

class ImageNotAuthorized(V2vException):
    message = _("Not authorized for image %(image_id)s.")
    
class GlanceConnectionFailed(V2vException):
    message = _("Connection to glance host %(host)s:%(port)s failed: "
        "%(reason)s")


class PlanTypeNotSupported(V2vException):
    message = _("The plan type '%(type)s' is unsupported. \
                Type must be 'clone' or 'migrate'.")
class ResourceTypeNotFound(NotFound):
    message = _("SearchOptions has no attribution 'type' or the type is None.")
    
class ResourceTypeNotSupported(V2vException):
    message = _("The resource type '%(resource_type)s' is unsupported.")
    
class PlanNotFound(NotFound):
    message = _("The plan <%(plan_id)s> could not be found.")
   
class PlanDeleteError(V2vException):
    message = _("Plan <%(plan_id)s> delete failed.")
   
class PlanUpdateError(V2vException):
    message = _("Plan updated failed. The key not found or unsupported to update.")
    
class PlanResourcesUpdateError(V2vException):
    message = _("Plan resources updated failed.")

class PlanFileOperationError(V2vException):
    message = _("Read or write plan file failed.")

class ResourceNotFound(NotFound):
    message = _("%(resource_type)s resource <%(resource_id)s> could not be found.")

    
class ResourceExtractFailed(V2vException):
    message = _("Resource extract failed! %(reason)s")
    
class ResourceAttributesException(V2vException):
    message = _("%(resource_type)s resource has no attribute '%(attribute)s' "
                "or the value is None.")

class TemplateValidateFailed(V2vException):
    message = _("Template validate failed.")
 
 
class ServiceCatalogException(V2vException):
    """Raised when a requested service is not available in the
    ``ServiceCatalog`` returned by Keystone.
    """
    def __init__(self, service_name):
        message = 'Invalid service catalog service: %s' % service_name
        super(ServiceCatalogException, self).__init__(message)
        
class PlanDeployError(V2vException):
    msg_fmt = _("The plan %s(plan_id)s deploy failed")


    
class PlanNotFoundInDb(NotFound):
    message = _("Plan not found for id <%(id)s>.")
    
class InvalidID(Invalid): 
    message = _("Invalid ID received %(id)s.")
    
class DataExists(V2vException):
    code = 409
    message = _("data already exists.")
    
class PlanExists(DataExists):
    message = _("plan id <%(id)s> already exists in db.")
    
class IntegrityException(V2vException):
    code = 409
    message = _("%(msg)s.")
    
class PlanCreateFailed(V2vException):
    message = _("Unable to create plan")
    
class DownloadTemplateFailed(V2vException):
    message = _("Download the plan <%(id)s> failed.%(msg)s")  
    
class ExportTemplateFailed(V2vException): 
    message = _("export template of the plan <%(id)s> failed.%(msg)s") 
    
class PlanCloneFailed(V2vException):
    message = _("clone plan <%(id)s> failed.%(msg)s")
    
class PlanMigrateFailed(V2vException):
    message = _("migrate plan <%(id)s> failed.%(msg)s")
    
class TimeoutException(V2vException): 
    message = _("%(msg)s.")
    
class VolumeErrorException(V2vException):
    message = _("volume <%(id)s> status is error")
