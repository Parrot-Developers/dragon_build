#===============================================================================
# Contains utilities functions for dragon environment.
# Imported by dragon.py.
#===============================================================================

import os
import dragon
import tempfile
import HTMLParser, urllib2
# version_match is not used here but is aimed to be used by dragon's call.
#from pinst_wrapper import version_match, ConfigFileParser

#===============================================================================
# Create a symlink with relative path
# src : source (target of link)
# dest : destination (link to create)
#===============================================================================
def relative_symlink(src, dest):
    if dragon.WORKSPACE_DIR in dragon.OUT_DIR:
        for _file_check in [src, dest]:
            if dragon.WORKSPACE_DIR not in os.path.realpath(_file_check):
                raise IOError("'%s' is not part of the workspace." %
                        _file_check)
    else:
        for _file_check in [src, dest]:
            if dragon.WORKSPACE_DIR not in os.path.realpath(_file_check):
                dragon.LOGW("'%s' is not part of the workspace." %
                        _file_check)

    if os.path.lexists(dest):
        if not os.path.islink(dest):
            raise IOError("'%s' should not be a regular file/directory" % dest)
        dragon.exec_cmd("rm -f %s" % dest)
    makedirs(os.path.dirname(dest))
    dragon.exec_cmd("ln -fs %s %s" %
            (os.path.relpath(src, os.path.dirname(dest)), dest))

#===============================================================================
# Create directory tree if needed with correct access rights.
#===============================================================================
def makedirs(dirpath, mode=0755):
    if not os.path.isdir(dirpath):
        os.makedirs(dirpath, mode)

#===============================================================================
# Return the path of the product_config.json
#===============================================================================
def get_json_config(json_file="product_config.json", additional_paths=None):
    search_paths = [
        os.path.join(dragon.OUT_DIR),
        os.path.join(dragon.WORKSPACE_DIR,"products",
            dragon.PRODUCT, dragon.VARIANT, "config"),
        os.path.join(dragon.WORKSPACE_DIR,"products",
            dragon.PRODUCT),
        ]
    if isinstance(additional_paths, list):
        search_paths.extend(additional_paths)

    try:
        cfp = ConfigFileParser(json_file, search_paths)
    except IOError:
        dragon.LOGW("%s file not found", json_file)
        cfp = None
    except ValueError as ex:
        raise dragon.TaskError(ex.message)
    return cfp

#===============================================================================
# Generate a manifest.xml from repo manifest command
# Takes a mandatory filepath as argument.
# Any file given will be erased if already existing.
#===============================================================================
def gen_manifest_xml(filepath):
    # Generate an intermediary manifest
    # It avoid issues if filepath is the same as the source manifest
    if not os.path.exists(os.path.dirname(filepath)):
        raise dragon.TaskError("Cannot generate manifest as the "
                "directory does not exist.")
    temp_file = tempfile.mkstemp(suffix=".xml")[1]
    cmd = "repo manifest --revision-as-HEAD " \
            "--suppress-upstream-revision -o %s" % temp_file
    dragon.exec_cmd(cmd, extra_env={"GIT_PAGER": "cat"})
    cmd = "mv %s %s" % (temp_file, filepath)
    dragon.exec_cmd(cmd)

