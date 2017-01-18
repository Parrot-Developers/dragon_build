#!/usr/bin/env python2

import sys, os, logging
import signal
import datetime
from multiprocessing import Pool

# Don't pollute tree with pyc
sys.dont_write_bytecode = True

import dragon

# Script usage
USAGE = (
    "Usage:\n"
    "  {0} -h|--help\n"
    "    -> Display this help message.\n"
    "  {0} -l\n"
    "    -> Display the list of available products/variants.\n"
    "  {0} [-p <product>[-<variant>]] -t\n"
    "    -> Display the list of available tasks. Use -tt to also show secondary tasks.\n"
    "  {0} [-p <product>[-<variant>]] [<options>] -A [<args>...]\n"
    "    -> Start alchemy build with given arguments.\n"
    "  {0} [-p <product>[-<variant>]] [<options>] -t <task> [<taskargs>...]... \n"
    "    -> Start a task and its sub tasks with given arguments.\n"
    "\n"
    " Multiple occurences of -A and -t <task> can be present in the same command line.\n"
    "\n"
    "  <product> : Product to use. Can be omitted if only one available.\n"
    "  <variant> : Variant of product. Can be omitted if only one available.\n"
    "  <task>    : Name of the task to execute.\n"
    "              sub tasks will also be executeed.\n"
    "  <args>    : Arguments to give to alchemy build system.\n"
    "  <taskargs>: Extra arguments to give to a task and its sub tasks.\n"
    "              They will overwrite arguments given in task registration\n"
    "              unless -a is given.\n"
    "  -j[<jobs>]: Number of concurrent jobs during build. Default is 1.\n"
    "              If no value is provided, the maximum possible is used.\n"
    "              It also accepts the special character /X where X shall be"
    " an even number, allowing using max/X.\n"
    "  -v|v=1|V=1: Enable verbose mode.\n"
    "  -n        : Dry run, don't execute commands, just print them.\n"
    "  -a        : Append arguments of command line with default arguments\n"
    "              given in task registration. Without this, command line\n"
    "              arguments overwrite them.\n"
    "  -b        : Specify a build id. Default is based on the latest tag\n"
    "              found on the manifest of the repo if any.\n"
    "  -k        : Keep going, don't stop if a task fails.\n"
    "  --no-color: inhibits use of colors. (suited for jenkins logs)\n"
    "  --parallel-variants: Build variants in parallel when variant is forall.\n"
    "\n"
).format(os.path.basename(__file__))

# Color definition
CLR_DEFAULT = "\033[00m"
CLR_RED = "\033[31m"
CLR_GREEN = "\033[32m"
CLR_YELLOW = "\033[33m"
CLR_BLUE = "\033[34m"
CLR_PURPLE = "\033[35m"
CLR_CYAN = "\033[36m"

