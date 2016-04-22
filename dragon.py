#===============================================================================
# Contains base functions to register tasks and execute them.
# Imported by build.py and product configuration.
#===============================================================================

import sys, logging
import subprocess

# Common tools for dragon and products needs
# Wildcard import to avoid prefixing everything with dragon.utils
from utils import *

# List of registered tasks
_tasks = {}

# Logger
_log = logging.getLogger("dragon")

# Options
OPTIONS = None

# Selected product configuration module
_product_cfg_module = None

# Set workspace directory (go up relative to this script)
WORKSPACE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Global variables
PRODUCT = ""
VARIANT = ""
OUT_ROOT_DIR = os.environ.get("DRAGON_OUT_ROOT_DIR", "")
OUT_DIR = os.environ.get("DRAGON_OUT_DIR", "")
BUILD_DIR = ""
STAGING_DIR = ""
FINAL_DIR = ""
IMAGES_DIR = ""
PRODUCT_DIR = ""
VARIANT_DIR = ""

# Parrot build properties, can be overridden by buildcfg.py
PARROT_BUILD_PROP_GROUP = os.environ.get("PARROT_BUILD_PROP_GROUP", "drones")
PARROT_BUILD_PROP_PROJECT = os.environ.get("PARROT_BUILD_PROP_PROJECT", "")
PARROT_BUILD_PROP_PRODUCT = os.environ.get("PARROT_BUILD_PROP_PRODUCT", "")
PARROT_BUILD_PROP_VARIANT = os.environ.get("PARROT_BUILD_PROP_VARIANT", "")
PARROT_BUILD_PROP_REGION = os.environ.get("PARROT_BUILD_PROP_REGION", "")
PARROT_BUILD_PROP_UID = os.environ.get("PARROT_BUILD_PROP_UID", "")
PARROT_BUILD_PROP_VERSION = os.environ.get("PARROT_BUILD_PROP_VERSION", "")

# Directory where alchemy is
ALCHEMY_HOME = os.environ.get("ALCHEMY_HOME", "")

# Directory where police is
POLICE_HOME = os.environ.get("POLICE_HOME", "")

POLICE_OUT_DIR = ""
POLICE_SPY_LOG = ""
POLICE_PROCESS_LOG = ""

# Log wrappers
LOGE = _log.error
LOGW = _log.warning
LOGI = _log.info
LOGD = _log.debug
LOGV = _log.debug

#===============================================================================
# Generic task error.
#===============================================================================
class TaskError(Exception):
    pass

#===============================================================================
#===============================================================================
class Hook(object):
    def __init__(self, fn, basehook=None):
        self.fn = fn
        self.basehook = basehook

    def __call__(self, task, args):
        self.fn(task, args)

#===============================================================================
# Generic task.
#===============================================================================
class Task(object):
    def __init__(self, name, desc, secondary_help=False,
            exechook=None, prehook=None, posthook=None, weak=False):
        self.name = name
        self.desc = desc
        self.secondary_help = secondary_help
        self.exechook = Hook(exechook) if exechook else None
        self.prehook = Hook(prehook) if prehook else None
        self.posthook = Hook(posthook) if posthook else None
        self.extra_env = None
        self.weak = weak

    # To be implemented by tasks to actually do something
    def _do_exec(self, args=None):
        pass

    def call_base_exec_hook(self, args):
        if self.exechook and self.exechook.basehook:
            self.exechook.basehook(self, args)

    def call_base_pre_hook(self, args):
        if self.prehook and self.prehook.basehook:
            self.prehook.basehook(self, args)

    def call_base_post_hook(self, args):
        if self.posthook and self.posthook.basehook:
            self.posthook.basehook(self, args)

    # Start execution of task by executing hooks before and after internal
    # task execution
    def execute(self, args=None, extra_env=None):
        # Clear extra env before executing hooks and task
        self.extra_env = {}
        if extra_env:
            self.extra_env.update(extra_env)

        # Start task
        if args:
            _log.info("Starting task '%s' with args: %s", self.name, " ".join(args))
        else:
            _log.info("Starting task '%s'", self.name)

        try:
            # Execute hooks
            if self.prehook:
                self.prehook(self, args)
            if self.exechook:
                self.exechook(self, args)
            else:
                self._do_exec(args)
            if self.posthook:
                self.posthook(self, args)
        except TaskError as ex:
            _log.error("Task '%s' failed (%s)", self.name, ex.message)
            if not OPTIONS.keep_going:
                sys.exit(1)
        else:
            # Task is finished
            _log.info("Finished task '%s'", self.name)

