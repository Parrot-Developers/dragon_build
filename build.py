#!/usr/bin/env python3

import sys
import os
import logging
import signal
import argparse
import datetime
import re
import importlib
import collections

# Don't pollute tree with pyc
sys.dont_write_bytecode = True

import dragon
import police

USAGE = (
    "  %(prog)s -h|--help\n"
    "    -> Display this help message.\n"
    "  %(prog)s -l\n"
    "    -> Display the list of available products/variants.\n"
    "  %(prog)s [-p <product>[-<variant>]] -t\n"
    "    -> Display the list of available tasks. Use -tt to also show secondary tasks.\n"
    "  %(prog)s [-p <product>[-<variant>]] [<options>] -A [<args>...]\n"
    "    -> Start alchemy build with given arguments.\n"
    "  %(prog)s [-p <product>[-<variant>]] [<options>] -t <task> [<taskargs>...]\n"
    "    -> Start a task and its sub tasks with given arguments.\n"
    "\n"
    " Multiple occurrences of -A and -t <task> can be present in the same command line.\n"
    "\n"
)

# Color definition
CLR_DEFAULT = "\033[00m"
CLR_RED = "\033[31m"
CLR_GREEN = "\033[32m"
CLR_YELLOW = "\033[33m"
CLR_BLUE = "\033[34m"
CLR_PURPLE = "\033[35m"
CLR_CYAN = "\033[36m"

#===============================================================================
# Get list of available entries (products/variants).
#===============================================================================
def get_dir_entries(dirpath):
    excludes = [".git", "__pycache__", "dragon_base", "common"]
    entries = []
    for entry in os.listdir(dirpath):
        if not os.path.isdir(os.path.join(dirpath, entry)):
            continue
        if entry in excludes:
            continue
        if os.path.exists(os.path.join(dirpath, entry, ".dragonignore")):
            continue
        # If default is link, ignore it (only the target of the link will be listed)
        if entry == "default" and os.path.islink(os.path.join(dirpath, entry)):
            continue
        entries.append(entry)
    return sorted(entries)

#===============================================================================
# Get default entry (product/variant).
# This gives something only if there is only one product available.
# If a product is named 'default' or has a symlink named 'default' pointing to it
# return it.
#===============================================================================
def get_default_entry(dirpath, entries):
    if len(entries) == 1:
        return entries[0]
    if "default" in entries:
        return "default"
    # Check if there is a symlink named default, return its target
    default_dirpath = os.path.join(dirpath, "default")
    if os.path.islink(default_dirpath):
        target = os.readlink(default_dirpath)
        if target in entries:
            return target
    return None

#===============================================================================
# Get list of available products.
#===============================================================================
def get_products():
    products_dir = os.path.join(dragon.WORKSPACE_DIR, "products")
    return get_dir_entries(products_dir)

#===============================================================================
# Get list of available variants.
#===============================================================================
def get_variants(product):
    variants_dir = os.path.join(dragon.WORKSPACE_DIR, "products", product)
    return get_dir_entries(variants_dir)

#===============================================================================
# Get default product.
# This gives something only if there is only one product available.
# If a product is named 'default' or has a symlink named 'default' pointing to it
# return it.
#===============================================================================
def get_default_product():
    products_dir = os.path.join(dragon.WORKSPACE_DIR, "products")
    return get_default_entry(products_dir, get_products())

#===============================================================================
# Get default variant.
# This gives something only if there is only one variant available.
# If a variant is named 'default' or has a symlink named 'default' pointing to it
# return it.
#===============================================================================
def get_default_variant(product):
    variants_dir = os.path.join(dragon.WORKSPACE_DIR, "products", product)
    return get_default_entry(variants_dir, get_variants(product))

#===============================================================================
# Check that given product is valid (picking default one if needed).
#===============================================================================
def check_product(options):
    if not options.product:
        options.product = get_default_product()
    if not options.product:
        logging.error("Missing product: %s", " ".join(get_products()))
        return False
    if options.product == "forall":
        return True

    # Check that product really exist
    products = get_products()
    if options.product in products:
        return True

    # Could it be a variant (if only one product or "default" exists) ?
    product = get_default_product()
    if options.variant is None and product is not None:
        variants = get_variants(product)
        if options.product in variants:
            options.variant = options.product
            options.product = product
            return True

    logging.error("'%s' is not a valid product", options.product)
    return False

