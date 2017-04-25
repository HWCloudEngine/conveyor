import hashlib
import requests
import zlib

from FSSecurity import crypt as fs_crypt
from conveyor.conveyorheat.api.aws import ec2token as aws_ec2token
from conveyor.conveyorheat.api.aws import exception
from conveyor.conveyorheat.common.i18n import _
from conveyor.conveyorheat.common.i18n import _LE
from conveyor.conveyorheat.common.i18n import _LI
from oslo_log import log as logging
from oslo_serialization import jsonutils as json
from oslo_utils import timeutils

LOG = logging.getLogger(__name__)


TOKEN_EXPIRES_SECOND = 10 * 60


class TokenCacheError(Exception):
    def __str__(self):
        return 'Token cache error.'


class TokenExpired(Exception):
    def __init__(self, expires_at):
        self.expires_at = expires_at

    def __str__(self):
        return 'Token expired at: %s.' % self.expires_at


class TokenInvalid(Exception):
    def __init__(self, code, message):
        self.code = code
        self.message = message

    def __str__(self):
        return 'Token is invalid. Code: %s, Message: %s' % \
               (self.code, self.message)


class Token(object):
    def __init__(self, expired_at, token_id, tenant_id, tenant_name):
        self.expired_at = expired_at
        self.tenant_id = tenant_id
        self.tenant_name = tenant_name

        self.token_id = self._zip_and_encrypt(token_id)

    def _check_token_timestamp(self):
        expires_time = timeutils.parse_isotime(self.expired_at.rstrip('Z'))
        expires_time = timeutils.normalize_time(expires_time)
        if timeutils.is_soon(expires_time, TOKEN_EXPIRES_SECOND):
            raise TokenExpired(self.expired_at)

    def _zip_and_encrypt(self, token_id):
        try:
            zip_token_id = zlib.compress(token_id)
            encrypt_token_id = fs_crypt.encrypt(zip_token_id)
        except Exception:
            LOG.error('crypt and zip error.')
            raise TokenCacheError()

        return encrypt_token_id

    def _decrypt_and_unzip(self, encrypted_token_id):
        try:
            decrypted_token_id = fs_crypt.decrypt(encrypted_token_id)
            unzip_token_id = zlib.decompress(decrypted_token_id)
        except Exception:
            LOG.error('unzip and decrypt error.')
            raise TokenCacheError

        return unzip_token_id

    def validate_token(self):
        try:
            self._check_token_timestamp()
        except Exception:
            import traceback
            LOG.error('Valid token error. traceback: %s' %
                      traceback.format_exc())
            return False

        return True

    def to_dict(self):
        return {
            'token': {
                'id': self._decrypt_and_unzip(self.token_id),
                'project': {
                    'name': self.tenant_name,
                    'id': self.tenant_id
                }
            }
        }


class TokenCache(object):
    '''Cache ec2token in memory.

    - For security, token is encrypted.
    - For save memory space, token info will be compressed.
    '''

    def __init__(self):
        self.cached_tokens = {}

    def cached(self, signature):
        if (not signature or signature not in self.cached_tokens):
            LOG.info('Get cached ec2token failed because signature '
                     'is None or not in cache.')
            return None

        token = self.cached_tokens.get(signature)
        if not token or not token.validate_token():
            LOG.info('Get cached ec2token failed. ec2token '
                     'is not cached or invalid.')
            return None

        LOG.info('Get cached ec2token success.')
        try:
            return token.to_dict()
        except Exception:
            return None

    def add_cache(self, signature, response):
        LOG.info('Add ec2token into cached list.')
        try:
            result = response.json()
            self.cached_tokens.update({
                signature: Token(result['token']['expires_at'],
                                 response.headers['X-Subject-Token'],
                                 result['token']['project']['id'],
                                 result['token']['project']['name'])
            })
        except Exception as e:
            # record log and do nothing else
            LOG.error('Add ec2token into cached list error. '
                      'exception: %s' % str(e))

        # For save memory space, we will delete expired token in cache.
        self._delete_expired_cache()

    def _delete_expired_cache(self):
        LOG.debug('Delete expired ec2token from cache.')
        for sig, token in self.cached_tokens.items():
            if not token.validate_token():
                self.cached_tokens.pop(sig)


