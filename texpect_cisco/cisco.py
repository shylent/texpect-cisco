'''
@author: shylent
'''
from twisted.python.failure import Failure
from twisted.python import log
from twisted.internet.defer import fail
from texpect import TExpect, RequestFailed, RequestTimeout,\
    RequestInterruptedByConnectionLoss

class Device(dict):
    """A mapping, that represents a 'device'.
    List of keys, that are currently used by the API:
        - B{id}: the unique identifier of the device in the organization
        - B{address}: domain name or ip address, that can be used to connect to the
        device
        - B{port}: port, to which to connect
        - B{connect_timeout}: TCP connection timeout
        - B{command_timeout}: number of seconds to wait for the command to complete,
        before considering it a failure
        - B{prompt}: the unprivileged prompt, in the form of a compiled regular
        expression or a string
        - B{enabled_prompt}: an experssion, that is supposed to match any kind of
        privileged prompt (C{'switch#'}, C{'switch(config-XXX)#'} and so on)
        - B{password_prompt}: the password prompt (the one, that you usually see
        upon establishing the connection)
        - B{password}: password, that is used to log in to the device
        - B{enable_command}: command, that is used to enter the privileged EXEC mode
        (normally 'enable')
        - B{enable_password_prompt}: prompt for the enable password
        - B{enable_password}: the password, that is used to enter the privileged
        EXEC mode
        - B{disable_paging}: whether or not should an attempt be made to disable
        paging
        - B{disable_paging_command}: the command, that should be used to disable
        paging on this device
        - B{debug}: whether or not debug mode is enabled. Enabling it should result in
        lots more stuff in the log, also the internal buffer is kept forever so
        that it is easier to examine the flow of events
        
        @note: Cisco commands that are stored should not include the trailing newline
        (see L{Cisco.run_command})
        
        Obviously, you don't need to provide all of these by hand, since it is
        easy to provide reasonable defaults for most of the options. Furthermore,
        if it is possible to derive certain options from other options or their
        combination, L{process_hooks<texpect_cisco.conf.process_hooks>}
        should be used to automate the process.
         
    """

device_defaults = Device({
    'disable_paging':True,
    'disable_paging_command':'terminal length 0',
    'port':23,
    'connect_timeout':5,
    'command_timeout':3,
    'password_prompt':'[Pp]assword:\s+$',
    'enable_password_prompt':'[Pp]assword:\s+$',
    'enable_command':'enable'
})


class TExpectCiscoError(Exception):
    """Base exception class for this package
        
    @ivar msg: An error message
    @type msg: C{str}
    
    @ivar command: The command, that has led to this error
    @type command: C{str}
    
    @ivar data: The data, that was collected
    @type data: C{str}
        
    """
    def __init__(self, msg='An error is reported by the device', command=None, data=None):
        """
        @param msg: An error message. Default: 'An error is reported by the device'.
        @type msg: C{str}
        
        @param command: The command, that has led to this error. Default: C{None}
        @type command: C{str}
        
        @param data: The data, that was collected. Default: C{None}
        @type data: C{str}
        
        """
        self.msg = msg
        self.command = command
        self.data = data
        super(TExpectCiscoError, self).__init__(self.msg)

class UnexpectedResultError(TExpectCiscoError):
    """Used when the device didn't do something, that we expected it to do,
    for example, produced a prompt, that doesn't match the prompt we are expecting
    and so on.
    
    """

class CiscoCommandError(TExpectCiscoError):
    """Used when the command was executed, but the device produced an error (usually a syntax error)
    and the error was processed successfully.
    
    @ivar msg: An error message
    @type msg: C{str}
    
    @ivar command: The command, that has led to this error
    @type command: C{str}
    
    @ivar data: The data, that was collected
    @type data: C{str}
    
    @ivar error: The error, as it was extracted from the command output
    @type error: C{str}
    
    """
    
    def __init__(self, msg='An error is reported by the device', command=None, data=None, error=None):
        """
        @param msg: An error message. Default: 'An error is reported by the device'.
        @type msg: C{str}
        
        @param command: The command, that has led to this error. Default: C{None}
        @type command: C{str}
        
        @param data: The data, that was collected. Default: C{None}
        @type data: C{str}
        
        @param error: The error, as it was extracted from the command output
        @type error: C{str}
        
        """
        super(CiscoCommandError, self).__init__(msg, command, data)
        self.error = error
    
    def __str__(self):
        return '\n'.join([TExpectCiscoError.__str__(self), self.error])