#===============================================================================
# Alchemy build system task.
#===============================================================================
class AlchemyTask(Task):
    def __init__(self, name, desc, product, variant, defargs=None,
                secondary_help=False, prehook=None, posthook=None, weak=False,
                outsubdir=None):
        Task.__init__(self, name, desc, secondary_help=secondary_help,
                prehook=prehook, posthook=posthook, weak=weak)
        self.product = product
        self.product_variant = variant
        self.defargs = defargs
        self.outsubdir = outsubdir
        # Define some helper variables (will be set in _setup_vars)
        self.top_dir = WORKSPACE_DIR
        self.fullname = None
        self.out_dir = None
        self.plf_path = None
        self.build_prop_path = None
        self.sdk_path = None
        self.symbols_path = None

    # Setup some variable and do some checks
    def _setup_vars(self):
        self.fullname = self.product + "-" + self.product_variant
        if self.outsubdir:
            self.out_dir = os.path.join(OUT_DIR, self.outsubdir)
        else:
            self.out_dir = OUT_DIR
        self.plf_path = os.path.join(self.out_dir,
                self.fullname + ".plf")
        self.build_prop_path = os.path.join(self.out_dir,
                "staging", "etc", "build.prop")
        self.sdk_path = os.path.join(self.out_dir,
                "sdk-%s.tar.gz" % self.fullname)
        self.symbols_path = os.path.join(self.out_dir,
                "symbols-%s.tar" % self.fullname)

    def _setup_extra_env(self):
        # Export parrot build properties
        if PARROT_BUILD_PROP_GROUP:
            self.extra_env["PARROT_BUILD_PROP_GROUP"] = PARROT_BUILD_PROP_GROUP
        if PARROT_BUILD_PROP_PROJECT:
            self.extra_env["PARROT_BUILD_PROP_PROJECT"] = PARROT_BUILD_PROP_PROJECT
        if PARROT_BUILD_PROP_PRODUCT:
            self.extra_env["PARROT_BUILD_PROP_PRODUCT"] = PARROT_BUILD_PROP_PRODUCT
        if PARROT_BUILD_PROP_VARIANT:
            self.extra_env["PARROT_BUILD_PROP_VARIANT"] = PARROT_BUILD_PROP_VARIANT
        if PARROT_BUILD_PROP_REGION:
            self.extra_env["PARROT_BUILD_PROP_REGION"] = PARROT_BUILD_PROP_REGION
        if PARROT_BUILD_PROP_UID:
            self.extra_env["PARROT_BUILD_PROP_UID"] = PARROT_BUILD_PROP_UID
        if PARROT_BUILD_PROP_VERSION:
            self.extra_env["PARROT_BUILD_PROP_VERSION"] = PARROT_BUILD_PROP_VERSION

        # Export Alchemy variables
        self.extra_env["ALCHEMY_WORKSPACE_DIR"] = self.top_dir
        self.extra_env["ALCHEMY_TARGET_PRODUCT"] = self.product
        self.extra_env["ALCHEMY_TARGET_PRODUCT_VARIANT"] = self.product_variant
        self.extra_env["ALCHEMY_TARGET_OUT"] = self.out_dir
        self.extra_env["ALCHEMY_TARGET_CONFIG_DIR"] = os.path.join(WORKSPACE_DIR,
                "products", self.product, self.product_variant, "config")

        # Only scan packages sub-directory and exclude top directory (workspace)
        self.extra_env["ALCHEMY_TARGET_SCAN_PRUNE_DIRS"] = " ".join([
                os.environ.get("ALCHEMY_TARGET_SCAN_PRUNE_DIRS", ""),
                self.top_dir])
        self.extra_env["ALCHEMY_TARGET_SCAN_ADD_DIRS"] = " ".join([
                os.environ.get("ALCHEMY_TARGET_SCAN_ADD_DIRS", ""),
                os.path.join(self.top_dir, "packages")])

        # Use colors (unless already set or disabled, by jenkins for example)
        if not os.environ.get("ALCHEMY_USE_COLORS", ""):
            self.extra_env["ALCHEMY_USE_COLORS"] = 1

    def _do_exec(self, args=None):
        # Setup variables end extra env
        self._setup_vars()
        self._setup_extra_env()
        cmd_args = []

        # Verbose/jobs
        cmd_args.append("-j%d" % OPTIONS.jobs)
        if OPTIONS.verbose:
            cmd_args.append("V=1")

        # Get arguments from task if none provided
        if (not args or OPTIONS.append_args) and self.defargs:
            cmd_args.extend(self.defargs)

        # Add given arguments
        if args:
            cmd_args.extend(args)

        # Execute command
        exec_cmd("%s/scripts/alchemake %s" %
                (ALCHEMY_HOME, " ".join(cmd_args)),
                cwd=self.top_dir,
                extra_env=self.extra_env)