#===============================================================================
# Check that given variant is valid (picking default one if needed).
#===============================================================================
def check_variant(options):
    if not options.variant:
        options.variant = get_default_variant(options.product)
    if not options.variant:
        logging.error("Missing variant: %s", " ".join(get_variants(options.product)))
        return False
    if options.variant == "forall":
        return True

    # Check that variant really exist
    variants = get_variants(options.product)
    if options.variant in variants:
        return True

    logging.error("'%s' is not a valid variant", options.variant)
    return False

#===============================================================================
# Parse the -j option in an actual number of jobs.
#===============================================================================
def parse_jobs(sval):
    # Compute the number of maximum possible jobs
    try:
        import multiprocessing
        max_jobs = multiprocessing.cpu_count()
    except (ImportError, NotImplementedError):
        max_jobs = 1

    JobInfo = collections.namedtuple("JobInfo", ["make_arg", "job_num", "restart_arg"])
    try:
        # Is it /X ?
        if sval.startswith("/"):
            # Divide max_jobs by the given number
            divisor = max(1, int(sval[1:]))
            jobs = (max_jobs + divisor - 1) // divisor
            return JobInfo("-j %d" % jobs, jobs, sval)
        ival = int(sval)
        if ival == 0:
            # Assume another way of computing jobs is wanted
            return JobInfo("-j -l %d" % max_jobs, max_jobs, sval)
        elif ival > 0:
            jobs = min(max_jobs, ival)
            return JobInfo("-j %d" % jobs, jobs, sval)
        else:
            jobs = max(1, max_jobs + ival)
            return JobInfo("-j %d" % jobs, jobs, sval)
    except ValueError:
        if sval == "__ALL_CPUS__":
            return JobInfo("-j %s" % max_jobs, max_jobs, "")
        # Unable to parse value
        logging.warning("Unable to parse -j option: '%s", sval)
        return JobInfo("-j 1", 1, sval)

#===============================================================================
# List all products (and variants)
#===============================================================================
def list_products():
    products = get_products()
    for product in products:
        sys.stderr.write(product)
        if product == get_default_product():
            sys.stderr.write("*")
        sys.stderr.write(":")
        variants = get_variants(product)
        for variant in variants:
            sys.stderr.write(" " + variant)
            if variant == get_default_variant(product):
                sys.stderr.write("*")
        sys.stderr.write("\n")
    sys.stderr.write("\n")
    sys.stderr.write("Default product is indicated with *\n")
    sys.stderr.write("Default variant for each product is indicated with *\n")

#===============================================================================
# List all available tasks.
#===============================================================================
def list_tasks(list_secondary_tasks):
    tasks = {}
    has_secondary_tasks = False
    for _, task in dragon.get_tasks().items():
        # Do not add hidden tasks(starting with '_')
        if task.name.startswith("_"):
            continue
        # Do not add secondary tasks if not asked
        if not list_secondary_tasks and task.secondary_help:
            has_secondary_tasks = True
            continue
        # OK, add task
        tasks[task.name] = task

    sys.stderr.write("Available tasks for %s-%s (%d):\n" %
            (dragon.PRODUCT, dragon.VARIANT, len(tasks)))

    for taskname in sorted(tasks.keys()):
        task = tasks[taskname]
        sys.stderr.write("  %s : %s%s%s\n" %
                (task.name, CLR_BLUE, task.desc, CLR_DEFAULT))

    if has_secondary_tasks:
        sys.stderr.write("\nPlease use './build.sh -p %s-%s -tt' "
                "to list all available tasks.\n" %
                (dragon.PRODUCT, dragon.VARIANT))

