import re
import sys
from cStringIO import StringIO
from collections import namedtuple
from urlparse import urljoin, urlparse, urlunparse

from pulp.common.compat import check_builtin


if sys.version_info < (2, 7):
    from xml.etree import ElementTree as ET
else:
    from xml.etree import cElementTree as ET


# required for converting an element to raw XML
STRIP_NS_RE = re.compile('{.*?}')
Namespace = namedtuple('Namespace', ['name', 'uri'])


def element_to_raw_xml(element, namespaces_to_register=None, default_namespace_uri=None):
    """
    Convert an Element to a raw XML block. Namespaces are preserved on element
    tags, but any namespace declaration on the root element will be removed.
    This function is intended to be used in a case where multiple XML string
    snippets will be concatenated into a valid XML document later. This function
    will not necessarily return a valid XML document.

    :param element:                 XML element that should be output as an XML string
    :type  element:                 xml.etree.ElementTree.Element
    :param namespaces_to_register:  collection of Namespace instances that should
                                    be registered while converting to a string.
                                    Any "xmlns" declarations for a prefix that
                                    appears in this collection will be removed.
    :type  namespaces_to_register:  list or tuple
    :param default_namespace_uri:   URI of the default namespace, if any. This
                                    will be stripped from the tag of the given
                                    element and any of its descendants.
    :type  default_namespace_uri:   basestring

    :return:    XML as a string
    :rtype:     str
    """
    namespaces_to_register = namespaces_to_register or tuple()
    for namespace in namespaces_to_register:
        if not isinstance(namespace, Namespace):
            raise TypeError('"namespaces" must be an iterable of Namespace instances')
        register_namespace(namespace.name, namespace.uri)

    if default_namespace_uri:
        strip_ns(element, default_namespace_uri)

    tree = ET.ElementTree(element)
    io = StringIO()
    tree.write(io, encoding='utf-8')
    ret = io.getvalue()

    for namespace in namespaces_to_register:
        # in python 2.7, these show up only on the root element. in 2.6, these
        # show up on each element that uses the prefix.
        ret = re.sub(' *xmlns:%s="%s" *' % (namespace.name, namespace.uri), ' ', ret)
    return ret


@check_builtin(ET)
def register_namespace(prefix, uri):
    """
    Adapted from xml.etree.ElementTree.register_namespace as implemented
    in Python 2.7.

    This implementation makes no attempt to remove other namespaces. It appears
    that there is a race condition in the python 2.7 stdlib pure python
    implementation. For our purposes, we don't need to be concerned about
    unregistering a namespace or URI, so we can let them remain unless
    overwritten.

    :param prefix:  namespace prefix
    :param uri:     namespace URI. Tags and attributes in this namespace will be
                    serialized with the given prefix, if at all possible.
    """
    ET._namespace_map[uri] = prefix


def strip_ns(element, uri=None):
    """
    Given an Element object, recursively strip the namespace info from its tag
    and all of its children. If a URI is specified, only that URI will be removed
    from the tag.

    :param element: the element whose tag namespace should be modified
    :type  element: xml.etree.ElementTree.Element
    :param uri:     The URI of a namespace that should be stripped. If specified,
                    only this URI will be removed, and all others will be left
                    alone.
    :type  uri:     basestring
    """
    if uri is None:
        element.tag = re.sub(STRIP_NS_RE, '', element.tag)
    else:
        element.tag = element.tag.replace('{%s}' % uri, '')
    for child in list(element):
        strip_ns(child, uri)


class RepoURLModifier(object):
    """
    Repository URL Modifier
    """
    def __init__(self, query_auth_token=None):
        """
        Initialize the URL modifier with defaults, populated from optional keyword arguments

        :param query_auth_token: If specified, will become the query string in modified URLs
                                 unless overridden when this instance is called
        :type query_auth_token: str or None

        """
        self._query_auth_token = query_auth_token

    def __call__(self, url, path_append=None, ensure_trailing_slash=None, query_auth_token=None):
        """
        Modify a URL based on the keys in the url modify conf. URL modification takes place in the
        order of arguments, so (for example) ensure_trailing_slash will add a trailing slash, if
        needed, *after* appending a path specified with path_append.

        :param url: URL to modify
        :type url: str
        :param path_append: path fragment to append to the end of the given URL's path
        :type path_append: str or None
        :param ensure_trailing_slash: if True, ensure that the URL path ends with a trailing slash
        :type ensure_trailing_slash: bool or None
        :param query_auth_token: If specified, will become the query string in the modified URL
        :type query_auth_token: str or None

        :return:     The modified URL
        :rtype:      str

        """
        query_auth_token = query_auth_token or self._query_auth_token

        scheme, netloc, path, params, query, fragment = urlparse(url)

        if path_append:
            if not path.endswith('/'):
                path += '/'
            path = urljoin(path, path_append)

        if ensure_trailing_slash:
            if not path.endswith('/'):
                path += '/'

        if query_auth_token:
            query = query_auth_token

        url = urlunparse(
            (scheme, netloc, path, params, query, fragment)
        )
        return url
