
import sys
import os
import logging
import argparse
import json
import tempfile
import collections

from task import Hook as Hook
from task import TaskError as TaskError
from task import TaskExit as TaskExit
from task import Task as Task
from task import AlchemyTask as AlchemyTask
from task import MetaTask as MetaTask
from task import ProductTask as ProductTask

from utils import *

# Options (set by build.py)
OPTIONS = None

# Set workspace directory (go up relative to this script)
WORKSPACE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Global variables (some are initialized from environment)
PRODUCT = ""
VARIANT = ""
OUT_ROOT_DIR = os.environ.get("DRAGON_OUT_ROOT_DIR", "")
OUT_DIR = os.environ.get("DRAGON_OUT_DIR", "")
BUILD_DIR = ""
DEPLOY_DIR = os.environ.get("TARGET_DEPLOY_ROOT", "usr").strip("/")
STAGING_DIR = ""
FINAL_DIR = ""
IMAGES_DIR = ""
PRODUCT_DIR = ""
VARIANT_DIR = ""
RELEASE_DIR = ""

# Initialize Parrot build properties from environment
PARROT_BUILD_PROP_GROUP = os.environ.get("PARROT_BUILD_PROP_GROUP", "drones")
PARROT_BUILD_PROP_PROJECT = os.environ.get("PARROT_BUILD_PROP_PROJECT", "")
PARROT_BUILD_PROP_PRODUCT = os.environ.get("PARROT_BUILD_PROP_PRODUCT", "")
PARROT_BUILD_PROP_VARIANT = os.environ.get("PARROT_BUILD_PROP_VARIANT", "")
PARROT_BUILD_PROP_REGION = os.environ.get("PARROT_BUILD_PROP_REGION", "")
PARROT_BUILD_PROP_UID = os.environ.get("PARROT_BUILD_PROP_UID", "")
PARROT_BUILD_PROP_VERSION = os.environ.get("PARROT_BUILD_PROP_VERSION", "")
PARROT_BUILD_TAG_PREFIX = os.environ.get("PARROT_BUILD_TAG_PREFIX", "")

# Initialize directory where alchemy is from environment
ALCHEMY_HOME = os.environ.get("ALCHEMY_HOME", "")

# Initialize directory where police is from environment
POLICE_HOME = os.environ.get("POLICE_HOME", "")

POLICE_OUT_DIR = ""
POLICE_SPY_LOG = ""
POLICE_PROCESS_LOG = ""
POLICE_XML_LICENSES = []

# Log wrappers
LOGE = logging.error
LOGW = logging.warning
LOGI = logging.info
LOGD = logging.debug
LOGV = logging.debug

# List of registered tasks
_TASKS = {}

#===============================================================================
# Wrapper around argparse.ArgumentParser that raise an exception in case of
# error instead of exiting.
#===============================================================================
class TaskArgumentParser(argparse.ArgumentParser):
    def __init__(self, task, **kwargs):
        argparse.ArgumentParser.__init__(self,
                prog="./build.sh -p %s-%s -t %s" % (PRODUCT, VARIANT, task.name),
                description=task.desc,
                formatter_class=argparse.RawDescriptionHelpFormatter,
                **kwargs)
    def parse_args(self, args=None, namespace=None):
        try:
            return argparse.ArgumentParser.parse_args(self,
                    args=args, namespace=namespace)
        except SystemExit as ex:
            if ex.code == 0:
                raise TaskExit()
            else:
                raise TaskError("Parse args (code=%d)" % ex.code)
    def parse_known_args(self, args=None, namespace=None):
        try:
            return argparse.ArgumentParser.parse_known_args(self,
                    args=args, namespace=namespace)
        except SystemExit as ex:
            if ex.code == 0:
                raise TaskExit()
            else:
                raise TaskError("Parse args (code=%d)" % ex.code)
    def error(self, message):
        raise TaskError(message)