#===============================================================================
# Generate completion file for dragon product
#===============================================================================
def gen_completion():
    filepath = os.path.join(dragon.PRODUCT_DIR, "%s_completion.bash" % dragon.PRODUCT)

    # List of tasks, excluding hidden ones
    tasks = [x for x in sorted(dragon.get_tasks().keys()) if not x.startswith("_")]
    contents = ("#!/bin/bash\n\n"
            "# This file is automatically generated by "
            "./build.sh -p %s-%s --gen-completion.\n"
            "_%s_completion () {\n"
            "    # complete targets for common\n"
            "    local cur opts;\n"
            "    cur=\"${COMP_WORDS[COMP_CWORD]}\"\n"
            "    # Automatically generated list.\n"
            "    opts=\"%s\"\n"
            "    COMPREPLY=( $(compgen -W \"${opts}\" -- ${cur}) )\n"
            "    return 0;\n"
            "}\n\n"
            "# Note that no two completion for build.sh can coexist.\n"
            "complete -F _%s_completion ./build.sh\n"
            "#END\n") % (dragon.PRODUCT, dragon.VARIANT, dragon.PRODUCT,
                    " ".join(tasks), dragon.PRODUCT)
    with open(filepath, "w") as fd:
        fd.write(contents)
    logging.info("Completion file: '%s'", filepath)

#===============================================================================
# Restart the build script with given product/variant
#===============================================================================
def restart(options, tasks, product, variant, docker_image=None):
    args = []
    for _task in tasks:
        args.append("-t %s" % _task["name"])
        args.extend(_task["args"])
    dragon.restart(options, product, variant, args, docker_image)

#===============================================================================
#===============================================================================
def setup_globals(options):
    # Force error messages of sub processes to English, keeping encoding to UTF-8
    # LANG=C.UTF8 does NOT work as expected (messages are still in original locale)
    os.environ["LC_MESSAGES"] = "C"
    os.environ["LC_TIME"] = "C"

    # Setup product/variant
    dragon.PRODUCT = options.product
    dragon.VARIANT = options.variant
    dragon.PRODUCT_DIR = options.product_dir
    dragon.VARIANT_DIR = options.variant_dir
    if not dragon.PARROT_BUILD_PROP_PRODUCT:
        dragon.PARROT_BUILD_PROP_PRODUCT = dragon.PRODUCT
    if not dragon.PARROT_BUILD_PROP_VARIANT:
        dragon.PARROT_BUILD_PROP_VARIANT = dragon.VARIANT

    # Project is set to product by default
    if not dragon.PARROT_BUILD_PROP_PROJECT:
        dragon.PARROT_BUILD_PROP_PROJECT = dragon.PARROT_BUILD_PROP_PRODUCT

    if not dragon.PARROT_BUILD_TAG_PREFIX:
        dragon.PARROT_BUILD_TAG_PREFIX = dragon.PARROT_BUILD_PROP_PRODUCT

    # Get uid from command line overwrite if not given in environment
    if options.build_id and not dragon.PARROT_BUILD_PROP_UID:
        dragon.PARROT_BUILD_PROP_UID = options.build_id

    # If no uid and no version given, get a default version
    if not dragon.PARROT_BUILD_PROP_VERSION and not dragon.PARROT_BUILD_PROP_UID:
        # Use the version indicated in next-version if available
        next_version_file = None
        if dragon.PRODUCT_DIR:
            next_version_file = os.path.join(dragon.PRODUCT_DIR, "next-version")
        if next_version_file and os.path.exists(next_version_file):
            with open(next_version_file, "r") as fd:
                dragon.PARROT_BUILD_PROP_VERSION = fd.read().strip("\n")
        else:
            dragon.PARROT_BUILD_PROP_VERSION = "0.0.0"

    # If no version but uid, extract version from uid
    # format: <prefix>-MAJOR.MINOR.RELEASE[-extra]
    # version will be MAJOR.MINOR.RELEASE[-extra]
    if not dragon.PARROT_BUILD_PROP_VERSION:
        assert dragon.PARROT_BUILD_PROP_UID
        match = re.match(r"^(?:.*-)?((\d+\.\d+\.\d+)(-.*)?)$",
                         dragon.PARROT_BUILD_PROP_UID)
        if not match:
            dragon.PARROT_BUILD_PROP_VERSION = "0.0.0"
            logging.warning("Unable to extract version from UID (%s).",
                    dragon.PARROT_BUILD_PROP_UID)
        else:
            dragon.PARROT_BUILD_PROP_VERSION = match.group(1)

    # Construct a default uid based on product/variant/version/date
    if not dragon.PARROT_BUILD_PROP_UID:
        dragon.PARROT_BUILD_PROP_UID = "%s-%s-%s-%s" % (
                dragon.PARROT_BUILD_PROP_PRODUCT,
                dragon.PARROT_BUILD_PROP_VARIANT,
                datetime.datetime.now().strftime("%Y%m%d-%H%M"),
                dragon.PARROT_BUILD_PROP_VERSION)

    # Synchronize option with variable for uid
    options.build_id = dragon.PARROT_BUILD_PROP_UID

    # Setup directories
    if not dragon.OUT_ROOT_DIR:
        dragon.OUT_ROOT_DIR = os.path.join(dragon.WORKSPACE_DIR, "out")
    if not dragon.OUT_DIR:
        dragon.OUT_DIR = dragon.get_out_dir(dragon.PRODUCT, dragon.VARIANT)
    dragon.BUILD_DIR = os.path.join(dragon.OUT_DIR, "build")
    dragon.STAGING_DIR = os.path.join(dragon.OUT_DIR, "staging")
    dragon.FINAL_DIR = os.path.join(dragon.OUT_DIR, "final")
    dragon.IMAGES_DIR = os.path.join(dragon.OUT_DIR, "images")
    dragon.RELEASE_DIR = os.path.join(dragon.OUT_DIR,
            "release-%s" % dragon.PARROT_BUILD_PROP_UID)

    # Directory where alchemy is (and re-export it in environment)
    if not dragon.ALCHEMY_HOME:
        dragon.ALCHEMY_HOME = os.path.join(dragon.WORKSPACE_DIR, "build", "alchemy")
    if not os.path.isdir(dragon.ALCHEMY_HOME):
        logging.warning("Alchemy not found at '%s'", dragon.ALCHEMY_HOME)
    os.environ["ALCHEMY_HOME"] = dragon.ALCHEMY_HOME

    # Directory where police is (and re-export it in environment)
    if not dragon.POLICE_HOME:
        dragon.POLICE_HOME = os.path.join(dragon.WORKSPACE_DIR, "build", "police")
    if not os.path.isdir(dragon.POLICE_HOME) and options.police:
        logging.warning("Police not found at '%s'", dragon.POLICE_HOME)
        options.police = False
    os.environ["POLICE_HOME"] = dragon.POLICE_HOME
    dragon.POLICE_OUT_DIR = os.path.join(dragon.OUT_DIR, "police")
    dragon.POLICE_SPY_LOG = os.path.join(dragon.POLICE_OUT_DIR, "police-spy.log")
    dragon.POLICE_PROCESS_LOG = os.path.join(dragon.POLICE_OUT_DIR, "police-process.log")

    # Setup police spy if needed
    if options.police and not options.police_no_spy:
        police.setup_spy()

