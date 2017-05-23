
import os
import logging

import dragon
import utils

#===============================================================================
# Setup police environment variables for spy.
# This shall be kept in sync with what is done in police-spy.sh
#===============================================================================
def setup_spy():
    # Nothing to do if already in LD_PRELOAD
    if "police-hook.so" in os.environ.get("LD_PRELOAD", ""):
        return

    # Setup environment
    os.environ["LD_PRELOAD"] = "police-hook.so"
    ldlibpath = [
        os.environ.get("LD_LIBRARY_PATH", ""),
        os.path.join(dragon.POLICE_HOME, "hook", "lib32"),
        os.path.join(dragon.POLICE_HOME, "hook", "lib64"),
    ]
    os.environ["LD_LIBRARY_PATH"] = ":".join(ldlibpath)
    os.environ["POLICE_HOOK_LOG"] = dragon.POLICE_SPY_LOG
    os.environ["POLICE_HOOK_RM_SCRIPT"] = os.path.join(
            dragon.POLICE_HOME, "police-rm.sh")
    os.environ["POLICE_HOOK_NO_ENV"] = "1"

    # Setup directory
    utils.makedirs(os.path.dirname(dragon.POLICE_SPY_LOG))

    # Keep previous logs. Spy will append to existing if any
    # If a fresh spy is required, user shall clean it before
    if not os.path.exists(dragon.POLICE_SPY_LOG):
        fd = open(dragon.POLICE_SPY_LOG, "w")
        fd.close()

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
def gen_report(addhtml=True, addtxt=False, compress=False):
    # Process step
    logging.info("Police: process")
    utils.exec_cmd("%s --infile %s --outfile %s %s" % (
            os.path.join(dragon.POLICE_HOME, "police-process.py"),
            dragon.POLICE_SPY_LOG,
            dragon.POLICE_PROCESS_LOG,
            "-v" if dragon.OPTIONS.verbose else ""))

    # Report step
    logging.info("Police: report")
    utils.exec_cmd("%s --infile %s --outdir %s --rootdir %s --builddir %s "
            "--finaldir %s --md5 --cmakepatch %s %s" % (
            os.path.join(dragon.POLICE_HOME, "police-report.py"),
            dragon.POLICE_PROCESS_LOG,
            dragon.POLICE_OUT_DIR,
            dragon.WORKSPACE_DIR,
            dragon.OUT_DIR,
            dragon.FINAL_DIR,
            "-v" if dragon.OPTIONS.verbose else "",
            " ".join([("--xml-license %s" % xml) for xml in dragon.POLICE_XML_LICENSES])))

    # Remove existing police files
    police_final_dir = os.path.join(dragon.FINAL_DIR, dragon.DEPLOY_DIR, "share", "police")
    utils.exec_cmd("rm -rf %s" % police_final_dir)
    utils.makedirs(police_final_dir)

    # Add files
    if addhtml:
        utils.exec_cmd("cp -af %s %s" % (
                os.path.join(dragon.POLICE_OUT_DIR, "police-notice.html"),
                police_final_dir))
        if compress:
            utils.exec_cmd("gzip %s" %
                    os.path.join(police_final_dir, "police-notice.html"))
    if addtxt:
        utils.exec_cmd("cp -af %s %s" % (
                os.path.join(dragon.POLICE_OUT_DIR, "police-notice.txt"),
                police_final_dir))
        if compress:
            utils.exec_cmd("gzip %s" %
                    os.path.join(police_final_dir, "police-notice.txt"))

#===============================================================================
#===============================================================================
def get_packages():
    # Get list of packages to generate
    filepath = os.path.join(dragon.POLICE_OUT_DIR, "police-package-license-module.txt")
    packages = []
    with open(filepath) as fin:
        for line in fin:
            package = line.split(" ")[1].rstrip("\n")
            if "#" in package:
                package = package.split("#")[0]
            if package not in packages:
                packages.append(package)
    return " ".join(packages)