#===============================================================================
# Meta task.
#===============================================================================
class MetaTask(Task):
    def __init__(self, name, desc, subtasks=None, secondary_help=False,
                exechook=None, prehook=None, posthook=None, weak=False):
        Task.__init__(self, name, desc, secondary_help=secondary_help,
                exechook=exechook, prehook=prehook, posthook=posthook,
                weak=weak)
        self.subtasks = subtasks

    def _do_exec(self, args=None):
        # Subtask list can be empty in case user was only interested in hooks
        if not self.subtasks:
            return
        for subtask in self.subtasks:
            cmd_args = []
            # Split subtask in name and arguments
            subtaskargs = subtask.split(" ")
            subtaskname = subtaskargs[0]
            subtaskargs = subtaskargs[1:]
            # Get arguments from subtask if none provided
            if (not args or OPTIONS.append_args) and subtaskargs:
                cmd_args.extend(subtaskargs)
            # Execute subtask
            do_task(subtaskname, cmd_args, self.extra_env)

#===============================================================================
# Product task.
#===============================================================================
class ProductTask(Task):
    def __init__(self, name, desc, product, variant, defargs=None,
                secondary_help=False,
                prehook=None, posthook=None, weak=False):
        Task.__init__(self, name, desc, secondary_help=secondary_help,
                prehook=prehook, posthook=posthook,
                weak=weak)
        self.product = product
        self.variant = variant
        self.defargs= defargs

    @staticmethod
    def _extend_args(cmd_args, args):
        # Add -t for each arg if not given
        for arg in args:
            if arg.startswith("-t"):
                cmd_args.append(arg)
            else:
                cmd_args.append("-t " + arg)

    def _do_exec(self, args=None):
        cmd_args = []

        # Get arguments from task if none provided
        if (not args or OPTIONS.append_args) and self.defargs:
            ProductTask._extend_args(cmd_args, self.defargs)

        # Add given arguments
        if args:
            ProductTask._extend_args(cmd_args, args)

        restart(OPTIONS, self.product, self.variant, cmd_args)

#===============================================================================
# Register a new task.
#===============================================================================
def add_task(task):
    if task.name in _tasks:
        # Task with same name already exists, check weakness
        if not _tasks[task.name].weak:
            # Previous task added is not weak !
            _log.warning("add_task: duplicate entry: '%s'", task.name)
        else:
            _tasks[task.name] = task
    else:
        _tasks[task.name] = task

#===============================================================================
# Register a new alchemy task.
#===============================================================================
def add_alchemy_task(name, desc, product, variant, defargs=None,
        secondary_help=False,
        prehook=None, posthook=None, weak=False,
        outsubdir=None):
    add_task(AlchemyTask(name, desc, product, variant, defargs,
            secondary_help, prehook, posthook, weak, outsubdir))

#===============================================================================
# Register a new meta task.
#===============================================================================
def add_meta_task(name, desc, subtasks=None,
        secondary_help=False,
        exechook=None, prehook=None, posthook=None, weak=False):
    add_task(MetaTask(name, desc, subtasks,
            secondary_help, exechook, prehook, posthook, weak))

#===============================================================================
# Register a new product task.
#===============================================================================
def add_product_task(name, desc, product, variant, defargs=None,
        secondary_help=False,
        prehook=None, posthook=None, weak=False):
    add_task(ProductTask(name, desc, product, variant, defargs,
            secondary_help, prehook, posthook, weak))

