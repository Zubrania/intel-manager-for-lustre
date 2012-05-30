#
# ========================================================
# Copyright (c) 2012 Whamcloud, Inc.  All rights reserved.
# ========================================================


import json

from chroma_cli.exceptions import InvalidApiResource, UnsupportedFormat, NotFound, TooManyMatches, BadRequest, InternalError, UnauthorizedRequest, AuthenticationFailure


class JsonSerializer(object):
    """
    Simple JSON serializer which implements the important parts of TastyPie's Serializer API.
    """
    formats = ["json"]
    content_types = {
            'json': "application/json"
    }
    datetime_formatting = "iso-8601"

    def __init__(self, formats=None, content_types=None, datetime_formatting=None):
        self.supported_formats = []

        for format in self.formats:
            self.supported_formats.append(self.content_types[format])

    def serialize(self, bundle, format="application/json", options={}):
        if format != "application/json":
            raise UnsupportedFormat("Can't serialize '%s', sorry." % format)

        return json.dumps(bundle, sort_keys=True)

    def deserialize(self, content, format='application/json'):
        if format != "application/json":
            raise UnsupportedFormat("Can't deserialize '%s', sorry." % format)

        return json.loads(content)


class ChromaSessionClient(object):
    def __init__(self):
        self.is_authenticated = False
        self.api_uri = "http://localhost/api"

        session_headers = {'Accept': "application/json",
                           'Content-Type': "application/json"}
        import requests
        self.__session = requests.session(headers=session_headers)

    def __getattr__(self, method):
        return getattr(self.__session, method)

    @property
    def session_uri(self):
        from urlparse import urljoin
        return urljoin(self.api_uri, "session/")

    @property
    def session(self):
        return self.__session

    def start_session(self):
        r = self.get(self.session_uri)
        if not 200 <= r.status_code < 300:
            raise RuntimeError("No session (status: %s, text: %s)" %
                               (r.status_code, r.content))

        self.session.headers['X-CSRFToken'] = r.cookies['csrftoken']
        self.session.cookies['csrftoken'] = r.cookies['csrftoken']
        self.session.cookies['sessionid'] = r.cookies['sessionid']

    def login(self, **credentials):
        if not self.is_authenticated:
            if 'sessionid' not in self.session.cookies:
                self.start_session()

            r = self.post(self.session_uri, data=json.dumps(credentials))
            if not 200 <= r.status_code < 300:
                raise AuthenticationFailure()
            else:
                self.is_authenticated = True

        return self.is_authenticated

    def logout(self):
        if self.is_authenticated:
            self.delete(self.session_uri)
            self.is_authenticated = False


class ApiClient(object):
    def __init__(self, serializer=None):
        self.client = ChromaSessionClient()
        self.serializer = serializer

        if not self.serializer:
            self.serializer = JsonSerializer()

    def get_content_type(self, short_format):
        return self.serializer.content_types.get(short_format,
                                                 'application/json')

    def get(self, uri, format="json", data=None, authentication=None, **kwargs):
        content_type = self.get_content_type(format)
        headers = {'Content-Type': content_type, 'Accept': content_type}

        if authentication and not self.client.is_authenticated:
            self.client.login(**authentication)

        return self.client.get(uri, headers=headers, params=data)

    def post(self, uri, format="json", data=None, authentication=None, **kwargs):
        content_type = self.get_content_type(format)
        headers = {'Content-Type': content_type, 'Accept': content_type}

        if authentication and not self.client.is_authenticated:
            self.client.login(**authentication)

        return self.client.post(uri, headers=headers,
                                data=self.serializer.serialize(data))

    def put(self, uri, format="json", data=None, authentication=None, **kwargs):
        content_type = self.get_content_type(format)
        headers = {'Content-Type': content_type, 'Accept': content_type}

        if authentication and not self.client.is_authenticated:
            self.client.login(**authentication)

        return self.client.put(uri, headers=headers,
                               data=self.serializer.serialize(data))

    def delete(self, uri, format="json", data=None, authentication=None, **kwargs):
        content_type = self.get_content_type(format)
        headers = {'Content-Type': content_type, 'Accept': content_type}

        if authentication and not self.client.is_authenticated:
            self.client.login(**authentication)

        return self.client.delete(uri, headers=headers, params=data)