#===============================================================================
# Register a new task.
#===============================================================================
def add_task(task):
    if task.name in _TASKS:
        # Task with same name already exists, check weakness
        if not _TASKS[task.name].weak:
            # Previous task added is not weak !
            logging.warning("add_task: duplicate entry: '%s'", task.name)
        else:
            _TASKS[task.name] = task
    else:
        _TASKS[task.name] = task

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
# Get registered tasks.
#===============================================================================
def get_tasks():
    return _TASKS

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
        exechook=None, prehook=None, posthook=None, outsubdir=None):
    task = _TASKS.get(name, None)
    if not task:
        logging.warning("override_alchemy_task: unknown task: '%s'", name)
    elif not isinstance(task, AlchemyTask):
        logging.warning("override_alchemy_task: invalid alchemy task: '%s'", name)
    else:
        if defargs is not None:
            task.defargs = defargs
        if outsubdir is not None:
            task.outsubdir = outsubdir
        _override_task(task, desc, exechook, prehook, posthook)

#===============================================================================
# Override a meta task
#===============================================================================
def override_meta_task(name, desc=None, subtasks=None,
        exechook=None, prehook=None, posthook=None):
    task = _TASKS.get(name, None)
    if not task:
        logging.warning("override_meta_task: unknown task: '%s'", name)
    elif not isinstance(task, MetaTask):
        logging.warning("override_meta_task: invalid meta task: '%s'", name)
    else:
        if subtasks is not None:
            task.subtasks = subtasks
        _override_task(task, desc, exechook, prehook, posthook)

#===============================================================================
# Check that tasks are valid: metatask subtasks should exist.
# Recursion is not detected
#===============================================================================
def check_tasks():
    for task in _TASKS.values():
        if not isinstance(task, MetaTask):
            continue
        if not task.subtasks:
            continue
        for subtask in task.subtasks:
            if not subtask:
                continue
            subtaskname = subtask.split(" ")[0]
            if subtaskname not in _TASKS:
                logging.warning("Meta task '%s' uses unknown task '%s'",
                        task.name, subtaskname)

#===============================================================================
# Disable default tasks (it will actually remove all currently registered tasks)
#===============================================================================
def disable_def_tasks(keep_list=None):
    LOGD("Disable default tasks")
    if keep_list is None:
        _TASKS.clear()
    else:
        # Iterate over a copy of keys to be able to modify the dictionary
        for taskname in list(_TASKS.keys()):
            if taskname not in keep_list:
                del _TASKS[taskname]

#===============================================================================
# Start a task.
#===============================================================================
def do_task(taskname, args=None, extra_env=None, top_info=None):
    if taskname not in _TASKS:
        raise TaskError("Unknown task: '%s'" % taskname)
    if top_info is None:
        top_info = collections.namedtuple("TopInfo", "taskname, args")(taskname, args)
    _TASKS[taskname].execute(args, extra_env, top_info)

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
# Check that the build id is valid.
#===============================================================================
def check_build_id():
    if not PARROT_BUILD_PROP_UID:
        raise TaskError("Missing uid, please use -b option")

#===============================================================================
# Restart the build script with given product/variant
#===============================================================================
def restart(options, product, variant, args, docker_image=None):
    cmd_args = []
    cmd_args.append("-p %s-%s" % (product, variant))
    cmd_args.append("-j %s" % options.jobs.restart_arg)
    opt_args = [
        (options.verbose, "-v"),
        (options.keep_going, "-k"),
        (not options.colors, "--no-color"),
        (options.build_id, "-b %s" % options.build_id),
        (options.police, "--police"),
        (options.police_no_spy, "--police-no-spy"),
        (options.police_packages, "--police-packages"),
        (not docker_image and options.docker_image, "--docker %s" % options.docker_image),
    ]
    for opt, arg in opt_args:
        if opt:
            cmd_args.append(arg)

    if args:
        cmd_args.extend(args)

    if docker_image is None:
        prog = sys.argv[0]
    else:
        prog = "%s %s" % (
                os.path.join(os.path.dirname(__file__), "build-with-docker.sh"),
                docker_image)

    try:
        exec_cmd("%s %s" % (prog, " ".join(cmd_args)), dryrun_arg="-n")
    except TaskError as ex:
        logging.error(str(ex))
        if not options.keep_going:
            sys.exit(1)

#===============================================================================
# Get default docker image
#===============================================================================
def get_default_docker_image():
    json_cfg = get_json_config()
    if json_cfg is None or "docker_image" not in json_cfg:
        return None
    return json_cfg["docker_image"]