#===============================================================================
#===============================================================================
def get_tasks():
    return _tasks

#===============================================================================
# Override a task
#===============================================================================
def _override_task(task, desc=None, exechook=None, prehook=None, posthook=None):
    if desc is not None:
        task.desc = desc
    # Chain new hooks
    if exechook is not None:
        task.exechook = Hook(exechook, task.exechook)
    if prehook is not None:
        task.prehook = Hook(prehook, task.prehook)
    if posthook is not None:
        task.posthook = Hook(posthook, task.posthook)

#===============================================================================
# Override an alchemy task
#===============================================================================
def override_alchemy_task(name, desc=None, defargs=None,
        exechook=None, prehook=None, posthook=None):
    task = _tasks.get(name, None)
    if not task:
        _log.warning("override_alchemy_task: unknown task: '%s'", name)
    elif not isinstance(task, AlchemyTask):
        _log.warning("override_alchemy_task: invalid alchemy task: '%s'", name)
    else:
        if defargs is not None:
            task.defargs = defargs
        _override_task(task, desc, exechook, prehook, posthook)

#===============================================================================
# Override a meta task
#===============================================================================
def override_meta_task(name, desc=None, subtasks=None,
        exechook=None, prehook=None, posthook=None):
    task = _tasks.get(name, None)
    if not task:
        _log.warning("override_meta_task: unknown task: '%s'", name)
    elif not isinstance(task, MetaTask):
        _log.warning("override_meta_task: invalid meta task: '%s'", name)
    else:
        if subtasks is not None:
            task.subtasks = subtasks
        _override_task(task, desc, exechook, prehook, posthook)

#===============================================================================
# Check that tasks are valid: metatask sun tasks should exist.
# Recursion is not detected
#===============================================================================
def check_tasks():
    for task in _tasks.values():
        if not isinstance(task, MetaTask):
            continue
        if not task.subtasks:
            continue
        for subtask in task.subtasks:
            subtaskname = subtask.split(" ")[0]
            if not subtaskname in _tasks:
                _log.warning("Meta task '%s' uses unknown task '%s'",
                        task.name, subtaskname)

#===============================================================================
# Disable default tasks (it will actually remove all currently registered tasks)
#===============================================================================
def disable_def_tasks(keep_list=None):
    LOGD("Disable default tasks")
    if keep_list is None:
        _tasks.clear()
    else:
        for task in _tasks.keys():
            if task not in keep_list:
                del _tasks[task]

#===============================================================================
# Execute given command in given directory with given extra environment
# and get output as a string.
# If command fails, it will be ignored.
#===============================================================================
def exec_shell(cmd, cwd=None, extra_env=None, single_line=True):
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    try:
        process = subprocess.Popen(cmd, cwd=cwd, env=env,
                stdout=subprocess.PIPE, shell=True)
        if single_line:
            return process.communicate()[0].replace("\n", " ").strip()
        else:
            return process.communicate()[0]
    except OSError as ex:
        LOGW("%s: %s", cmd, str(ex))
        return ""

#===============================================================================
# Execute the given command in given directory with given extra environment.
#===============================================================================
def exec_cmd(cmd, cwd=None, extra_env=None, dryrun_arg=""):
    if not cwd:
        cwd = os.getcwd()
    # Add extra environment variables before command
    if extra_env:
        env = " ".join(['%s="%s"' % (key, extra_env[key]) for (key) in sorted(extra_env.keys())])
        cmd = env + " " + cmd
    # Execute command unless in dry mode
    if OPTIONS.dryrun:
        if not dryrun_arg:
            _log.info("Dry run in '%s': %s", cwd, cmd)
            return
        cmd += " " + dryrun_arg

    _log.info("In '%s': %s", cwd, cmd)
    try:
        process = subprocess.Popen(cmd, cwd=cwd, shell=True)
        process.wait()
        if process.returncode != 0:
            raise TaskError("Command failed (returncode=%d)" % process.returncode)
    except OSError as ex:
        raise TaskError("Exception caught ([err=%d] %s)" % (ex.errno, ex.strerror))

