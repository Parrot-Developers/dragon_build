
# Due to wildcard import in dragon, import local modules as private

import os as _os
import sys as _sys
import logging as _logging
import subprocess as _subprocess

# Detect windows platform to force using msys shell (though 'sh')
# instead of default shell (cmd.exe)
_mswindows = (_sys.platform == "win32")

import dragon as _dragon

#===============================================================================
# Exec call error
#===============================================================================
class ExecError(_subprocess.SubprocessError):
    def __init__(self, message):
        _subprocess.SubprocessError.__init__(self)
        self.message = message
    def __str__(self):
        return self.message

#===============================================================================
# Execute given command in given directory with given extra environment
# and get output as a string.
# If command fails, it will be ignored.
#===============================================================================
def exec_shell(cmd, cwd=None, extra_env=None, single_line=True):
    env = _os.environ.copy()
    if extra_env:
        env.update(extra_env)
    try:
        if _mswindows:
            process = _subprocess.Popen("sh -c '%s'" % cmd, cwd=cwd, env=env,
                    stdout=_subprocess.PIPE, shell=False, universal_newlines=True)
        else:
            process = _subprocess.Popen(cmd, cwd=cwd, env=env,
                    stdout=_subprocess.PIPE, shell=True, universal_newlines=True)
        if single_line:
            return process.communicate()[0].replace("\n", " ").strip()
        else:
            return process.communicate()[0]
    except OSError as ex:
        _logging.warning("%s: %s", cmd, str(ex))
        return ""

#===============================================================================
# Execute the given command in given directory with given extra environment.
#===============================================================================
def exec_cmd(cmd, cwd=None, extra_env=None, dryrun=None, dryrun_arg=None):
    if not cwd:
        cwd = _dragon.WORKSPACE_DIR
    if dryrun is None:
        dryrun = _dragon.OPTIONS.dryrun
    # Add extra environment variables before command
    if extra_env:
        env = " ".join(['%s="%s"' % (key, extra_env[key])
                for key in sorted(extra_env.keys())])
        cmd = env + " " + cmd
    # Execute command unless in dry mode
    if dryrun:
        if not dryrun_arg:
            _logging.info("Dry run in '%s': %s", cwd, cmd)
            return
        cmd += " " + dryrun_arg

    _logging.info("In '%s': %s", cwd, cmd)
    try:
        if _mswindows:
            process = _subprocess.Popen("sh -c '%s'" % cmd, cwd=cwd, shell=False)
        else:
            process = _subprocess.Popen(cmd, cwd=cwd, shell=True)
        process.wait()
        if process.returncode != 0:
            raise ExecError("Command failed (returncode=%d)" % process.returncode)
    except OSError as ex:
        raise ExecError("Exception caught ([err=%d] %s)" % (ex.errno, ex.strerror))

#===============================================================================
# Create a symlink with relative path
# src : source (target of link)
# dst : destination (link to create)
#===============================================================================
def relative_symlink(src, dst):
    out_dir = _os.path.realpath(_dragon.OUT_DIR)
    workspace_dir = _os.path.realpath(_dragon.WORKSPACE_DIR)
    if out_dir.startswith(workspace_dir):
        for path in [src, dst]:
            if not _os.path.realpath(path).startswith(workspace_dir):
                raise ExecError("'%s' is not part of the workspace." % path)
    else:
        # OUT_DIR is outside WORKSPACE_DIR (jenkins), simply warn
        for path in [src, dst]:
            if not _os.path.realpath(path).startswith(workspace_dir):
                _logging.warning("'%s' is not part of the workspace.", path)

    if _os.path.lexists(dst):
        if not _os.path.islink(dst):
            raise ExecError("'%s' should not be a regular file/directory" % dst)
        exec_cmd("rm -f %s" % dst)
    makedirs(_os.path.dirname(dst))
    exec_cmd("ln -fs %s %s" % (_os.path.relpath(src, _os.path.dirname(dst)), dst))

#===============================================================================
# Create directory tree if needed with correct access rights.
#===============================================================================
def makedirs(dirpath, mode=0o755):
    if not _os.path.isdir(dirpath):
        _os.makedirs(dirpath, mode)

#===============================================================================
# Forward basic dragon options
#
# When using subscripts called by dragon, some options may be propagated
# like verbosity or color.
#===============================================================================
def forward_options():
    arguments = []
    if _dragon.OPTIONS.verbose:
        arguments.append("--verbose")

    if _dragon.OPTIONS.colors:
        arguments.append("--color")
    else:
        arguments.append("--no-color")

    return arguments

#===============================================================================
# Call a sub script, implicitely forwarding dragon_options
#
# We assume that the script implements these basic options
#===============================================================================
def call_script(script_name, args, **kwargs):
    base_args = forward_options()

    dryrun = None
    if _dragon.OPTIONS.dryrun:
        dryrun = "--dry-run"

    cmd = [script_name]
    cmd.extend(base_args)
    if args:
        cmd.extend(args)
    exec_cmd(" ".join(cmd), dryrun_arg=dryrun, **kwargs)