#===============================================================================
# Generate a manifest.xml from repo manifest command
# Takes a mandatory filepath as argument.
# Any file given will be erased if already existing.
#===============================================================================
def gen_manifest_xml(filepath):
    # Generate in a temp file, then move it
    if not os.path.exists(os.path.join(WORKSPACE_DIR, ".repo")):
        return
    tmpfilepath = tempfile.mkstemp(suffix=".xml")
    os.close(tmpfilepath[0])
    cmd = ("repo manifest "
            "--revision-as-HEAD "
            "--suppress-upstream-revision -o %s") % tmpfilepath[1]
    exec_cmd(cmd, extra_env={"GIT_PAGER": "cat"})
    exec_cmd("mv %s %s" % (tmpfilepath[1], filepath))

#===============================================================================
# Dump alchemy database in xml and return path to it
#===============================================================================
def gen_alchemy_dump_xml():
    exec_cmd(cmd="./build.sh -p %s-%s -A dump-xml" % (PRODUCT, VARIANT))
    return os.path.join(OUT_DIR, "alchemy-database.xml")

#===============================================================================
# Dump alchemy variable
#===============================================================================
def get_alchemy_var(varname):
    alchemy = get_tasks()["alchemy"]
    return alchemy.get_var(varname)

#===============================================================================
# Return the path of the product_config.json
#===============================================================================
def get_json_config_path(warn_if_not_found=False):
    search_paths = [
        os.path.join(OUT_DIR),
        os.path.join(WORKSPACE_DIR, "products", PRODUCT, VARIANT, "config"),
        os.path.join(WORKSPACE_DIR, "products", PRODUCT),
    ]

    json_name = "product_config.json"
    for dirpath in search_paths:
        json_path = os.path.join(dirpath, json_name)
        if os.path.exists(json_path):
            return json_path

    if warn_if_not_found:
        logging.warning("'%s' file not found", json_name)
    return None

#===============================================================================
# Return the product_config.json contents if found else None.
#===============================================================================
def get_json_config(warn_if_not_found=False):
    json_path = get_json_config_path(warn_if_not_found)
    if not json_path:
        return None
    with open(json_path, "r") as fd:
        try:
            return json.load(fd)
        except ValueError as ex:
            raise TaskError("Error while parsing json file %s : %s" %
                    (json_path, str(ex)))

#===============================================================================
# Add files in release directory. Symlinks will be created to avoid disk waste.
# Destination is always overwritten (warning is displayed if warn_on_overwrite
# is True).
#
# contents is a list of element
# {
#     "src": <path>,
#     "dest": <path>,
#     "mandatory": False
# }
#
# <path> can either be a directory or a file
# <src> if relative, it is from  OUT_DIR. It can also contains reference to
# special directory (${STAGING_DIR}...)
# <dest> is always relative to the release directory.
# <mandatory> if set to True (default), task will stop if source is missing.
#===============================================================================
def add_release_contents(contents, warn_on_exist=False):
    # Export some variables in environment to be used expanded in json
    oldenv = os.environ.copy()
    for _envvar in ["PARROT_BUILD_PROP_GROUP",
            "PARROT_BUILD_PROP_PROJECT",
            "PARROT_BUILD_PROP_PRODUCT",
            "PARROT_BUILD_PROP_VARIANT",
            "PARROT_BUILD_PROP_REGION",
            "PARROT_BUILD_PROP_UID",
            "PARROT_BUILD_PROP_VERSION",
            "WORKSPACE_DIR",
            "OUT_DIR"]:
        os.environ[_envvar] = globals().get(_envvar)

    for _elem in contents:
        src = os.path.expandvars(_elem["src"])
        dest = os.path.expandvars(_elem.get("dest", os.path.basename(src)))
        mandatory = _elem.get("mandatory", True)
        if not os.path.isabs(src):
            src = os.path.join(OUT_DIR, src)
        dest = os.path.join(RELEASE_DIR, dest)

        if os.path.exists(dest):
            if warn_on_exist:
                logging.warning("'%s' already exists", dest)
        elif os.path.exists(src):
            relative_symlink(src, dest)
        elif mandatory and not OPTIONS.dryrun:
            raise TaskError("'%s' file is missing" % src)

    # Restore environment
    os.environ.clear()
    os.environ.update(oldenv)