#===============================================================================
# Execute the given command in given directory.
#===============================================================================
def exec_dir_cmd(dirpath, cmd, extra_env=None):
    exec_cmd(cmd=cmd, cwd=dirpath, extra_env=extra_env)

#===============================================================================
# Start a task.
#===============================================================================
def do_task(taskname, args=None, extra_env=None):
    if taskname not in _tasks:
        raise TaskError("Unknown task: '%s'" % taskname)
    else:
        _tasks[taskname].execute(args, extra_env)

#===============================================================================
# Restart the build script with given product/variant
#===============================================================================
def restart(options, product, variant, args):
    cmd_args = []
    cmd_args.append("-p %s-%s" % (product, variant))
    cmd_args.append("-j %s" % options.jobs)
    opt_args = [
        (options.verbose, "-v"),
        (options.dryrun, "-n"),
        (options.append_args, "-a"),
        (options.keep_going, "-k"),
        (options.build_id, "-b %s" % options.build_id),
        (options.police, "--police"),
        (options.police_no_spy, "--police-no-spy"),
        (options.police_packages, "--police-packages"),
    ]
    for opt, arg in opt_args:
        if opt:
            cmd_args.append(arg)

    if args:
        cmd_args.extend(args)

    try:
        exec_cmd("%s %s" % (sys.argv[0], " ".join(cmd_args)))
    except TaskError as ex:
        logging.error(str(ex))
        if not options.keep_going:
            sys.exit(1)

#===============================================================================
# Get the output directory of a product/variant.
# Default is to to get current product/variant
#===============================================================================
def get_out_dir(product=None, variant=None):
    if product is None and variant is None:
        # Both None, use current
        product = PRODUCT
        variant = VARIANT
    elif product is None or variant is None:
        # Both shall be set
        raise TaskError("get_out_dir: product or variant missing")
    return os.path.join(OUT_ROOT_DIR, "%s-%s" % (product, variant))

#===============================================================================
# Generate police report in the final directory.
#
# To be taken into account, it shall be done AFTER the 'final' task and BEFORE
# the 'image' task
#
# addhtml: True to add the generated html
# addtxt: True to add the generated txt
# compress: True to compress the files with gzip.
#===============================================================================
def police_report(addhtml=True, addtxt=False, compress=False):
    # Process step
    _log.info("Police: process")
    exec_cmd("%s --infile %s --outfile %s %s" % (
            os.path.join(POLICE_HOME, "police-process.py"),
            POLICE_SPY_LOG,
            POLICE_PROCESS_LOG,
            "-v" if OPTIONS.verbose else ""))

    # Report step
    _log.info("Police: report")
    exec_cmd("%s --infile %s --outdir %s --rootdir %s --builddir %s --finaldir %s --md5 %s" % (
            os.path.join(POLICE_HOME, "police-report.py"),
            POLICE_PROCESS_LOG,
            POLICE_OUT_DIR,
            WORKSPACE_DIR,
            OUT_DIR,
            FINAL_DIR,
            "-v" if OPTIONS.verbose else ""))

    # Remove existing police files
    police_final_dir = os.path.join(FINAL_DIR, "usr", "share", "police")
    exec_cmd("rm -rf %s" % police_final_dir)
    makedirs(police_final_dir)

    # Add files
    if addhtml:
        exec_cmd("cp -af %s %s" % (
                os.path.join(POLICE_OUT_DIR, "police-notice.html"),
                police_final_dir))
        if compress:
            exec_cmd("gzip %s" % os.path.join(police_final_dir, "police-notice.html"))
    if addtxt:
        exec_cmd("cp -af %s %s" % (
                os.path.join(POLICE_OUT_DIR, "police-notice.txt"),
                police_final_dir))
        if compress:
            exec_cmd("gzip %s" % os.path.join(police_final_dir, "police-notice.txt"))

#===============================================================================
#===============================================================================
def police_get_packages():
    # Get list of packages to generate
    packages = []
    with open(os.path.join(POLICE_OUT_DIR, "police-package-license-module.txt")) as fin:
        for line in fin:
            package = line.split(" ")[1].rstrip("\n")
            if "#" in package:
                package = package.split("#")[0]
            if package not in packages:
                packages.append(package)
    return " ".join(packages)
