texpect-cisco
==
Interact with Cisco devices using [Twisted](http://twistedmatrix.com/).

##Description

TExpect-Cisco extends [TExpect](http://github.com/shylent/texpect) and attempts to provide an easy way to run commands against the device.

Since TExpect-Cisco utilizes Twisted's asynchronous I/O, it doesn't really matter if you are talking to one device or to a hundred of them, - no special handling (threads, manual multiplexing, etc) has to be done.

All the device-specific configuration (credentials, address/port, prompts, typical commands) is represented as a dictionary, that is expected to have a set of well-known keys (see documentation for the `Device` class). Reasonable default values are provided.

##Example

Do not be alarmed by the seemingly large amount of boilerplate code, it should be
trivial to neatly abstract it all away, should you need to.

    import sys
    import re
    from twisted.internet.protocol import ClientCreator
    from twisted.internet import reactor
    from twisted.python import log
    from texpect_cisco.cisco import Cisco, device_defaults
    from texpect_cisco.conf import process_hooks
    
    # Define a couple of 'hook' functions here, so that we don't need
    # to hardcode the prompt regular expressions
    
    def prompt_from_device_id(device):
        """Construct the prompt regex using the device id"""
        return re.compile('%s>$' % device['id'], re.IGNORECASE)
    
    def enabled_prompt_from_device_id(device):
        """Construct the enabled prompt regex using the device id"""
        return re.compile(r'%s\s*?(\(config(-\S+?)?\))?#$' %
                          device['id'], re.IGNORECASE)
    
    hooks = (
        ('prompt', prompt_from_device_id),
        ('enabled_prompt', enabled_prompt_from_device_id)
    )
    
    def do_interact(inst):
        """Talk to the device. Retrieve and log the current configuration"""
        d = inst.login()
        d.addCallback(lambda ign: inst.enable())
        d.addCallback(lambda ign: inst.run_command('show running-config'))
        d.addCallback(lambda output: log.msg("Configuration for device %s:\n%s" %
                                             (inst.device['id'], output)))
        d.addCallback(lamgda ign: inst.exit())
        return d
    
   
    def main():
        device = {'id':'switch', 'address':'10.0.0.5',
                  'password':'p4ssw0rD', 'enable_password':'s3kr1t'}
        # Build the configuration: first apply defaults
        for k, v in device_defaults.iteritems():
            device.setdefault(k, v)
        # Then run the hooks to fill the rest of the keys based on what
        # we already have
        device = process_hooks(hooks, device)
        
        cc = ClientCreator(reactor, Cisco, device)
        conn = cc.connectTCP(device['address'], device['port'],
                             device['connect_timeout'])
        conn.addCallback(do_interact)
        conn.addErrback(log.err)
        conn.addBoth(lambda ign: reactor.stop())
        
        reactor.run()
        
    if __name__ == '__main__':
        log.startLogging(sys.stdout)
        main()

##Dependencies
[TExpect](http://github.com/shylent/texpect) and, consequently, [Twisted](http://twistedmatrix.com/).


##Documentation
The API is fully documented using [epydoc](http://epydoc.sourceforge.net/). In fact, there is probably more documentation here, than code :)

I would advise skipping the underscore-prefixed methods when building the documentation.
Those methods are not to be used directly and have large and repetitive signatures,
that no-one should be interested in.

##Tests
A test suite is included, but it is impossible to account for all the potential subtle differences between IOS versions. Luckily, most of the time such problems can be fixed by providing the correct configuration, rather than altering the actual logic.

##Future
At the moment, TExpect-Cisco only supports telnet as a medium, because so does [TExpect](http://github.com/shylent/texpect). Once I properly abstract the application-level protocol away, ssh will also become an option.

I will probably implement a way to run multiple commands as a batch in the following fashion:

    inst.run_batch("""
        !login
        !enable
        do_something
        do_something_else
    """)

that will fire with a list of strings with an item for each command that was run.

Paging mode (you know, when you get only a portion of the output and are supposed to
press spacebar to get more) is not supported, because it is possible to just turn it off
immediately after logging in. If I discover that it is neccessary to be able to work
in paging mode, I will implement it, sure.
 