class Disconnected(TExpectCiscoError):
    """A command unexpectedly resulted in connection loss"""

class LoginFailed(TExpectCiscoError):
    """Used when the login attempt was made, but failed. The most common source
    of this is the password being invalid.
    
    """

class EnableFailed(TExpectCiscoError):
    """Used when an attempt was made to enter the privileged EXEC mode, but failed."""

class NotConnected(TExpectCiscoError):
    """An attempt was made to run a command, but we are not connected to the device anymore"""


class Cisco(TExpect):
    """

    @ivar device: A L{Device} instance, that represents the device,
    we are talking to
    @type device: L{Device} (C{dict}) 
        
    @ivar enabled: Whether or not we are in privileged EXEC mode at the moment
    @type enabled: C{bool}
    
    """
    
    def __init__(self, device, command_timeout=None, debug=False):
        """
        
        @param device: A L{Device} instance, that will be used for this session
        @type device: L{Device}
        
        @param command_timeout: Override the 'command_timeout' provided in the
        C{Device} instance. Default: C{None}
        @type command_timeout: C{int}
        
        @param debug: Override the 'debug' value provided in the C{Device} instance.
        Default: C{False}
        @type debug: C{bool}
            
        """
        self.device = device
        self.enabled = False
        self.debug = self.device.get('debug', debug)
        if command_timeout is not None:
            timeout = command_timeout
        else:
            timeout = device.get('command_timeout', None)
        TExpect.__init__(self, timeout=timeout, debug=debug)
    
    def connectionMade(self):
        """Do something, when the connection is established. Currently does nothing
        so it is neccessary to login explicitly.
        
        """
        
    def read_to_prompt(self, prompt=None, timeout=None):
        """Read all data up to and including the prompt. The prompt, that is used
        depends on whether or not the prompt argument is provided and on the mode
        the session is in at the moment (privileged/non-privileged)
        
        @param prompt: Override the instance-default prompt. Default: C{None}.
        If left unspecified, requires 'prompt' (or 'enabled_prompt' if we are in
        privileged EXEC mode) key to be populated in the L{device} dictionary.
        @type prompt: C{str} or C{SRE_Pattern}
        
        @param timeout: Override the instance-default command timeout. Default: C{None}.
        @type timeout: C{int}
        
        @return: A L{Deferred}, that will be fired with the output up to and including
        the prompt. An errback may be called (see L{ReadUntil<texpect.TExpect.read_until>}).
        @rtype: L{Deferred}
        
        @note: There should be no real need to use this method directly. L{run_command}
        already attempts to read to the appropriate prompt to find the end of
        command output.
        
        """
        if timeout is None:
            timeout = self.timeout
        if prompt is None:
            if self.enabled:
                prompt = self.device['enabled_prompt']
            else:
                prompt = self.device['prompt']
        return self.read_until(prompt, timeout=timeout)
    
    def login(self):
        """Attempt to log in using the information in L{device} dictionary.
        
        Requires the C{'password'} and C{'password_prompt'} keys to be populated
        in the L{device} dictionary.
        
        @return: A L{Deferred}, that is fired when (if) the login succeeds. Callback
        argument is meaningless and should be ignored. Possible errback argument types:
            - L{UnexpectedResultError}: if the desired password prompt wasn't encountered
            - L{LoginFailed}: if the prompt was not encountered after entering the
            password (usually happens when the password is incorrect).
        @rtype: L{Deferred}
        
        """
        d = self.read_until(self.device['password_prompt'])
        d.addCallbacks(callback=lambda ign: self.write(self.device['password']+'\n'),
                       errback=self._no_password_prompt)
        d.addCallback(lambda ign: self.read_to_prompt())
        d.addCallbacks(callback=self._on_login_success, errback=self._on_login_failure)
        return d
    
    def _no_password_prompt(self, failure):
        """Handle unexpected output when waiting for the password prompt.
        Only L{RequestTimeout<texpect.RequestTimeout>} is caught.
        
        @param failure: L{Failure} instance, that was passed to the handler.
        @type failure: L{Failure}
        
        @return: L{Failure}, containing L{UnexpectedResultError}
        @rtype: L{Failure}
        
        """
        failure.trap(RequestTimeout)
        exc = failure.value
        return Failure(UnexpectedResultError(
            'Did not get what we expected. Expected: %s, got %r' %
             ([e.pattern for e in exc.promise.expecting], exc.data), data=exc.data
        ))
    
    def _on_login_success(self, res):
        """Handle successful login. If 'disable_paging' is present in the
        L{device} dictionary, attempt to disable paging on the device using the
        command, specified at the 'disable_paging_command' key of the L{device}
        dictionary
        
        @param res: Result of the callback, meaningless.
        @type res: C{str}
        
        @return: Result of the previous callback invocation or L{Deferred}, if we
        are trying to disable paging (for possible errback argument types in this
        case see L{run_command})
        @rtype: C{str} or L{Deferred}
        
        """
        if self.debug:
            log.msg("Logged in to %s" % self.device['id'])
        disable_paging = self.device.get('disable_paging')
        if disable_paging:
            return self.run_command(self.device['disable_paging_command'])
        return res
    
    def _on_login_failure(self, failure):
        """Handle failed login. Catches L(RequestFailed<texpect.RequestFailed>).
        
        @return: L{Failure}, containing L{LoginFailed}
        @rtype: L{Failure}
        
        """
        failure.trap(RequestFailed)
        exc = failure.value
        return Failure(LoginFailed('Failed to log in to %s' %
                                   self.device['id'], data=exc.data))
    
    def run_command(self, command, prompt=None, timeout=None,
            strip_command=True, strip_prompt=True, process_errors=True,
            _may_disconnect=False):
        """Run a command, capturing the output.
        
        @param command: the command to be executed. Do not include trailing newline.
        @type command: C{str}
        
        @param prompt: Normally a command should end with a prompt (normal, privileged
        or privileged with suffix, like C{'switch(config-if)#'}). This argument
        overrides the prompt if the default behaviour is not sufficient
        @type prompt: C{str} or C{_sre.SRE_Pattern} (compiled regular expression instance)
        
        @param timeout: Override the instance-default timeout
        @type timeout: C{int}
        
        @param strip_command: Whether or not the line, containing the actual invocation
        of the command should be stripped. Default: C{True}.
        @type strip_command: C{bool}
        
        @param strip_prompt: Whether or not the line, containing the prompt, that
        follows the command output should be stripped. Default: C{True}.
        @type strip_prompt: C{bool}
        
        @param process_errors: Whether or not should the output be checked for
        Cisco-produced errors (lines, starting with '%'). Default: C{True}.
        @type process_errors: C{bool}
        
        @param _may_disconnect: Signals if the command that is to be run may cause
        the connection to be terminated. Invokes a special case in the error processing
        logic so that we don't get an error if we are disconnected. Default: C{False}
        @type _may_disconnect: C{bool}
        
        @return: A L{Deferred}, that will be fired with the processed output of the
        command.
        Errback argument types:
            - L{UnexpectedResultError}: if the command failed in an out-of-band
            way (the desired prompt was not encountered or something)
            - L{CiscoCommandError}: if the command has been executed, but the device
            has reported an error (due to a syntax error, invalid arguments and so on)
            - L{Disconnected}: if the connection was lost during or as a result
            of running the command
        @rtype: L{Deferred}
         
        """
        if self.eof:
            return fail(Failure(NotConnected('Not connected to %s at the moment' %
                                              self.device['id'], command=command)))
        if timeout is None:
            timeout = self.timeout
        if prompt is None:
            if self.enabled:
                prompt = self.device['enabled_prompt']
            else:
                prompt = self.device['prompt']
        command = command.strip()
        
        if self.debug:
            log.msg("Running command '%s' on %s, expecting %s" %
                    (command, self.device['id'], prompt))

        d = self.write(command+'\n')
        d.addCallback(lambda ign: self.expect([prompt], timeout=timeout))
        d.addCallbacks(callback=self._process_command_result,
                       callbackArgs=[command, strip_command, strip_prompt, process_errors],
                       errback=self._on_command_error,
                       errbackArgs=[command, strip_command, strip_prompt,
                                    process_errors, _may_disconnect])
        return d
    
    def _on_command_error(self, failure, cmd, strip_command, strip_prompt,
                          process_errors, _may_disconnect):
        """Handle command error, such as unexpected connection loss,
        not encountering the expected prompt and so on. Anything, not derived from
        L{RequestFailed<texpect.RequestFailed>} is not caught.
        
        @param failure: L{Failure} instance, that was passed to the errback.
        @type failure: L{Failure}
        
        @param cmd: The command, that was run.
        @type cmd: C{str}
        
        @param strip_command: Whether or not the line, containing the actual invocation
        of the command should be stripped. Default: C{True}.
        @type strip_command: C{bool}
        
        @param strip_prompt: Whether or not the line, containing the prompt, that
        follows the command output should be stripped. Default: C{True}.
        @type strip_prompt: C{bool}
        
        @param process_errors: Whether or not should the output be checked for
        Cisco-produced errors (lines, starting with '%'). Default: C{True}.
        @type process_errors: C{bool}
        
        @note: These three arguments are only used if L{_may_disconnect} is set to
        C{True} and we got disconnected. In such a case these arguments are forwarded
        to L{_process_command_result}. 
        
        @param _may_disconnect: If C{True} a request interrupted by connection loss
        is considered a success and further command processing resumes, so that we
        can get back the output. Default: C{False}
        @type _may_disconnect: C{bool}
        
        @return: A L{Failure} instance, wrapping L{UnexpectedResultError}.  
        @rtype: L{Failure}
        
        """
        failure.trap(RequestFailed)
        exc = failure.value
        if failure.check(RequestInterruptedByConnectionLoss) is not None:
            # Unconditionally set strip_prompt to False (there will be no prompt)
            # and fake the usual 'expect' result (first two items will not be needed)
            if _may_disconnect: 
                return self._process_command_result((None, None, exc.data), cmd,
                                                strip_command, False, process_errors)
            else:
                return Failure(Disconnected('Command resulted in a disconnection',
                                            cmd, data=exc.data))
        return Failure(UnexpectedResultError(
            "Error running command '%s'. Expected: %s, got %r" %
             (cmd, [e.pattern for e in exc.promise.expecting], exc.data)
        ))
    
    def _process_command_result(self, res, cmd, strip_command, strip_prompt, process_errors):
        """Process the result of a successfully completed command.
        
        @param res: Result of the underlying L{Expect} callback, typically
        C{(pattern_index, match_object, data)}.
        @type res: C{tuple}
        
        @param cmd: The command, that was run.
        @type cmd: C{str}
        
        @param strip_command: Whether or not the line, containing the actual invocation
        of the command should be stripped.
        @type strip_command: C{bool}
        
        @param strip_prompt: Whether or not the line, containing the prompt, that
        follows the command output should be stripped.
        @type strip_prompt: C{bool}
        
        @param process_errors: Whether or not should the output be checked for
        Cisco-produced errors (lines, starting with '%').
        @type process_errors: C{bool}
        
        @return: Command output or L{Failure}, containing L{CiscoCommandError}, if
        L{process_errors} is True and errors were encountered.
        @rtype: C{str} or L{Failure}
        
        """
        (match_obj, data) = res[1:]
        if strip_prompt:
            data = data[:match_obj.start()]
        data = data.strip()
        if strip_command:
            if data.startswith(cmd):
                data = data[len(cmd):].lstrip()
        if process_errors:
            error = self._process_device_errors(data)
            if error is not None:
                (error_lines, _) = error
                return Failure(CiscoCommandError(
                    'An error was reported by the device "%s" while running the command "%s"' %
                        (self.device['id'], cmd),
                    command=cmd,
                    error='\n'.join(error_lines),
                    data=data
                    ))
        return data
    
    def _process_device_errors(self, data):
        """Check for typical Cisco-style errors in the output. The errors are usually
        formatted in one of two ways:
            - with the error marker::
                switch#show qwerty
                             ^
                % Invalid input detected at '^' marker.
    
                switch#
            
            - or without::
                
                switch>123
                % Unknown command or computer name, or unable to find computer address
                switch>
        
        @param data: Data to be checked for errors
        @type data: C{str}
        
        @return: A 2-tuple where the items are:
            - the error message, that was captured, presented as a list of lines
            - the data sans the error message (basically, everything before and after
            the error), presented as a list of lines
        or C{None} if the error was not detected
        @rtype: C{tuple} or C{None}
        
        @note: If the error message contains a '^' marker, its position, relative
        to the previous line is not preserved! 

        """
        lines = data.split('\n')
        for ind, line in enumerate(lines):
            if line.startswith('%'):
                if line.find("'^' marker") != -1:
                    error_lines = lines[ind-1:ind+2]
                    data_lines = lines[:ind-1]+lines[ind+2:]
                else:
                    error_lines = lines[ind:ind+1]
                    data_lines = lines[:ind]+lines[ind+1:]
                return (error_lines, data_lines)
        else:
            return None
        
    
    def enable(self, timeout=None):
        """Attempt to enter privileged EXEC mode.
        Requires 'enable_command', 'enable_password', 'enable_password_prompt' and 'enabled_prompt'
        keys to be populated in the L{device} dictionary.
        
        @param timeout: Override the instance-default command timeout. Default: C{None}
        @type timeout: C{int}
        
        @return: L{Deferred}, that will be fired when (if) the 'enable' command succeeds.
        Callback argument is meaningless.
        Errback argument types
            - L{EnableFailed}: if the prompt was not encountered after entering
            'enable_password'. Usually happens when the password is invalid
            - L{CiscoCommandError}: if the 'enable' command failed to run at all,
            perhaps the value at the 'enable_command' key of L{device} dictionary
            is invalid
        @rtype: L{Deferred}
        
        """
        if timeout is None:
            timeout = self.timeout
        d = self.run_command(self.device['enable_command'],
                             prompt=self.device['enable_password_prompt'])
        d.addCallback(lambda ign: self.write(self.device['enable_password']+'\n'))
        d.addCallback(lambda ign: self.read_to_prompt(self.device['enabled_prompt'], timeout))
        d.addCallbacks(callback=self._on_enable, errback=self._on_enable_failure)
        return d
    
    def _on_enable(self, res):
        """Handle success of the 'enable' command. Sets the L{enabled} instance
        attribute.
        
        @param res: Result of the previous callback
        
        @return: Result of the previous callback, meaningless and should not be used.
        
        """
        if self.debug:
            log.msg("Entered privileged EXEC mode on %s" % self.device['id'])
        self.enabled = True
        return res
        
    def _on_enable_failure(self, failure):
        """Handle the failure of 'enable' command. Catches L{RequestFailed}.
        
        @param failure: L{Failure} instance, passed to this errback
        @type failure: L{Failure}
        
        @return: L{Failure}, containing L{EnableFailed}.
        @rtype: L{Failure}
        """
        failure.trap(RequestFailed)
        exc = failure.value
        return Failure(EnableFailed('Failed to enter privileged EXEC mode on %s' %
                                    self.device['id'], data=exc.data))
    
    def exit(self, prompt=None, timeout=None,strip_command=True,
             strip_prompt=True, process_errors=True):
        """Convenience method for the 'exit' command. Handles the situation, when
        running it results in the connection loss.
        
        See L{run_command}
        
        """
        return self.run_command('exit', prompt, timeout,
                                strip_command, strip_prompt, process_errors,
                                _may_disconnect=True)
    