#===============================================================================
# Generate an archive for a version to be released.
# Generally used in association with the publish task.
#
# Will generate an archive named <release_id>.tar either in the top_dir or
# in the out_dir of the workspace.
#
# File list format :
# List content of {
#     "src":<path>,
#     "dest": <path>,
#     "mandatory":False
# }
# <path> can either be a directory or a file, but take note that the dest
# Is *always* overwritten.
# <src> must be relative to TOP_DIR (or absolute if using dragon.XXX special
# path variables.
# <dest> is always relative to the release_id.
# Its default path if not provided is the top of the release dir.
# <mandatory> field shall be explicitly set to False as it is by default True.
# It will stop the task if a file is missing. This field may be absent.
#===============================================================================
def generate_release_archive(release_id, additional_files=None,
        product_config="product_config.json", warn_on_overwrite=False,
        previous_manifest=None):

    # Disable police while generating the archive
    os.environ["POLICE_HOOK_DISABLED"] = "1"

    # Init final directories and sources
    release_dir = os.path.join(dragon.OUT_DIR, "release-" + release_id)
    release_config_dir = os.path.join(release_dir, "config")

    # Create base list of files for release
    archive_content = [
        {
            "src": os.path.join(dragon.OUT_DIR,
                "symbols-%s-%s.tar" % (dragon.PRODUCT, dragon.VARIANT)),
            "dest": os.path.join(release_dir, "symbols.tar"),
        },
        {
            "src": os.path.join(dragon.OUT_DIR,
                "sdk-%s-%s.tar.gz" % (dragon.PRODUCT, dragon.VARIANT)),
            "dest": os.path.join(release_dir, "sdk.tar.gz"),
        },
        {
            "src": os.path.join(dragon.OUT_DIR, "images"),
            "dest": os.path.join(release_dir, "images"),
        },
        {
            "src": os.path.join(dragon.OUT_DIR, "staging", "etc", "build.prop"),
            "dest": os.path.join(release_dir, "build.prop"),
        },
        {
            "src": os.path.join(dragon.OUT_DIR, "build", "linux", ".config"),
            "dest": os.path.join(release_config_dir, "linux.config"),
            "mandatory": False
        },
        {
            "src": os.path.join(dragon.OUT_DIR, "global.config"),
            "dest": os.path.join(release_config_dir, "global.config"),
        },
        {
            "src": os.path.join(dragon.WORKSPACE_DIR, "build", "dragon_build",
                "pinst_wrapper.py"),
            "dest": os.path.join(release_dir, "pinst_wrapper.py"),
        },
        {
            "src": os.path.join(dragon.OUT_DIR, "police"),
            "dest": os.path.join(release_dir, "police"),
            "mandatory": False
        },
        {
            "src": os.path.join(dragon.OUT_DIR, "oss-packages"),
            "dest": os.path.join(release_dir, "oss-packages"),
            "mandatory": False
        },
    ]

    release_manifest = "release.xml"
    if not previous_manifest:
        previous_manifest = release_manifest

    cfp = get_json_config(product_config)
    release_section = None
    if cfp:
        release_section = cfp.get_section("release")
    # As this section is optional, we add it only if present
    if release_section:
        json_filepath = cfp.get_config_filepath()
        archive_content.append({
            "src": json_filepath,
            "dest": os.path.join(release_dir, "product_config.json")
            })
        # Export current variables as environment to be used with json
        for _envvar in ["PARROT_BUILD_PROP_GROUP", "PARROT_BUILD_PROP_PROJECT",
                "PARROT_BUILD_PROP_PRODUCT", "PARROT_BUILD_PROP_VARIANT",
                "PARROT_BUILD_PROP_REGION", "PARROT_BUILD_PROP_UID",
                "PARROT_BUILD_PROP_VERSION", "WORKSPACE_DIR", "OUT_DIR" ]:
            os.environ[_envvar] = getattr(dragon, _envvar)

        json_add_files = release_section.get("additional_files", [])
        release_manifest = release_section.get("manifest_name",
                release_manifest)
        # In case of a previous manifest with different name
        # between two versions (It serves only for changelog)
        previous_manifest = release_section.get("previous_manifest",
                release_manifest)
        for _elem in json_add_files:
            archive_content.append({
                "src": os.path.expandvars(_elem["src"]),
                "dest": os.path.join(
                    release_dir, os.path.expandvars(_elem["dest"])),
                "mandatory":_elem.get("mandatory", True),
            })
        warn_on_overwrite = release_section.get("warn_on_overwrite", False)
    # For files provided by function calling
    if isinstance(additional_files, list):
        archive_content.extend(additional_files)

    for _elem in archive_content:
        src = _elem["src"]
        dest = _elem["dest"]
        # Optional field
        mandatory = _elem.get("mandatory", True)
        if os.path.exists(dest):
            if warn_on_overwrite:
                dragon.LOGW("%s will be overwritten.", dest)
            os.unlink(dest)
        # This function already do the parent dirname creation when needed
        if os.path.exists(src):
            relative_symlink(src, dest)
        else:
            if mandatory and not dragon.OPTIONS.dryrun:
                raise dragon.TaskError("%s file is absent. Cannot generate release." % src)

    # Normally it is also found in final/etc but in case the product does not
    # have this feature because of the task being overloaded.
    gen_manifest_xml(os.path.join(release_dir, "manifest.xml"))
    # Too bad if absent
    # Can raise error on first release, where no previous manifest is found
    try:
        dragon.exec_cmd("repo diffmanifest --full --graph --no-color "
                "+:{previous_xml_name} {xml_name} > {output}".format(
                    output=os.path.join(release_dir, "changelog.txt"),
                    xml_name=release_manifest,
                    previous_xml_name=previous_manifest)
                )
    except:
        pass

    # Generate md5sum file
    dragon.exec_dir_cmd(dirpath=release_dir, cmd="md5sum $(find -follow -type f) > md5sum.txt")

    # Archive the release
    dragon.exec_cmd("tar -C %s -hcf %s.tar ." % (release_dir, release_dir))

    # Re-enable police while generating the archive
    del os.environ["POLICE_HOOK_DISABLED"]

    # Do not move in workspace if output dir is somewhere else (jenkins for example)
    if dragon.OUT_DIR.startswith(dragon.WORKSPACE_DIR):
        dragon.exec_cmd("mv -f %s.tar %s " % (release_dir,
                os.path.join(dragon.WORKSPACE_DIR, "%s.tar" % dragon.PARROT_BUILD_PROP_UID)))