#===============================================================================
# Options parser.
#===============================================================================
class Options(object):
    def __init__(self):
        self.list_products = False
        self.list_tasks = False
        self.list_secondary_tasks = False
        self.product = None
        self.variant = None
        self.product_dir = None
        self.variant_dir = None
        self.colors = True
        self.jobs = 1
        self.verbose = False
        self.dryrun = False
        self.append_args = False
        self.build_id = None
        self.help_asked = False
        self.keep_going = False
        self.police = False
        self.police_no_spy = False
        self.police_packages = False
        self.generate_completion = False
        self.parallel_variants = False
        self.tasks = []
        self.args = []

        self._argv = None
        self._argidx = 0
        self._skipnext = False
        self._curtask = -1

    # Get the next argument
    def _get_next_arg(self):
        if self._argidx + 1 < len(self._argv):
            self._skipnext = True
            return self._argv[self._argidx + 1]
        else:
            return ""

    # Get value associated with an option in an argument
    def _get_opt_value(self, arg, opt):
        # Value can be just after the option or in the next argument
        value = arg.split(opt, 1)[1]
        if value.startswith("="):
            value = value[1:]
        elif value == "":
            value = self._get_next_arg()
        return value

    def _set_task(self, name, args=None):
        # To make sure we have a correctly initialized argument table
        if args is None:
            args = []
        self._curtask = len(self.tasks)
        self.tasks.append({ "name": name, "args": args })

    # Process an argument
    def _process_arg(self, arg):
        if arg == "-l":
            self.list_products = True
        elif arg.startswith("-b"):
            self.build_id = self._get_opt_value(arg, "-b")
        elif arg.startswith("-j"):
            max_jobs = 1

            # Compute the number of maximum possible jobs
            try:
                import multiprocessing
                max_jobs = multiprocessing.cpu_count()
            except (ImportError, NotImplementedError):
                pass

            job_computation = False
            divisor = 0
            try:
                jobsarg = self._get_opt_value(arg, "-j")
                self.jobs = int(jobsarg)
                if self.jobs < 1:
                    job_computation = True
            except ValueError:
                # -j is given without arguments,
                # so we do not skip the next argument
                self._skipnext = False
                divisor = 1
                if jobsarg.startswith("/"):
                    divisor = int(jobsarg[1:])
                    # Skip if '-j /X' and not if '-j/X'
                    if "/" not in arg:
                        self._skipnext = True

                # Need specific operation of jobs
                job_computation = True

            # In case of a division or a negative job argument
            # Note that the value obtained can't be inferior to 1
            if job_computation is True:
                if divisor == 0:
                    self.jobs = max(max_jobs + int(jobsarg), 1)
                else:
                    self.jobs = (max_jobs + divisor - 1) // divisor

        elif arg == "-A":
            self._set_task("alchemy")
        elif arg == "-t":
            if self._argidx + 1 < len(self._argv):
                # Get task name
                taskname = self._get_opt_value(arg, "-t")
                self._set_task(taskname)
            else:
                # Last argument, simply list tasks
                self.list_tasks = True
        elif arg == "-tt":
            self.list_tasks = True
            self.list_secondary_tasks = True
        elif arg.startswith("-p"):
            # Extract product and variant from argument
            self.product = self._get_opt_value(arg, "-p")
            idx = self.product.rfind("-")
            if idx >= 0:
                self.variant = self.product[idx+1:]
                self.product = self.product[:idx]
            elif self.product == "forall":
                self.variant = "forall"
        elif arg == "-v":
            self.verbose = True
        elif arg.startswith("v="):
            self.verbose = (self._get_opt_value(arg, "v=") == "1")
        elif arg.startswith("V="):
            self.verbose = (self._get_opt_value(arg, "V=") == "1")
        elif arg == "-n":
            self.dryrun = True
        elif arg == "-a":
            self.append_args = True
        elif arg == "-k":
            self.keep_going = True
        elif arg == "--police":
            self.police = True
        elif arg == "--no-color":
            self.colors = False
            os.environ["ALCHEMY_USE_COLORS"] = "0"
        elif arg == "--police-no-spy":
            self.police_no_spy = True
        elif arg == "--police-packages":
            self.police_packages = True
        elif arg == "--gen-completion":
            self.generate_completion = True
        elif arg == "-h" or arg == "--help":
            # If a task has been specified, assumed help of task is requested
            if self._curtask >= 0:
                self.tasks[self._curtask]["args"].append(arg)
            else:
                self.help_asked = True
        elif arg == "--parallel-variants":
            self.parallel_variants = True
        else:
            # Add to current task/general arguments
            if self._curtask >= 0:
                self.tasks[self._curtask]["args"].append(arg)
            else:
                sys.stderr.write("You shall not give arg without associated -t or -A option.\n")
                sys.exit(1)

    # Parse command line
    def parse(self, argv):
        self._argv = argv
        # Process arguments, skipping the first one (the command executed)
        for self._argidx in range(1, len(self._argv)):
            arg = self._argv[self._argidx]
            if self._skipnext == True:
                self._skipnext = False
            else:
                self._process_arg(arg)

#===============================================================================
# Display program usage.
#===============================================================================
def usage():
    sys.stderr.write(USAGE)

#===============================================================================
# Get list of available products (excluding 'dragon_base').
#===============================================================================
def get_products():
    excludes = [".git", "dragon_base"]
    products = []
    products_dir = os.path.join(dragon.WORKSPACE_DIR, "products")
    entries = os.listdir(products_dir)
    for entry in entries:
        if not os.path.isdir(os.path.join(products_dir, entry)):
            continue
        if entry in excludes:
            continue
        if os.path.exists(os.path.join(products_dir, entry, ".dragonignore")):
            continue
        # If default is link, ignore it (only the target of the link will be listed)
        if entry == "default" and os.path.islink(os.path.join(products_dir, entry)):
            continue
        products.append(entry)
    return products