#===============================================================================
# Parse command line arguments and return options and list of tasks to execute.
#===============================================================================
def parse_args(extensions):
    # Help option is disabled in standard parser, it will be handled in extra
    # parser (the help option can be associated with a task)
    parser = argparse.ArgumentParser(usage=USAGE, add_help=False)

    parser.add_argument("-l", "--list",
            dest="list_products",
            action="store_true",
            help="Display the list of available products/variants")

    parser.add_argument("-p", "--product",
            dest="product",
            action="store",
            help="<product>-<variant> to use. product/variant can be omitted "
                    "if only one or defaut is available. "
                    "Can be <product>-forall or forall to launch multiple builds.")

    parser.add_argument("-b", "--build-id",
            dest="build_id",
            action="store",
            help="Build id. "
                    "Default will be <product>-<variant>-0.0.0-<datetime>.")

    parser.add_argument("-j", "--jobs",
            dest="jobs",
            nargs="?",
            default="1",
            const="__ALL_CPUS__",
            help="Number of concurrent jobs during build. Default is 1. "
                    "If no value is provided, the maximum umber of cpu is used. "
                    "If 0 is provided, we instead pass -l to make. "
                    "It also accepts the special format /X meaning max/X.")

    parser.add_argument("-v", "--verbose",
            dest="verbose",
            action="store_true",
            help="Be more verbose in logs.")

    parser.add_argument("-n", "--dry-run",
            dest="dryrun",
            action="store_true",
            help="Dry run, don't execute commands, just print them.")

    parser.add_argument("-k", "--keep-going",
            dest="keep_going",
            action="store_true",
            help="Keep going, don't stop if a task fails.")

    parser.add_argument("--no-color",
            dest="colors",
            action="store_false",
            default=True,
            help="Disable the use of color in logs.")

    parser.add_argument("--gen-completion",
            dest="gen_completion",
            action="store_true",
            help="Generate shell completion script.")

    parser.add_argument("--police",
            dest="police",
            action="store_true",
            help="Enable police spy and report.")

    parser.add_argument("--police-no-spy",
            dest="police_no_spy",
            action="store_true",
            help="When police is enabled, disable spy and only enable report.")

    parser.add_argument("--police-packages",
            dest="police_packages",
            action="store_true",
            help="When police is enabled, also enable packages generation.")

    parser.add_argument("--docker",
            dest="docker_image",
            nargs="?",
            metavar="IMAGE",
            const="__USE_DEFAULT__",
            default=None,
            help="Use a docker container for the build. "
                    "Default image depends on product/variant.")

    call_extensions(extensions, "setup_argparse", parser)

    # Parse standard arguments and extra arguments
    options, args = parser.parse_known_args()
    tasks = parse_extra_args(parser, options, args)

    # Print help how if requested
    if options.help_asked:
        parser.print_help()
        parser.exit()

    return options, tasks