class ApiHandle(object):
    # By default, we want to use our own ApiClient class.  This
    # provides a handle for the test framework to inject its own
    # ApiClient which uses Django's Client under the hood.
    ApiClient = ApiClient

    def __init__(self, api_uri=None, authentication=None):
        self.__schema = None
        self.base_url = api_uri
        if not self.base_url:
            self.base_url = "http://localhost/api"
        self.authentication = authentication
        self.endpoints = ApiEndpointGenerator(self)
        self.serializer = JsonSerializer()
        self.api_client = self.ApiClient()
        # Ugh. Least-worst option, I think.
        self.api_client.client.api_uri = self.base_url

    @property
    def schema(self):
        if not self.__schema:
            self.__schema = self.send_and_decode("get", "")

        return self.__schema

    def data_or_text(self, content):
        try:
            return self.serializer.deserialize(content)
        except ValueError:
            return content

    def send_and_decode(self, method_name, relative_url, data=None):
        from urlparse import urljoin
        full_url = urljoin(self.base_url, relative_url)

        method = getattr(self.api_client, method_name)
        r = method(full_url, data=data)
        if r.status_code == 401:
            # Try logging in and retry the request
            self.api_client.client.login(**self.authentication)
            r = method(full_url, data=data)

        if 200 <= r.status_code < 304:
            return self.data_or_text(r.content)
        elif r.status_code == 400:
            raise BadRequest(self.data_or_text(r.content))
        elif r.status_code == 401:
            raise UnauthorizedRequest(self.data_or_text(r.content))
        elif r.status_code == 404:
            decoded = self.data_or_text(r.content)
            try:
                raise NotFound(decoded['traceback'])
            except KeyError:
                raise NotFound("Not found (%s)" % decoded)
        elif r.status_code == 500:
            decoded = self.data_or_text(r.content)
            try:
                raise InternalError(decoded['traceback'])
            except KeyError:
                raise InternalError("Unknown server error: %s" % decoded)
        else:
            raise RuntimeError("status: %s, text: %s" % (r.status_code,
                                                         r.content))


class ApiEndpointGenerator(object):
    """
    Emulate a dict of resource -> endpoint pairs, but only as much as
    necessary.

    Doesn't implement the full dict API, so beware.
    """
    def __init__(self, api):
        self.api = api
        self.endpoints = {}

    def keys(self):
        return self.api.schema.keys()

    def _load_endpoints(self):
        for resource in self.keys():
            if resource not in self.endpoints:
                self.endpoints[resource] = ApiEndpoint(self.api, resource)

    def values(self):
        self._load_endpoints()
        return self.endpoints.values()

    def items(self):
        self._load_endpoints()
        return self.endpoints.items()

    def __getitem__(self, resource_name):
        if resource_name not in self.endpoints:
            if resource_name in self.api.schema:
                self.endpoints[resource_name] = ApiEndpoint(self.api,
                                                            resource_name)
            else:
                raise InvalidApiResource(resource_name)

        return self.endpoints[resource_name]


class ApiEndpoint(object):
    def __init__(self, handle, name):
        self.__schema = None
        self.api_handle = handle
        self.name = name

        import chroma_cli.api_resource
        try:
            self.resource_klass = getattr(chroma_cli.api_resource,
                                          self.name.capitalize())
        except AttributeError:
            # generic fallback
            self.resource_klass = chroma_cli.api_resource.ApiResource

    @property
    def schema(self):
        if not self.__schema:
            schema_url = self.api_handle.schema[self.name]['schema']
            self.__schema = self.api_handle.send_and_decode("get", schema_url)

        return self.__schema

    @property
    def url(self):
        return self.api_handle.schema[self.name]['list_endpoint']

    def resolve_id(self, query):
        try:
            # Slight hack here -- relies on the "name" field usually being
            # first in a reverse-sort in order to optimize for the most
            # common query.
            for field, expressions in (
                    sorted(self.schema['filtering'].iteritems(),
                           key=lambda x: x[0], reverse=True)):
                for expression in expressions:
                    filter = "%s__%s" % (field, expression)

                    try:
                        candidates = self.list(**{filter: query})
                    except BadRequest:
                        continue

                    if len(candidates) > 1:
                        raise TooManyMatches("The query %s/%s matches more than one resource: %s" % (self.name, query, candidates))

                    try:
                        if query in candidates[0][field]:
                            return candidates[0]['id']
                    except IndexError:
                        continue
        except KeyError:
            # No filtering possible?
            pass

        raise NotFound("Unable to resolve id for %s/%s" % (self.name, query))

    def get_decoded(self, url=None, **data):
        if not url:
            url = self.url
        return self.api_handle.send_and_decode("get", url, data=data)

    def list(self, **data):
        resources = []
        try:
            for object in self.get_decoded(**data)['objects']:
                resources.append(self.resource_klass(**object))
        except ValueError:
            pass
        return resources

    def show(self, subject):
        id = self.resolve_id(subject)
        from urlparse import urljoin
        object = self.get_decoded(url=urljoin(self.url, "%s/" % id))
        return self.resource_klass(**object)

    def create(self, **data):
        return self.api_handle.send_and_decode("post", self.url, data=data)
