
import sys
import os
import logging

import dragon
import utils

# Generic task error.
TaskError = utils.ExecError

# Raised to exit current task and continue
class TaskExit(Exception):
    # Wrap a function call, catching and ignoring TaskExit exceptions
    @staticmethod
    def wrap(fct, *args):
        try:
            fct(*args)
        except TaskExit:
            pass

#===============================================================================
#===============================================================================
class Hook(object):
    def __init__(self, fct, basehook=None):
        self.fct = fct
        self.basehook = basehook

    def __call__(self, task, args):
        self.fct(task, args)

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
        self.top_info = None

    # To be implemented by tasks to actually do something
    def _do_exec(self, args=None):
        pass

    def call_base_exec_hook(self, args):
        if self.exechook and self.exechook.basehook:
            oldhook = self.exechook
            self.exechook = self.exechook.basehook
            try:
                TaskExit.wrap(self.exechook, self, args)
            finally:
                self.exechook = oldhook

    def call_base_pre_hook(self, args):
        if self.prehook and self.prehook.basehook:
            oldhook = self.prehook
            self.prehook = self.prehook.basehook
            try:
                TaskExit.wrap(self.prehook, self, args)
            finally:
                self.prehook = oldhook

    def call_base_post_hook(self, args):
        if self.posthook and self.posthook.basehook:
            oldhook = self.posthook
            self.posthook = self.posthook.basehook
            try:
                TaskExit.wrap(self.posthook, self, args)
            finally:
                self.posthook = oldhook

    # Start execution of task by executing hooks before and after internal
    # task execution
    def execute(self, args=None, extra_env=None, top_info=None):
        # Clear extra env before executing hooks and task
        self.extra_env = {}
        if extra_env:
            self.extra_env.update(extra_env)
        self.top_info = top_info

        # Start task
        if args:
            logging.info("Starting task '%s' with args: %s", self.name, " ".join(args))
        else:
            logging.info("Starting task '%s'", self.name)

        try:
            # Execute hooks
            if self.prehook:
                TaskExit.wrap(self.prehook, self, args)
            if self.exechook:
                TaskExit.wrap(self.exechook, self, args)
            else:
                TaskExit.wrap(self._do_exec, args)
            if self.posthook:
                TaskExit.wrap(self.posthook, self, args)
        except TaskError as ex:
            logging.error("Task '%s' failed (%s)", self.name, ex.message)
            if not dragon.OPTIONS.keep_going:
                sys.exit(1)
        else:
            # Task is finished
            logging.info("Finished task '%s'", self.name)

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

    def _setup_extra_env(self):
        # Export parrot build properties
        if dragon.PARROT_BUILD_PROP_GROUP:
            self.extra_env["PARROT_BUILD_PROP_GROUP"] = dragon.PARROT_BUILD_PROP_GROUP
        if dragon.PARROT_BUILD_PROP_PROJECT:
            self.extra_env["PARROT_BUILD_PROP_PROJECT"] = dragon.PARROT_BUILD_PROP_PROJECT
        if dragon.PARROT_BUILD_PROP_PRODUCT:
            self.extra_env["PARROT_BUILD_PROP_PRODUCT"] = dragon.PARROT_BUILD_PROP_PRODUCT
        if dragon.PARROT_BUILD_PROP_VARIANT:
            self.extra_env["PARROT_BUILD_PROP_VARIANT"] = dragon.PARROT_BUILD_PROP_VARIANT
        if dragon.PARROT_BUILD_PROP_REGION:
            self.extra_env["PARROT_BUILD_PROP_REGION"] = dragon.PARROT_BUILD_PROP_REGION
        if dragon.PARROT_BUILD_PROP_UID:
            self.extra_env["PARROT_BUILD_PROP_UID"] = dragon.PARROT_BUILD_PROP_UID
        if dragon.PARROT_BUILD_PROP_VERSION:
            self.extra_env["PARROT_BUILD_PROP_VERSION"] = dragon.PARROT_BUILD_PROP_VERSION

        # Determine output directory
        if self.outsubdir:
            out_dir = os.path.join(dragon.OUT_DIR, self.outsubdir)
        else:
            out_dir = dragon.OUT_DIR

        # Export Alchemy variables
        self.extra_env["ALCHEMY_WORKSPACE_DIR"] = dragon.WORKSPACE_DIR
        self.extra_env["ALCHEMY_TARGET_PRODUCT"] = self.product
        self.extra_env["ALCHEMY_TARGET_PRODUCT_VARIANT"] = self.product_variant
        self.extra_env["ALCHEMY_TARGET_OUT"] = out_dir
        self.extra_env["ALCHEMY_TARGET_CONFIG_DIR"] = os.path.join(
                dragon.WORKSPACE_DIR, "products",
                self.product, self.product_variant, "config")

        # Only scan 'packages' sub-directory and exclude top directory (workspace)
        self.extra_env["ALCHEMY_TARGET_SCAN_PRUNE_DIRS"] = " ".join([
                os.environ.get("ALCHEMY_TARGET_SCAN_PRUNE_DIRS", ""),
                dragon.WORKSPACE_DIR])
        self.extra_env["ALCHEMY_TARGET_SCAN_ADD_DIRS"] = " ".join([
                os.environ.get("ALCHEMY_TARGET_SCAN_ADD_DIRS", ""),
                os.path.join(dragon.WORKSPACE_DIR, "packages")])

        # Use colors (unless already set or disabled, by jenkins for example)
        if not dragon.OPTIONS.colors:
            self.extra_env["ALCHEMY_USE_COLORS"] = "0"
        elif not os.environ.get("ALCHEMY_USE_COLORS", ""):
            self.extra_env["ALCHEMY_USE_COLORS"] = "1"

    def _do_exec(self, args=None):
        # Setup extra env
        self._setup_extra_env()
        cmd_args = []

        # jobs argument
        cmd_args.append(dragon.OPTIONS.jobs.make_arg)

        # Verbose
        if dragon.OPTIONS.verbose:
            cmd_args.append("V=1")

        # Get arguments from task if none provided
        if not args and self.defargs:
            cmd_args.extend(self.defargs)

        # Add given arguments
        if args:
            cmd_args.extend(args)

        # Execute command
        utils.exec_cmd("%s/scripts/alchemake %s" %
                (dragon.ALCHEMY_HOME, " ".join(cmd_args)),
                extra_env=self.extra_env)

    def get_var(self, varname):
        self.extra_env = {}
        self._setup_extra_env()
        output =  dragon.exec_shell("make -f %s/envsetup.mk var-%s" %
                (dragon.ALCHEMY_HOME, varname),
                extra_env=self.extra_env, single_line=False)
        for line in output.splitlines():
            if line.startswith(varname + "="):
                return line[len(varname)+1:]
        return None

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
        if self.subtasks:
            for subtask in self.subtasks:
                if subtask:
                    # Split subtask in name and arguments
                    subtaskargs = subtask.split(" ")
                    subtaskname = subtaskargs[0]
                    subtaskargs = subtaskargs[1:]
                    dragon.do_task(subtaskname, subtaskargs,
                            self.extra_env, self.top_info)

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
        self.defargs = defargs

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
        if not args and self.defargs:
            ProductTask._extend_args(cmd_args, self.defargs)

        # Add given arguments
        if args:
            ProductTask._extend_args(cmd_args, args)

        dragon.restart(dragon.OPTIONS, self.product, self.variant, cmd_args)