#===============================================================================
# Generate an archive for a version to be released.
#===============================================================================
def gen_release_archive():
    tmp_release_file = "%s.tar" % RELEASE_DIR
    release_file = os.path.join(WORKSPACE_DIR, "%s.tar" % PARROT_BUILD_PROP_UID)

    # Create base list of files for release
    contents = [
        {
            "src": "symbols-%s-%s.tar" % (PRODUCT, VARIANT),
            "dest": "symbols.tar",
            "mandatory": False,
        },
        {
            "src": "sdk-%s-%s.tar.gz" % (PRODUCT, VARIANT),
            "dest": "sdk.tar.gz",
            "mandatory": False,
        },
        {
            "src": "images",
        },
        {
            "src": "build.prop",
        },
        {
            "src": "manifest.xml",
        },
        {
            "src": "global.config",
            "dest": "config/global.config",
        },
        {
            "src": "build/linux/linux.config",
            "dest": "config/linux.config",
            "mandatory": False,
        },
        {
            "src": "police",
            "mandatory": False,
        },
        {
            "src": os.path.join(WORKSPACE_DIR, "build", "pinst_tools"),
            "mandatory": False,
        },
        {
            "src": "oss-packages",
            "mandatory": False,
        },
        {
            "src": os.path.join(WORKSPACE_DIR, "HOWTO"),
            "mandatory": False
        },
        {
            "src": "HOWTO_rebuild",
            "mandatory": False
        },
        {
            "src": os.path.join(WORKSPACE_DIR, PARROT_BUILD_PROP_UID + ".ods"),
            "mandatory": False
        },

    ]
    add_release_contents(contents)

    # Is there a 'product_config.json' ?
    json_path = get_json_config_path()
    json_cfg = get_json_config()
    if json_cfg:
        add_release_contents([{"src": json_path, "dest": "product_config.json"}])
        if "release" in json_cfg and "additional_files" in json_cfg["release"]:
            add_release_contents(json_cfg["release"]["additional_files"],
                    json_cfg["release"].get("warn_on_exist", False))

    # Disable police while generating the archive
    os.environ["POLICE_HOOK_DISABLED"] = "1"

    # Generate md5sum file
    exec_cmd("md5sum $(find . -follow  -name '.git*' -prune -or -type f -print) > md5sum.txt", cwd=RELEASE_DIR)

    # Archive the release (follow symlinks)
    exec_cmd("tar --exclude=.git -C %s -hcf %s ." % (RELEASE_DIR, tmp_release_file))

    # Do not create link at root of workspace if output dir is somewhere else
    # (jenkins for example)
    if OUT_DIR.startswith(WORKSPACE_DIR):
        relative_symlink(tmp_release_file, release_file)

    # Re-enable police once archive has been generated
    del os.environ["POLICE_HOOK_DISABLED"]

#===============================================================================
# Install locally a specfic version of debian packages  if needed.
# base_url: base url of the debian repository
# pkg_name: name of the package (without version, arch or .deb extension)
# pkg_version: version of the package.
# pkg_arch: architecture of the package (amd64 by default).
# extract_dir: wher the debian package will be installed.
# force: if True, package will be forcibly downloaded and extracted, otherwise
# nothing will be done if the extracted directory already exists.
#===============================================================================
def debian_install(base_url, pkg_name, pkg_version,
        pkg_arch=None, extract_dir=None, force=False):
    # Setup some default
    if pkg_arch is None:
        pkg_arch = "amd64"
    if extract_dir is None:
        extract_dir = os.path.join(WORKSPACE_DIR, "build", "debian-packages",
                pkg_name, pkg_version)

    # Remove existing extract directory if in 'force' mode
    if force and os.path.exists(extract_dir):
        exec_cmd("rm -rf %s" % extract_dir)

    # Construct package file name
    pkg_deb_filename = "%s_%s_%s.deb" % (pkg_name, pkg_version, pkg_arch)
    pkg_deb_path = os.path.join(WORKSPACE_DIR, "build", pkg_deb_filename)
    url = "%s/%s" % (base_url, pkg_deb_filename)

    # Check if we already have the binary
    if not os.path.exists(extract_dir):
        try:
            # Download debian package and extract it
            exec_cmd("wget %s -O %s" % (url, pkg_deb_path))
            makedirs(extract_dir)
            exec_cmd("dpkg -x %s %s" % (pkg_deb_path, extract_dir))
        finally:
            # Cleanup downloaded file (keep extracted dir though)
            exec_cmd("rm -f %s" % pkg_deb_path)
    return extract_dir
