'''
@author: shylent
'''
from twisted.trial import unittest
from texpect_cisco.cisco import Cisco, UnexpectedResultError, Disconnected,\
    NotConnected, LoginFailed
import re
from twisted.internet.protocol import Protocol, ServerFactory, ClientCreator

device = {'id':'device', 'address':'localhost', 'port':2300, 'command_timeout':1,
          'password_prompt':'Password:', 'password':'p4ssw0rD',
          'prompt':'device>'}

class CiscoTestCase(unittest.TestCase):
    
    def test_no_id(self):
        device = {}
        self.failUnless(Cisco(device))
        
class OneShotServer(Protocol):

    def connectionMade(self):
        self.transport.write(self.factory.greeting)
        
    def dataReceived(self, data):
        for byte in data:
            self.transport.write(byte)
        self.transport.write(self.factory.response)
        if self.factory._disconnect:
            self.loseConnection(self)
    
    def loseConnection(self, reason):
        self.transport.loseConnection()

class CommandTestCase(unittest.TestCase):
    
    def setUp(self):
        self.server_factory = ServerFactory()
        self.server_factory.protocol = OneShotServer
            
    def go(self, greeting='', response='', disconnect=False):
        from twisted.internet import reactor
        self.server_factory.response = response
        self.server_factory.greeting = greeting
        self.server_factory._disconnect = disconnect
        self.port = reactor.listenTCP(2300, self.server_factory)
        cc = ClientCreator(reactor, Cisco, device)
        
        self.addCleanup(self.port.stopListening)
        
        return cc.connectTCP('localhost', 2300)
    
    def test_command(self):
        def cb(inst):
            self.addCleanup(inst.transport.loseConnection)
            d = inst.run_command('foo', prompt='prompt>')
            d.addCallback(lambda res: self.assertEqual(res, 'Some command output'))
            return d
        d = self.go(response='Some command output\n'
                    'prompt>')
        d.addCallback(cb)
        return d
    
    def test_command_invalid_prompt(self):
        def cb(inst):
            self.addCleanup(inst.transport.loseConnection)
            d = inst.run_command('foo', prompt='prompt#')
            self.failUnlessFailure(d, UnexpectedResultError)
            return d
        d = self.go(response='Some command output\n'
                    'prompt>')
        d.addCallback(cb)
        return d
    
    def test_command_unexpected_disconnection(self):
        def cb(inst):
            self.addCleanup(inst.transport.loseConnection)
            d = inst.run_command('foo', prompt='prompt>')
            #d.addCallback(lambda res: self.assertEqual(res, 'Some command output'))
            self.failUnlessFailure(d, Disconnected)
            return d
        d = self.go(disconnect=True)
        d.addCallback(cb)
        return d
    
    def test_command_expected_disconnection(self):
        def cb(inst):
            d = inst.run_command('foo', strip_command=False, prompt="I don't matter", _may_disconnect=True)
            d.addCallback(lambda res: self.assertEqual(res, 'foo\nI am about to disconnect you'))
            d.addCallback(lambda ign: self.failUnless(inst.eof))
            return d
        d = self.go(response='I am about to disconnect you', disconnect=True)
        d.addCallback(cb)
        return d
    
    def test_command_after_disconnection(self):
        def cb(inst):
            d = inst.run_command('foo', strip_command=False, prompt="I don't matter", _may_disconnect=True)
            d.addCallback(lambda res: self.assertEqual(res, 'foo\nI am about to disconnect you'))
            d.addCallback(lambda ign: self.failUnless(inst.eof))
            d.addCallback(lambda ign: inst.run_command('foo'))
            self.failUnlessFailure(d, NotConnected)
            return d
        d = self.go(response='I am about to disconnect you', disconnect=True)
        d.addCallback(cb)
        return d
    
    def test_command_disconnected(self):
        c = Cisco(device)
        c.eof = True
        d = c.run_command('something')
        self.failUnlessFailure(d, NotConnected)
        
    def test_exit(self):
        def cb(inst):
            d = inst.exit(prompt="prompt>")
            d.addCallback(lambda res: self.assertEqual(res, ''))
            d.addCallback(lambda ign: self.failUnless(inst.eof))
            return d
        d = self.go(response='', disconnect=True)
        d.addCallback(cb)
        return d
    
    def test_exit_no_disconnection(self):
        def cb(inst):
            self.addCleanup(inst.transport.loseConnection)
            d = inst.exit(prompt="prompt>")
            d.addCallback(lambda res: self.assertEqual(res, ''))
            d.addCallback(lambda ign: self.failIf(inst.eof))
            return d
        d = self.go(response='prompt>', disconnect=False)
        d.addCallback(cb)
        return d
    
    def test_login(self):
        def cb(inst):
            self.addCleanup(inst.transport.loseConnection)
            d = inst.login()
            return d
        d = self.go(greeting='\nPassword:', response='device>')
        d.addCallback(cb)
        return d
        
    def test_login_failed(self):
        def cb(inst):
            self.addCleanup(inst.transport.loseConnection)
            d = inst.login()
            self.failUnlessFailure(d, LoginFailed)
            return d
        d = self.go(greeting='\nPassword:', response='Password:')
        d.addCallback(cb)
        return d

    