#===============================================================================
# Get list of available variants (excluding 'common').
#===============================================================================
def get_variants(product):
    excludes = [".git", "common"]
    variants = []
    variants_dir = os.path.join(dragon.WORKSPACE_DIR, "products", product)
    entries = os.listdir(variants_dir)
    for entry in entries:
        if not os.path.isdir(os.path.join(variants_dir, entry)):
            continue
        if entry in excludes:
            continue
        if os.path.exists(os.path.join(variants_dir, entry, ".dragonignore")):
            continue
        # If default is link, ignore it (only the target of the link will be listed)
        if entry == "default" and os.path.islink(os.path.join(variants_dir, entry)):
            continue
        variants.append(entry)
    return variants

#===============================================================================
# Get default product.
# This gives something only if there is only one product available.
# If a product is named 'default' or has a symlink named 'default' pointing to it
# return it.
#===============================================================================
def get_default_product():
    products = get_products()
    if len(products) == 1:
        return products[0]
    if "default" in products:
        return "default"
    # Check if there is a symlink named default, return its target
    default_dirpath = os.path.join(dragon.WORKSPACE_DIR, "products", "default")
    if os.path.islink(default_dirpath):
        target = os.readlink(default_dirpath)
        if target in products:
            return target
    return None

#===============================================================================
# Get default variant.
# This gives something only if there is only one variant available.
# If a variant is named 'default' or has a symlink named 'default' pointing to it
# return it.
#===============================================================================
def get_default_variant(product):
    variants = get_variants(product)
    if len(variants) == 1:
        return variants[0]
    if "default" in variants:
        return "default"
    # Check if there is a symlink named default, return its target
    default_dirpath = os.path.join(dragon.WORKSPACE_DIR, "products", product, "default")
    if os.path.islink(default_dirpath):
        target = os.readlink(default_dirpath)
        if target in variants:
            return target
    return None

#===============================================================================
# List all available tasks.
#===============================================================================
def list_tasks(list_secondary_tasks):
    tasks = dragon.get_tasks()

    # Remove tasks from list to have a real total
    has_secondary_tasks = False
    for taskname in tasks.keys():
        # Remove hidden tasks from the list
        if taskname.startswith("_"):
            tasks.pop(taskname)
        # Remove secondary tasks if not asked
        if not list_secondary_tasks and tasks[taskname].secondary_help:
            has_secondary_tasks = True
            tasks.pop(taskname)

    sys.stderr.write("Available tasks for %s-%s (%d):\n" % (
            dragon.PRODUCT, dragon.VARIANT, len(tasks)))
    for taskname in sorted(tasks.keys()):
        task = tasks[taskname]
        sys.stderr.write("  %s : %s%s%s\n" %
            (task.name, CLR_BLUE, task.desc, CLR_DEFAULT))
    if has_secondary_tasks:
        sys.stderr.write(
                "\nPlease use './build.sh -p %s-%s -tt' to list all available tasks.\n" %
                (dragon.PRODUCT, dragon.VARIANT))

#===============================================================================
# Generate completion file for dragon product
#===============================================================================
def generate_completion():
    filepath = os.path.join(
            dragon.PRODUCT_DIR, "%s_completion.bash" % dragon.PRODUCT)

    # list of tasks, excluding hidden ones
    tasks = [ x for x in dragon.get_tasks().keys() if not x.startswith("_")]
    completion_text = '#!/bin/bash\n\n' \
            '# This file is automatically generated by ' \
            './build.sh --gen-completion.\n' \
            '_%s_completion () {\n' \
            '    # complete targets for common\n' \
            '    local cur opts;\n' \
            '    cur="${COMP_WORDS[COMP_CWORD]}"\n' \
            '    # Automatically generated list.\n' \
            '    opts="%s"\n' \
            '    COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )\n' \
            '    return 0;\n' \
            '}\n\n' \
            '# Note that no two completion for build.sh can coexist.\n' \
            'complete -F _%s_completion ./build.sh\n' \
            '#END\n' % (dragon.PRODUCT, " ".join(tasks), dragon.PRODUCT)
    with open(filepath, "wb") as compfp:
        compfp.write(completion_text)

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
# Restart the build script with given product/variant
#===============================================================================
def restart(options, product, variant):
    args = []
    args.extend(options.args)
    for _task in options.tasks:
        args.append("-t %s" % _task["name"])
        args.extend(_task["args"])
    dragon.restart(options, product, variant, args)