#===============================================================================
# Parse extra arguments and return the list of tasks to execute.
#===============================================================================
def parse_extra_args(parser, options, args):
    # Add extra options
    options.list_tasks = False
    options.list_secondary_tasks = False
    options.help_asked = False

    # Process remaining non standard arguments
    tasks = []
    curtask = -1
    skipnext = False
    for argidx in range(0, len(args)):
        # Skip next argument if requested
        if skipnext:
            skipnext = False
            continue

        arg = args[argidx]
        if arg == "-A":
            # Shortcut for -t alchemy
            tasks.append({"name": "alchemy", "args": []})
            curtask += 1
        elif arg == "-t":
            # If a name is given add a task otherwise simply list them
            if argidx + 1 < len(args) and not args[argidx + 1].startswith("-"):
                tasks.append({"name": args[argidx + 1], "args": []})
                curtask += 1
                skipnext = True
            else:
                options.list_tasks = True
        elif arg == "-tt":
            # List all tasks including secondary ones
            options.list_tasks = True
            options.list_secondary_tasks = True
        elif arg == "-h" or arg == "--help":
            # If a task has been specified, assumed help of task is requested
            if curtask >= 0:
                tasks[curtask]["args"].append(arg)
            else:
                options.help_asked = True
        elif arg.upper().startswith("V="):
            options.verbose = arg[2:] != "0"
        else:
            # Add to current task or print error
            if curtask >= 0:
                tasks[curtask]["args"].append(arg)
            else:
                parser.error("Unknown argument '%s', -t or -A missing." % arg)

    return tasks

#===============================================================================
# Setup logging with given options.
#===============================================================================
def setup_log(options):
    # Return color 'clr' or empty depending on 'colors' option
    getclr = lambda clr: clr if options.colors else ""

    # Setup basic log, with custom format and default level depending on verbose
    logging.basicConfig(
            level=(logging.DEBUG if options.verbose else logging.INFO),
            format="%(levelname)s %(message)s" + getclr(CLR_DEFAULT),
            stream=sys.stderr)
    logging.addLevelName(logging.CRITICAL, getclr(CLR_RED) + "[C]")
    logging.addLevelName(logging.ERROR, getclr(CLR_RED) + "[E]")
    logging.addLevelName(logging.WARNING, getclr(CLR_YELLOW) + "[W]")
    logging.addLevelName(logging.INFO, getclr(CLR_GREEN) + "[I]")
    logging.addLevelName(logging.DEBUG, "[D]")

#===============================================================================
# Load extensions. Search files named 'buildext.py' in sibling directories of
# this script's parent directory.
#===============================================================================
def load_extensions():
    parent_dir = os.path.dirname(__file__)
    extensions = []
    extensions_dirpath = os.path.abspath(os.path.join(parent_dir, ".."))
    buildext_name = "buildext.py"
    sys.path.append(extensions_dirpath)
    for entry in sorted(os.listdir(extensions_dirpath)):
        if entry != os.path.basename(parent_dir):
            buildext_path = os.path.join(extensions_dirpath, entry, buildext_name)
            if os.path.exists(buildext_path):
                # Import and save module
                extension = importlib.import_module(
                        entry + "." + os.path.splitext(buildext_name)[0])
                extensions.append(extension)
    return extensions

