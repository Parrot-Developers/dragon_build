#===============================================================================
# Default tasks.
# Can be overwritten by product configuration.
#===============================================================================

import os
import dragon
import shutil
import argparse

#===============================================================================
# Hooks
#===============================================================================
def hook_post_clean(task, args):
    dragon.exec_cmd("rm -rf %s" % dragon.POLICE_OUT_DIR)
    dragon.exec_cmd("rm -rf %s" % dragon.IMAGES_DIR)
    dragon.exec_cmd("rm -rf %s" % os.path.join(dragon.OUT_DIR, "release-*"))
    dragon.exec_cmd("rm -rf %s" % os.path.join(dragon.OUT_DIR, "pinstrc"))

def hook_geneclipse(task, args):
    if (len(args) == 0):
        raise dragon.TaskError("module argument missing")

    if args[0] == "--help" or args[0] == "-h":
        dragon.LOGI("usage: ./build.sh -t %s [-f] <module1> <module2> ...", task.name)
        return

    if args[0] == "--full" or args[0] == "-f":
        build_option = "-f"
        if (len(args) == 1):
            raise dragon.TaskError("module argument missing")
        projects = args[1:]
    else:
        build_option = "-d"
        projects = args[0:]

    # dump alchemy database in xml
    alchemy_xml = os.path.join(dragon.OUT_DIR, "alchemy-database.xml")
    dragon.exec_dir_cmd(dirpath=dragon.WORKSPACE_DIR,
        cmd="./build.sh -p %s-%s -A dump-xml" %
        (dragon.PRODUCT, dragon.VARIANT))

    # invoke alchemy eclipseproject python script
    build_cmd = r"-p \${TARGET_PRODUCT}-\${TARGET_PRODUCT_VARIANT} -A"
    dragon.exec_dir_cmd(dirpath=dragon.WORKSPACE_DIR,
                 cmd="%s/scripts/eclipseproject.py %s -b \"%s\" %s %s" %
                 (dragon.ALCHEMY_HOME, build_option, build_cmd, alchemy_xml,
                 " ".join(projects)))

def hook_genqtcreator(task, args):
    if (len(args) == 0):
        raise dragon.TaskError("module or atom.mk directory argument missing")

    if args[0] == "--help" or args[0] == "-h":
        dragon.LOGI("usage: ./build.sh -t %s [-f] <module1|dir1> <module2|dir2> ...", task.name)
        return

    projects = args[0:]

    # dump alchemy database in xml
    alchemy_xml = os.path.join(dragon.OUT_DIR, "alchemy-database.xml")
    dragon.exec_dir_cmd(dirpath=dragon.WORKSPACE_DIR,
        cmd="./build.sh -p %s-%s -A dump-xml" %
        (dragon.PRODUCT, dragon.VARIANT))

    # invoke alchemy qtcreatorproject python script
    build_cmd = "-p %s-%s -A" % (dragon.PRODUCT, dragon.VARIANT)
    dragon.exec_dir_cmd(dirpath=dragon.WORKSPACE_DIR,
        cmd="%s/scripts/qtcreatorproject.py %s -b '%s' %s" %
        (dragon.ALCHEMY_HOME, alchemy_xml, build_cmd, " ".join(projects)))

#===============================================================================
# Tasks
#===============================================================================

dragon.add_meta_task(
    name = "build",
    desc = "Build everything and generate final directory",
    subtasks=["alchemy all final"],
    weak = True,
)

dragon.add_meta_task(
    name = "clean",
    desc = "Clean everything",
    subtasks=["alchemy clobber"],
    posthook = hook_post_clean,
    weak = True,
)

dragon.add_meta_task(
    name="all",
    desc="Build and generate images for product",
    subtasks=["build", "images"],
    weak=True
)

dragon.add_alchemy_task(
    name = "alchemy",
    desc = "Directly pass commands to alchemy",
    product = dragon.PRODUCT,
    variant = dragon.VARIANT,
    weak = False,
)

# Use generic configuration tasks
dragon.add_meta_task(
    name="xconfig",
    desc="Modules configuration with graphical interface.",
    subtasks=["alchemy xconfig"],
    weak = True,
)
dragon.add_meta_task(
    name="menuconfig",
    desc="Modules configuration with ncurses interface.",
    subtasks=["alchemy menuconfig"],
    weak = True,
)
# Kernel config
dragon.add_meta_task(
    name="linux-xconfig",
    desc="Kernel configuration with graphical interface.",
    subtasks=["alchemy linux-xconfig"],
    weak = True,
)
dragon.add_meta_task(
    name="linux-menuconfig",
    desc="Kernel configuration with ncurses interface.",
    subtasks=["alchemy linux-menuconfig"],
    weak = True,
)
dragon.add_meta_task(
    name = "geneclipse",
    desc = "Generate Eclipse CDT project",
    posthook = hook_geneclipse
)
dragon.add_meta_task(
    name = "genqtcreator",
    desc = "Generate QtCreator project",
    posthook = hook_genqtcreator
)