#===============================================================================
# Setup logging with given options.
#===============================================================================
def setup_log(options):
    if options.colors:
        fmt = "%(levelname)s %(message)s" + CLR_DEFAULT
        logging.addLevelName(logging.CRITICAL, CLR_RED + "[C]")
        logging.addLevelName(logging.ERROR, CLR_RED + "[E]")
        logging.addLevelName(logging.WARNING, CLR_YELLOW + "[W]")
        logging.addLevelName(logging.INFO, CLR_GREEN + "[I]")
        logging.addLevelName(logging.DEBUG, "[D]")
    else:
        fmt = "%(levelname)s %(message)s"
        logging.addLevelName(logging.CRITICAL, "[C]")
        logging.addLevelName(logging.ERROR, "[E]")
        logging.addLevelName(logging.WARNING, "[W]")
        logging.addLevelName(logging.INFO, "[I]")
        logging.addLevelName(logging.DEBUG, "[D]")

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(fmt=fmt))

    logging.root.addHandler(handler)
    if options.verbose:
        logging.root.setLevel(logging.DEBUG)
    else:
        logging.root.setLevel(logging.INFO)

#===============================================================================
# Setup police environment variables for spy.
# This shall be kept in sync with what is done in police-spy.sh
#===============================================================================
def setup_police_spy():
    if "police-hook.so" in os.environ.get("LD_PRELOAD", ""):
        return
    # Setup env variables
    os.environ["LD_PRELOAD"] = "police-hook.so"
    ldlibpath = [
            os.environ.get("LD_LIBRARY_PATH", ""),
            os.path.join(dragon.POLICE_HOME, "hook", "lib32"),
            os.path.join(dragon.POLICE_HOME, "hook", "lib64"),
    ]
    os.environ["LD_LIBRARY_PATH"] = ":".join(ldlibpath)
    os.environ["POLICE_HOOK_LOG"] = dragon.POLICE_SPY_LOG
    os.environ["POLICE_HOOK_RM_SCRIPT"] = os.path.join(dragon.POLICE_HOME, "police-rm.sh")
    os.environ["POLICE_HOOK_NO_ENV"] = "1"
    # Setup directory
    dragon.makedirs(os.path.dirname(dragon.POLICE_SPY_LOG))

    # Keep previous logs. Spy will append to existing if any
    # If a fresh spy is required, user shall clean it before
    if not os.path.exists(dragon.POLICE_SPY_LOG):
        fd = open(dragon.POLICE_SPY_LOG, "w")
        fd.close()

#===============================================================================
#===============================================================================
def setup_globals(options):
    os.environ["LANG"] = "C"

    # Setup product/variant
    dragon.PRODUCT = options.product
    dragon.VARIANT = options.variant
    dragon.PRODUCT_DIR = options.product_dir
    dragon.VARIANT_DIR = options.variant_dir

    if not dragon.PARROT_BUILD_PROP_PRODUCT:
        dragon.PARROT_BUILD_PROP_PRODUCT = dragon.PRODUCT
    if not dragon.PARROT_BUILD_PROP_VARIANT:
        dragon.PARROT_BUILD_PROP_VARIANT = dragon.VARIANT

    # Initialize default build properties, can be overwritten by product configuration
    if options.build_id:
        dragon.PARROT_BUILD_PROP_UID = options.build_id

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

    if not dragon.PARROT_BUILD_PROP_VERSION:
        # Remove part before version num
        _match = dragon.version_match(dragon.PARROT_BUILD_PROP_UID, prefix=True, suffix=True)
        if _match:
            # Recover the UID part with possible details (MAJOR.MINOR.RELEASE[-specification])
            (_uid, _version) = _match
            _version = _uid[_uid.find(_version):]
        else:
            _version = "0.0.0"
            dragon.LOGW("Unable to extract version from UID (%s)." % dragon.PARROT_BUILD_PROP_UID)
        dragon.PARROT_BUILD_PROP_VERSION = _version

    if not dragon.PARROT_BUILD_PROP_UID:
        dragon.PARROT_BUILD_PROP_UID = "%s-%s-%s-%s" % (
                dragon.PARROT_BUILD_PROP_PRODUCT,
                dragon.PARROT_BUILD_PROP_VARIANT,
                dragon.PARROT_BUILD_PROP_VERSION,
                datetime.datetime.now().strftime("%Y%m%d-%H%M"))

    # Setup directories
    if not dragon.OUT_ROOT_DIR:
        dragon.OUT_ROOT_DIR = os.path.join(dragon.WORKSPACE_DIR, "out")
    if not dragon.OUT_DIR:
        dragon.OUT_DIR = dragon.get_out_dir(dragon.PRODUCT, dragon.VARIANT)
    dragon.BUILD_DIR = os.path.join(dragon.OUT_DIR, "build")
    dragon.STAGING_DIR = os.path.join(dragon.OUT_DIR, "staging")
    dragon.FINAL_DIR = os.path.join(dragon.OUT_DIR, "final")
    dragon.IMAGES_DIR = os.path.join(dragon.OUT_DIR, "images")

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
    os.environ["POLICE_HOME"] = dragon.POLICE_HOME
    dragon.POLICE_OUT_DIR = os.path.join(dragon.OUT_DIR, "police")
    dragon.POLICE_SPY_LOG = os.path.join(dragon.POLICE_OUT_DIR, "police-spy.log")
    dragon.POLICE_PROCESS_LOG = os.path.join(dragon.POLICE_OUT_DIR, "police-process.log")

    # Setup spy if needed
    if options.police and not options.police_no_spy:
        setup_police_spy()