#===============================================================================
# Call the given function for all loaded extensions
#===============================================================================
def call_extensions(extensions, fct, *args):
    for extension in extensions:
        if hasattr(extension, fct):
            getattr(extension, fct)(*args)

#===============================================================================
#===============================================================================
def main():
    # Signal handler (avoid displaying python backtrace when interrupted)
    def signal_handler(_sig, _frame):
        sys.exit(0)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Load extensions
    extensions = load_extensions()

    # Parse options/tasks
    options, tasks = parse_args(extensions)
    setup_log(options)
    options.jobs = parse_jobs(options.jobs)
    dragon.OPTIONS = options

    # We can log now that logging was correctly setup
    for extension in extensions:
        logging.debug("Loaded extension '%s'", extension.__file__)

    # Extract product and variant from -p option
    if options.product is not None:
        idx = options.product.rfind("-")
        if idx >= 0:
            options.variant = options.product[idx+1:]
            options.product = options.product[:idx]
        elif options.product == "forall":
            options.variant = "forall"
        else:
            options.variant = None
    else:
        options.variant = None
    options.product_dir = None
    options.variant_dir = None

    if sys.platform != "win32" and os.geteuid() == 0:
        logging.error("Please do not run this script as root.")
        sys.exit(1)

    # List products and exit
    if options.list_products:
        list_products()
        sys.exit(0)

    # Check product/variant
    if not check_product(options) or not check_variant(options):
        sys.exit(1)
    if options.product != "forall":
        options.product_dir = os.path.join(dragon.WORKSPACE_DIR,
                "products", options.product)
    if options.variant != "forall":
        options.variant_dir = os.path.join(dragon.WORKSPACE_DIR,
                "products", options.product, options.variant)

    # Setup global variables (directories...)
    setup_globals(options)

    # Now that product/variant is set in global variables, get default docker
    # image to use if asked
    if options.docker_image == "__USE_DEFAULT__":
        options.docker_image = dragon.get_default_docker_image()
        if options.docker_image is None:
            logging.error("No default docker image for %s-%s",
                    dragon.PRODUCT, dragon.VARIANT)
            sys.exit(1)

    # Import default tasks
    import deftasks
    call_extensions(extensions, "setup_deftasks")

    # Import optional product configuration (search variant dir then product dir)
    buildcfg_name = "buildcfg.py"
    for dirpath in [options.variant_dir, options.product_dir]:
        if dirpath:
            buildcfg_path = os.path.join(dirpath, buildcfg_name)
            if os.path.exists(buildcfg_path):
                logging.debug("Importing '%s'", buildcfg_path)
                sys.path.append(os.path.dirname(buildcfg_path))
                importlib.import_module(os.path.splitext(buildcfg_name)[0])
                break

    # Check all tasks
    dragon.check_tasks()

    # List tasks and exit
    if options.list_tasks:
        list_tasks(options.list_secondary_tasks)
        sys.exit(0)

    # Generate completion file based on product
    if options.gen_completion:
        gen_completion()
        sys.exit(0)

    # Build given tasks
    if not tasks:
        logging.error("No task given ! Please use -t option to have a list "
                "of available tasks for your product.")
        sys.exit(1)

    if options.product == "forall":
        for product in get_products():
            restart(options, tasks, product, "forall")
    elif options.variant == "forall":
        variants = get_variants(options.product)
        for variant in variants:
            restart(options, tasks, options.product, variant)
    else:
        try:
            # If a docker image is specified, restart inside it
            if options.docker_image is not None:
                restart(options, tasks, options.product, options.variant,
                        options.docker_image)
            else:
                for task in tasks:
                    dragon.do_task(task["name"], task["args"])
        except dragon.TaskError as ex:
            logging.error(str(ex))
            if not options.keep_going:
                sys.exit(1)

#===============================================================================
#===============================================================================
if __name__ == "__main__":
    main()