class CommandResultTestCase(unittest.TestCase):
    
    def setUp(self):
        self.c = Cisco(device)
    
    def test_return_as_is(self):
        self.assertEqual(self.c._process_command_result((0, None, '\ta line\r\nanother line\n '), 'show run',
                                       strip_command=False, strip_prompt=False, process_errors=False), 'a line\r\nanother line')
    
    def test_strip_prompt(self):
        prompt = re.compile('bar>$')
        self.c._buf = '\ta line\r\nanother line\n bar>'
        result = self.c._process_buffer([prompt])
        self.assertEqual(self.c._process_command_result(result, 'show run', strip_command=False, strip_prompt=True, process_errors=False),
                         'a line\r\nanother line')

    def test_strip_command(self):
        prompt = re.compile('bar>$')
        self.c._buf = 'show run\ta line\r\nanother line\n bar>'
        result = self.c._process_buffer([prompt])
        self.assertEqual(self.c._process_command_result(result, 'show run', strip_command=True, strip_prompt=False, process_errors=False),
                         'a line\r\nanother line\n bar>')
    
    def test_strip_command_and_prompt(self):
        prompt = re.compile('bar>$')
        self.c._buf = 'show run\ta line\r\nanother line\n bar>'
        result = self.c._process_buffer([prompt])
        self.assertEqual(self.c._process_command_result(result, 'show run', strip_command=True, strip_prompt=True, process_errors=False),
                         'a line\r\nanother line')
    
class DeviceErrorsTestCase(unittest.TestCase):
    
    def setUp(self):
        self.c = Cisco(device)
    
    def test_no_error(self):
        data = """show running-config
Building configuration..."""
        self.failUnlessIdentical(self.c._process_device_errors(data), None)
    
    def test_empty(self):
        self.failUnlessIdentical(self.c._process_device_errors(''), None)
    
    def test_error_with_marker(self):
        data = """foo bar
        ^
% Invalid input detected at '^' marker.

switch>"""
        self.assertEqual(self.c._process_device_errors(data), (['        ^', "% Invalid input detected at '^' marker.", ''],
                                                               ['foo bar', 'switch>']))
    
    def test_error_with_marker_incomplete_results(self):
        data = r"""foo bar
    ^
% Something really terrible at '^' marker"""
        self.assertEqual(self.c._process_device_errors(data), (['    ^', "% Something really terrible at '^' marker"],
                                                               ['foo bar']))
    
    def test_error_no_marker(self):
        data = """$bad input
% Unknown command or computer name, or unable to find computer address
rest of data"""
        self.assertEqual(self.c._process_device_errors(data),
                         (['% Unknown command or computer name, or unable to find computer address'],
                          ['$bad input', 'rest of data']))
    
    def test_error_no_marker_incomplete_results_1(self):
        data = """$bad input
% Unknown command or computer name, or unable to find computer address"""
        self.assertEqual(self.c._process_device_errors(data),
                         (['% Unknown command or computer name, or unable to find computer address'],
                          ['$bad input']))
    def test_error_no_marker_incomplete_results_2(self):    
        data = """% Unknown command or computer name, or unable to find computer address"""
        self.assertEqual(self.c._process_device_errors(data),
                         (['% Unknown command or computer name, or unable to find computer address'],
                          []))
    def test_error_no_marker_incomplete_results_3(self):        
        data = """% Unknown command or computer name, or unable to find computer address
rest of the output"""
        self.assertEqual(self.c._process_device_errors(data),
                         (['% Unknown command or computer name, or unable to find computer address'],
                          ['rest of the output']))