#===============================================================================
#===============================================================================
def main():
    options = Options()
    dragon.OPTIONS = options

    # Signal handler (avoid displaying python backtrace when interrupted)
    def signal_handler(sig, frame):
        sys.exit(0)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Parse options
    options.parse(sys.argv)
    setup_log(options)

    if os.geteuid() == 0:
        dragon.LOGE("Please do not run this script as root.")
        sys.exit(1)

    # Print help now if requested and no other argument given, otherwise see
    # below if help is requested on a task
    if options.help_asked and not options.tasks and not options.args:
        usage()
        sys.exit(0)

    # List products and exit
    if options.list_products:
        products = get_products()
        for product in products:
            sys.stderr.write(product + ":")
            variants = get_variants(product)
            for variant in variants:
                sys.stderr.write(" " + variant)
                if variant == get_default_variant(product):
                    sys.stderr.write("*")
            sys.stderr.write("\n")
        sys.stderr.write("Default variant for each product is indicated with *\n")
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

    # Import default tasks
    import deftasks

    # Import optional product configuration (search variant dir then product dir)
    if options.variant_dir is not None:
        sys.path.append(options.variant_dir)
    if options.product_dir is not None:
        sys.path.append(options.product_dir)
    try:
        dragon._product_cfg_module = __import__("buildcfg")
    except ImportError:
        pass

    # If project has not been defined, set default to product
    if not dragon.PARROT_BUILD_PROP_PROJECT:
        dragon.PARROT_BUILD_PROP_PROJECT = dragon.PARROT_BUILD_PROP_PRODUCT

    # Check all tasks
    dragon.check_tasks()

    # Generate completion file based on product
    if options.generate_completion:
        generate_completion()
        sys.exit(0)

    # List tasks and exit
    if options.list_tasks:
        list_tasks(options.list_secondary_tasks)
        sys.exit(0)

    # Add --help to task argument if needed
    if options.help_asked:
        options.args.append("--help")

    # Build given tasks
    if not options.tasks:
        logging.error("No task given ! Please use -t option to have a list"
                " of available tasks for your product.")
        sys.exit(1)

    if options.product == "forall":
        for product in get_products():
            restart(options, product, "forall")
    elif options.variant == "forall":
        pre_hook_variant_forall_task = getattr(dragon._product_cfg_module,
                "pre_hook_variant_forall_task", None)
        post_hook_variant_forall_task = getattr(dragon._product_cfg_module,
                "post_hook_variant_forall_task", None)

        _tasks = [ x["name"] for x in options.tasks ]
        _tasks_args = [ x["args"] for x in options.tasks ]
        if pre_hook_variant_forall_task:
            try:
                pre_hook_variant_forall_task(_tasks, _tasks_args)
            except dragon.TaskError as ex:
                logging.error(str(ex))
                if not options.keep_going:
                    sys.exit(1)
        variants = get_variants(options.product)
        if options.parallel_variants:
            pool = Pool(processes=len(variants))
            for variant in variants:
                pool.apply_async(restart, args=(options, options.product, variant))
            pool.close()
            pool.join()
        else:
            for variant in variants:
                restart(options, options.product, variant)
        if post_hook_variant_forall_task:
            try:
                post_hook_variant_forall_task(_tasks, _tasks_args)
            except dragon.TaskError as ex:
                logging.error(str(ex))
                if not options.keep_going:
                    sys.exit(1)
    elif len(options.tasks) > 0:
        try:
            for _task in options.tasks:
                dragon.do_task(_task["name"], _task["args"])
        except dragon.TaskError as ex:
            logging.error(str(ex))
            if not options.keep_going:
                sys.exit(1)

#===============================================================================
#===============================================================================
if __name__ == "__main__":
    main()
