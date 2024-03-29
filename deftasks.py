
import sys
import os
import json
import platform

import dragon
import police

#===============================================================================
# Hooks.
#===============================================================================

def hook_post_clean(task, args):
    dragon.exec_cmd("rm -rf %s" % dragon.POLICE_OUT_DIR)
    dragon.exec_cmd("rm -rf %s" % dragon.IMAGES_DIR)
    dragon.exec_cmd("rm -rf %s" % os.path.join(dragon.OUT_DIR, "release-*"))
    dragon.exec_cmd("rm -rf %s" % os.path.join(dragon.OUT_DIR, "pinstrc"))
    dragon.exec_cmd("rm -f %s" % os.path.join(dragon.OUT_DIR, "build.prop"))
    dragon.exec_cmd("rm -f %s" % os.path.join(dragon.OUT_DIR, "manifest.xml"))

def hook_pre_images(task, args):
    # Automatically generate a manifest.xml in final/etc (if it exists)
    manifest_path = os.path.join(dragon.FINAL_DIR, "etc", "manifest.xml")
    if os.path.exists(os.path.dirname(manifest_path)):
        dragon.gen_manifest_xml(manifest_path)
        dragon.relative_symlink(manifest_path,
                                os.path.join(dragon.OUT_DIR,
                                             os.path.basename(manifest_path)))
    # Link final/etc/build.prop in out if it exists
    build_prop_path = os.path.join(dragon.FINAL_DIR, "etc", "build.prop")
    if os.path.exists(build_prop_path):
        dragon.relative_symlink(build_prop_path,
                                os.path.join(dragon.OUT_DIR,
                                             os.path.basename(build_prop_path)))

def hook_post_images(task, args):
    # Create the images directory so the release task is happy
    dragon.makedirs(dragon.IMAGES_DIR)
    # Get json config file
    json_cfg = dragon.get_json_config()
    # Alchemy images to get verbatim
    if json_cfg and "images" in json_cfg:
        for _ext in json_cfg["images"].get("extensions", []):
            filename = "%s-%s%s" % (dragon.PRODUCT, dragon.VARIANT, _ext)
            src_path = os.path.join(dragon.OUT_DIR, filename)
            dst_path = os.path.join(dragon.IMAGES_DIR, filename)
            if os.path.exists(src_path):
                dragon.exec_cmd("mv -f %s %s" % (src_path, dst_path))

def hook_police_report(task, args):
    police.gen_report(addhtml=True, addtxt=False, compress=False)

def hook_pre_police_packages(task, args):
    task.extra_env["OSS_PACKAGES"] = police.get_packages()

def hook_pre_release(task, args):
    # Do not include gdb server in generated images
    os.environ["TARGET_INCLUDE_GDBSERVER"] = "0"
    dragon.check_build_id()
    if dragon.PARROT_BUILD_PROP_UID.lower() != dragon.PARROT_BUILD_PROP_UID:
        raise dragon.TaskError("You shall provide a lowercase build_id")
    dragon.exec_cmd("rm -rf %s" % dragon.RELEASE_DIR)
    dragon.makedirs(dragon.OUT_DIR)
    if platform.system() == 'Linux':
        dragon.exec_cmd("dpkg --list > os_packages.txt", cwd=dragon.OUT_DIR)
    elif platform.system() == 'Darwin':
        data = dragon.exec_shell("brew info --installed --json=v1")
        data_json = json.loads(data)
        with open(os.path.join(dragon.OUT_DIR, 'os_packages.txt'), 'w') as os_packages:
            data_lines = json.dumps(data_json, indent=4)
            os_packages.write(data_lines)

def hook_gen_release_archive(task, args):
    dragon.gen_release_archive()

def hook_alchemy_genproject(task, args):
    script_path = os.path.join(dragon.ALCHEMY_HOME, "scripts",
                               "genproject", "genproject.py")
    subscript_name = task.name.replace("gen", "")

    if "-h" in args or "--help" in args:
        dragon.exec_cmd("%s %s -h" % (script_path, subscript_name))
        dragon.LOGW("Note: The -b option and dump_xml file are automatically given.")
        raise dragon.TaskExit()

    dump_xml = dragon.gen_alchemy_dump_xml()
    cmd_args = [script_path, subscript_name,
                "-b", "'-p %s-%s -A'" % (dragon.PRODUCT, dragon.VARIANT),
                dump_xml, " ".join(args)]
    dragon.exec_cmd(" ".join(cmd_args))

#===============================================================================
# Tasks
#===============================================================================

dragon.add_alchemy_task(
    name = "alchemy",
    desc = "Directly pass commands to alchemy",
    product = dragon.PRODUCT,
    variant = dragon.VARIANT,
    weak = False,
)

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
    name="images",
    desc="Generate default images for product",
    subtasks=["alchemy image"],
    prehook=hook_pre_images,
    posthook=hook_post_images,
    weak=True
)

dragon.add_meta_task(
    name="images-all",
    desc="Generate all images for product",
    subtasks=["alchemy image"],
    prehook=hook_pre_images,
    posthook=hook_post_images,
    weak=True
)

dragon.add_meta_task(
    name="all",
    desc="Build and generate default images for product",
    subtasks=["build", "images"],
    weak=True
)

dragon.add_meta_task(
    name="xconfig",
    desc="Modules configuration with graphical interface.",
    subtasks=["alchemy xconfig"],
    weak = True
)
dragon.add_meta_task(
    name="menuconfig",
    desc="Modules configuration with ncurses interface.",
    subtasks=["alchemy menuconfig"],
    weak = True
)

gen_tasks = {
    "geneclipse": "Generate Eclipse CDT project",
    "genqtcreator": "Generate QtCreator project",
    "genvscode": "Generate VisualStudio Code project",
    "genjsondb": "Generate compile_commands.json"
}
for taskname, taskdesc in gen_tasks.items():
    dragon.add_meta_task(
        name = taskname,
        desc = taskdesc,
        exechook = hook_alchemy_genproject,
        weak = True
    )

dragon.add_meta_task(
    name="police-report",
    desc="Generate police report and add it in final tree",
    exechook=hook_police_report,
    secondary_help=True,
    weak=True
)

dragon.add_meta_task(
    name="police-packages",
    desc="Generate police packages",
    subtasks=["alchemy oss-packages"],
    prehook=hook_pre_police_packages,
    secondary_help=True,
    weak = True
)

dragon.add_meta_task(
    name = "gen-release-archive",
    desc = "Generate release package",
    prehook = hook_pre_release,
    exechook = hook_gen_release_archive,
    secondary_help=True,
    weak=True
)

dragon.add_meta_task(
    name = "release",
    desc = "Build everything & generate a release archive",
    subtasks = [
        "build",
        "police-report" if dragon.OPTIONS.police else "",
        "police-packages" if dragon.OPTIONS.police_packages else "",
        "images-all",
        "alchemy symbols-tar sdk dump-modules",
        "gen-release-archive"
    ],
    prehook = hook_pre_release,
    secondary_help=True,
    weak=True
)
