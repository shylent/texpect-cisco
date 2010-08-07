'''
@author: shylent
'''
from twisted.python import log
from texpect_cisco.cisco import TExpectCiscoError


class ImproperlyConfigured(TExpectCiscoError):
    """An error has occured while processing the configuration"""


def process_hooks(hooks, device, force=False, strict=True):
    """Populate the L{device} dictionary, using the attribute-to-callable
    mapping provided in L{hooks} iterable.
    
    @param hooks: An iterable, that yields 2-tuples, that represents a 'hook'.
    The items of the tuples are:
        - the key in the L{device} dictionary, that will be populated by the
        return value of this hook
        - a callable, that will be called with the L{device} dictionary
        as a sole argument. This callable is expected to do one of two things:
            - return a computed value, using the contents of the provided L{device}
            dictionary, that will then be assigned to the appropriate key
            - raise L{ImproperlyConfigured} if it is impossible to derive the
            neccessary value from the contents of the passed L{device} dictionary
    @type hooks: C{iterable}
    @param device: A dictionary, that represents a 'device'.
    @type device: C{dict}
    
    @param force: If C{True}, the hook will be run for a given key in the L{device}
    dictionary, even if that key already exists (default: C{False}).
    @type force: C{bool}
    
    @param strict: If C{False}, any exception raised by the hook will be wrapped in
    an L{ImproperlyConfigured} exception and reraised (thereby terminating the processing).
    If C{True}, exceptions, raised by hooks are suppressed and logged and the processing
    is not terminated (Default: C{True}).
    @type strict: C{bool}
    
    """
    for attr_name, hook in hooks:
        if attr_name in device and not force:
            continue
        try:
            device[attr_name] = hook(device)
        except ImproperlyConfigured, e:
            log.err(e, "An error has occured while processing configuration")
            if strict:
                raise
        except Exception, e:
            exc = ImproperlyConfigured("An exception was raised in the hook: %s" % e)
            log.err(exc)
            if strict:
                raise exc
    return device