class EC2Token(aws_ec2token.EC2Token):
    '''Extend AWS ec2 token.

    In this class, we will save token, grouped by signature, in memory.
    Any signature was cached, we will use cached ec2token instead of getting
    token from keystone every time.
    '''

    cached_token = TokenCache()

    def _get_ec2_token(self, req, access, signature, auth_uri):
        if not access:
            if 'X-Auth-User' in req.headers:
                return self.application
            else:
                LOG.info(_LI("No AWSAccessKeyId/Authorization Credential"))
                raise exception.HeatMissingAuthenticationTokenError()

        LOG.info(_LI("AWS credentials found, checking against keystone."))

        if not auth_uri:
            LOG.error(_LE("Ec2Token authorization failed, no auth_uri "
                          "specified in config file"))
            raise exception.HeatInternalFailureError(_('Service '
                                                       'misconfigured'))

        # Make a copy of args for authentication and signature verification.
        auth_params = dict(req.params)
        # 'Signature' param Not part of authentication args
        auth_params.pop('Signature', None)

        # Authenticate the request.
        # AWS v4 authentication requires a hash of the body
        body_hash = hashlib.sha256(req.body).hexdigest()
        creds = {'ec2Credentials': {'access': access,
                                    'signature': signature,
                                    'host': req.host,
                                    'verb': req.method,
                                    'path': req.path,
                                    'params': auth_params,
                                    'headers': dict(req.headers),
                                    'body_hash': body_hash
                                    }}
        creds_json = json.dumps(creds)
        headers = {'Content-Type': 'application/json'}

        keystone_ec2_uri = self._conf_get_keystone_ec2_uri(auth_uri)
        LOG.info(_LI('Authenticating with %s'), keystone_ec2_uri)
        response = requests.post(keystone_ec2_uri, data=creds_json,
                                 headers=headers,
                                 verify=self.ssl_options['verify'],
                                 cert=self.ssl_options['cert'])
        return response

    def _authorize(self, req, auth_uri):
        # Read request signature and access id.
        # If we find X-Auth-User in the headers we ignore a key error
        # here so that we can use both authentication methods.
        # Returning here just means the user didn't supply AWS
        # authentication and we'll let the app try native keystone next.
        LOG.info(_LI("Checking AWS credentials.."))

        signature_raw = self._get_signature(req)
        if not signature_raw:
            if 'X-Auth-User' in req.headers:
                return self.application
            else:
                LOG.info(_LI("No AWS Signature found."))
                raise exception.HeatIncompleteSignatureError()

        signature = self._decrypt(signature_raw, 'heat_decrypt')

        # first check token in memory cache
        result = EC2Token.cached_token.cached(signature)
        cached_flag = True
        access = self._get_access(req)
        if not result:
            cached_flag = False
            # if no cached token or cached token is invalid,
            # get it from keytone
            response = self._get_ec2_token(req, access, signature, auth_uri)
            # cache token into cache
            EC2Token.cached_token.add_cache(signature, response)
            result = response.json()

        try:
            token_id = result['token']['id'] if cached_flag else \
                response.headers['X-Subject-Token']
            tenant = result['token']['project']['name']
            tenant_id = result['token']['project']['id']
            LOG.info(_LI("AWS authentication successful."))
        except (AttributeError, KeyError):
            LOG.info(_LI("AWS authentication failure."))
            # Try to extract the reason for failure so we can return the
            # appropriate AWS error via raising an exception
            try:
                reason = result['error']['message']
            except KeyError:
                reason = None

            if reason == "EC2 access key not found.":
                raise exception.HeatInvalidClientTokenIdError()
            elif reason == "EC2 signature not supplied.":
                raise exception.HeatSignatureError()
            else:
                raise exception.HeatAccessDeniedError()

        # Authenticated!
        ec2_creds = {'ec2Credentials': {'access': access,
                                        'signature': signature}}
        req.headers['X-Auth-EC2-Creds'] = json.dumps(ec2_creds)
        req.headers['X-Auth-Token'] = token_id
        req.headers['X-Tenant-Name'] = tenant
        req.headers['X-Tenant-Id'] = tenant_id
        req.headers['X-Auth-URL'] = auth_uri

        roles = [role['name']
                 for role in result['token'].get('roles', [])]
        req.headers['X-Roles'] = ','.join(roles)

        return self.application


def EC2Token_filter_factory(global_conf, **local_conf):
    '''Factory method for paste.deploy'''

    conf = global_conf.copy()
    conf.update(local_conf)

    def filter(app):
        return EC2Token(app, conf)

    return filter