#===============================================================================
# Get informations from version server about a specific release
# or list available releases.
#
#===============================================================================
class VersionServerHTMLParser(HTMLParser.HTMLParser, object):
    is_printable = False
    content = []
    def handle_data(self, data):
        if self.is_printable:
            self.content.append(data)
    def handle_starttag(self, tag, attrs):
        # Assuming that on version server, versions are in a 'a' markup
        dragon.LOGD("Begin : %s with %s", tag, attrs)
        if tag == "a":
            for attr, value in attrs:
                if attr == "href" and "/versions/" in value:
                    self.is_printable = True
        else:
            self.is_printable = False
    def handle_endtag(self, tag):
        # Not needed
        dragon.LOGD("End : %s", tag)
        pass
    def feed(self, content):
        super(VersionServerHTMLParser, self).feed(content)
        return self.content

class VersionServerInterface(object):
    def __init__(self, url, images_dir="bin/images"):
        self.url = url
        self.images_dir = images_dir
        self.parser = VersionServerHTMLParser()

    def __get_list(self, url):
        # Get server content, accepting certificates)
        dragon.LOGD("Trying to open %s" % url)
        url_fp = urllib2.urlopen(url)
        content = self.parser.feed(url_fp.read())
        return content

    def get_version_list(self, custom_filter=""):
        if dragon.OPTIONS.dryrun:
            return

        versions = self.__get_list(self.url)
        dragon.LOGI("List of versions found :")
        versions = [ x for x in versions if custom_filter in x ]
        print "\n".join(versions)

    def __download_from(self, url, version, image_file,
            additional_files=None):
        filelist = []
        # Get default mandatory files
        # Respect the order
        urls_suffixes = [
                ("../product_config.json", False),
                (image_file, True),
                ]
        # Add optional additional files
        if isinstance(additional_files, list):
            urls_suffixes.extend(additional_files)
        for _suffix in urls_suffixes:
            (full_url, mandatory) = (os.path.join(url, _suffix[0]),
                    _suffix[1])
            try:
                url_fp = urllib2.urlopen(full_url)
            except urllib2.HTTPError as ex:
                # To skip optional files, we allow in this case 404 errors
                if ex.code == 404 and not mandatory:
                    continue
                else:
                    raise dragon.TaskError("HTTPError (%d/%s) "
                            "while recovering %s " % (
                                ex.code, ex.msg,
                                full_url))

            dstfile = version + "_" + full_url[full_url.rindex("/")+1:]
            dstpath = os.path.join(dragon.OUT_DIR, "version", dstfile)
            makedirs(os.path.dirname(dstpath))

            if not os.path.exists(dstpath):
                dragon.LOGI("Recovering %s in %s", full_url, dstpath)
                if not dragon.OPTIONS.dryrun:
                    with open(dstpath, "w") as fp:
                        fp.write(url_fp.read())
            filelist.append(dstpath)
        return filelist

    def download_from(self, version, exts=None, additional_files=None):
        if exts is None:
            exts = [".tar", ".tar.gz", ".tgz"]
        url = os.path.join(self.url, version, self.images_dir)
        if dragon.OPTIONS.dryrun:
            dragon.LOGI("Prompting %s for download list.", url)
            return None

        # Recover list of images matching extensions
        content = self.__get_list(url)
        archive_files = []
        for _file in content:
            for _ext in exts:
                if _file.endswith(_ext):
                    archive_files.append(_file)
                    break

        # Get file to flash, prompting if more than one found
        image_file = None
        if len(archive_files) == 0:
            raise dragon.TaskError("Could not find images associated "
                    "with version %s !" % version)
        elif len(archive_files) == 1:
            image_file = archive_files[0]
        else:
            index = 0
            for _file in archive_files:
                index += 1
                print str(index) + ")", _file
            result = raw_input("Which file would you like to flash ? ")
            try:
                image_file = archive_files[int(result) - 1]
            # In case of the file name is given instead of the index
            except Exception:
                image_file = result

        # Download all needed files, product_config may be absent
        return self.__download_from(url, version, image_file,
                                    additional_files=additional_files)
