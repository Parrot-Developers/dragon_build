# Due to wildcard import in dragon, import local modules as private

import re as _re

#
# PyPuf:
# Python implementation of libpuf version parsing & comparison functions
#


class Version(object):
    TYPE_DEV = 0
    TYPE_ALPHA = 1
    TYPE_BETA = 2
    TYPE_RC = 3
    TYPE_RELEASE = 4

    # regex for parsing x.y.z[-suffix][+customW]
    _RE = _re.compile(
        # x.y.z
        r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
        # optional -suffix
        r"(?:-(?P<suffix>[^+]+))?"
        # optional +customW
        r"(?:\+(?P<custom>[a-z_-]+)(?P<custom_nb>\d+))?$"
    )
    # regex for parsing `suffix' into type/build
    _TYPE_RE = _re.compile(r"^(?P<type>alpha|beta|rc)(?P<build>\d+)$")
    # regex for custom names
    _CUSTOM_RE = _re.compile(r"^[a-z_-]{1,32}$")

    _UNSET = object()

    def __init__(self, name="0.0.0"):
        type_from_str = {
            "alpha": Version.TYPE_ALPHA,
            "beta": Version.TYPE_BETA,
            "rc": Version.TYPE_RC,
        }

        match = Version._RE.match(name)
        if not match:
            raise ValueError("Invalid version: {}".format(name))
        self.major = int(match.group("major"))
        self.minor = int(match.group("minor"))
        self.patch = int(match.group("patch"))

        suffix = match.group("suffix")
        self.type_string = None

        custom_name = match.group("custom")
        custom_number = match.group("custom_nb")

        if self.major == 0 and self.minor == 0 and self.patch == 0:
            self.type = Version.TYPE_DEV
            self.build = 0
            if suffix:
                type_match = Version._TYPE_RE.match(suffix)
                if type_match:
                    raise ValueError("Invalid version: {}".format(name))
                self.type_string = suffix
        elif suffix:
            type_match = Version._TYPE_RE.match(suffix)
            if not type_match:
                raise ValueError("Invalid version: {}".format(name))
            self.type = type_from_str[type_match.group("type")]
            self.build = int(type_match.group("build"))
        else:
            self.type = Version.TYPE_RELEASE
            self.build = 0

        if custom_name and custom_number:
            self.custom = custom_name
            self.custom_number = int(custom_number)
        else:
            self.custom = None
            self.custom_number = 0

        self.validate(name)

    def validate(self, name):
        # sanity checks
        # TYPE_DEV version must be 0.0.0
        if self.type == Version.TYPE_DEV:
            if self.major != 0 or self.minor != 0 or self.patch != 0:
                raise ValueError("Invalid version: {} (not 0.0.0)".format(name))
        # only TYPE_DEV can have a type_string
        if self.type != Version.TYPE_DEV and self.type_string is not None:
            raise ValueError("Invalid version: {} (type_string not empty)".format(name))
        # TYPE_DEV and TYPE_RELEASE must have a 0 build, while others must have a non-0 build
        if self.type == Version.TYPE_DEV or self.type == Version.TYPE_RELEASE:
            if self.build != 0:
                raise ValueError("Invalid version: {} (build != 0)".format(name))
        else:
            if self.build == 0:
                raise ValueError("Invalid version: {} (build == 0)".format(name))
        # setting custom implies a non-zero custom number to be set,
        # and custom must match _CUSTOM_RE (lowercase letters, _ and -, less than 32 chars)
        if self.custom:
            if self.custom_number == 0:
                raise ValueError(
                    "Invalid version: {} (custom_number == 0)".format(name)
                )
            if not Version._CUSTOM_RE.match(self.custom):
                raise ValueError("Invalid version: {} (invalid custom)".format(name))
        # if a custom_number is provided, custom must be provided too
        if self.custom_number != 0 and not self.custom:
            raise ValueError("Invalid version: {} (empty custom)".format(name))

        if self.type == Version.TYPE_DEV or self.type == Version.TYPE_RELEASE:
            self.p_lang = " " if self.custom else ""
        elif self.type == Version.TYPE_ALPHA:
            self.p_lang = "{}{:02d}".format("a" if self.custom else "A", self.build)
        elif self.type == Version.TYPE_BETA:
            self.p_lang = "{}{:02d}".format("b" if self.custom else "B", self.build)
        elif self.type == Version.TYPE_RC:
            self.p_lang = "{}{:02d}".format("r" if self.custom else "R", self.build)
        else:
            raise ValueError("Invalid version: {} (unknown type)".format(name))

    def __repr__(self):
        type_to_str = {
            Version.TYPE_ALPHA: "alpha",
            Version.TYPE_BETA: "beta",
            Version.TYPE_RC: "rc",
        }

        name = []
        name.append("{}.{}.{}".format(self.major, self.minor, self.patch))
        if self.type in type_to_str:
            name.append("-{}{}".format(type_to_str[self.type], self.build))
        elif self.type_string:
            name.append("-{}".format(self.type_string))
        if self.custom:
            name.append("+{}{}".format(self.custom, self.custom_number))
        return "".join(name)

    def __eq__(self, other):
        if self.major != other.major:
            return False
        if self.minor != other.minor:
            return False
        if self.patch != other.patch:
            return False
        if self.type != other.type:
            return False
        if self.build != other.build:
            return False
        # two custom versions are equal regardless of their custom name/number
        if bool(self.custom) != bool(other.custom):
            return False
        return True

    def __ne__(self, other):
        return not self.__eq__(other)

    def __lt__(self, other):
        if self.major != other.major:
            return self.major < other.major
        if self.minor != other.minor:
            return self.minor < other.minor
        if self.patch != other.patch:
            return self.patch < other.patch
        if self.type != other.type:
            return self.type < other.type
        if self.build != other.build:
            return self.build < other.build
        # a non-custom version is older than a custom one
        if not self.custom and other.custom:
            return True
        return False

    def __gt__(self, other):
        if self.major != other.major:
            return self.major > other.major
        if self.minor != other.minor:
            return self.minor > other.minor
        if self.patch != other.patch:
            return self.patch > other.patch
        if self.type != other.type:
            return self.type > other.type
        if self.build != other.build:
            return self.build > other.build
        # a custom version is newer than a non-custom one
        if self.custom and not other.custom:
            return True
        return False

    def __le__(self, other):
        return not self.__gt__(other)

    def __ge__(self, other):
        return not self.__lt__(other)

    def replace(
        self,
        major=_UNSET,
        minor=_UNSET,
        patch=_UNSET,
        type=_UNSET,
        type_string=_UNSET,
        build=_UNSET,
        custom=_UNSET,
        custom_number=_UNSET,
    ):
        v = Version(self.__repr__())

        if major is not Version._UNSET:
            v.major = major
        if minor is not Version._UNSET:
            v.minor = minor
        if patch is not Version._UNSET:
            v.patch = patch
        if type is not Version._UNSET:
            v.type = type
        if type_string is not Version._UNSET:
            v.type_string = type_string
        if build is not Version._UNSET:
            v.build = build
        if custom is not Version._UNSET:
            v.custom = custom
        if custom_number is not Version._UNSET:
            v.custom_number = custom_number

        v.validate(v.__repr__())
        return v

    # generate a pure release version from the current version
    def as_release(self):
        return self.replace(
            type=Version.TYPE_RELEASE,
            custom=None,
            custom_number=0,
            type_string=None,
            build=0,
        )

    # generate a version without custom suffix from the current version
    def as_not_custom(self):
        return self.replace(custom=None, custom_number=0)


def split_uid(uid):
    # find a dash in uid where the right part is a valid version
    start = 0
    end = len(uid)
    while start < end:
        idx = uid.find("-", start, end)
        if idx < 0:
            break
        try:
            _ = Version(uid[idx + 1 :])
        except ValueError:
            pass
        else:
            return uid[:idx], uid[idx + 1 :]
        start = idx + 1

    _ = Version(uid)
    return "", uid


def _test():
    # Unit test should be kept in sync with libpuf tests
    test_constructor = [
        # 0.0.0 versions
        ("0.0.0", (0, 0, 0, Version.TYPE_DEV, 0, None, 0, "")),
        ("0.0.0-test", (0, 0, 0, Version.TYPE_DEV, 0, None, 0, "")),
        ("0.0.0-test space", (0, 0, 0, Version.TYPE_DEV, 0, None, 0, "")),
        ("0.0.0+custom1", (0, 0, 0, Version.TYPE_DEV, 0, "custom", 1, " ")),
        ("0.0.0-test+custom1", (0, 0, 0, Version.TYPE_DEV, 0, "custom", 1, " ")),
        ("0.0.0-test space+custom1", (0, 0, 0, Version.TYPE_DEV, 0, "custom", 1, " ")),
        # wrong 0.0.0 versions
        ("0.0.0-alpha1", None),
        ("0.0.0-beta2", None),
        ("0.0.0-rc3", None),
        # x.y.z versions
        ("1.2.3", (1, 2, 3, Version.TYPE_RELEASE, 0, None, 0, "")),
        ("1.2.3-alpha1", (1, 2, 3, Version.TYPE_ALPHA, 1, None, 0, "A01")),
        ("1.2.3-beta2", (1, 2, 3, Version.TYPE_BETA, 2, None, 0, "B02")),
        ("1.2.3-rc3", (1, 2, 3, Version.TYPE_RC, 3, None, 0, "R03")),
        ("1.2.3+custom1", (1, 2, 3, Version.TYPE_RELEASE, 0, "custom", 1, " ")),
        ("1.2.3-alpha1+custom1", (1, 2, 3, Version.TYPE_ALPHA, 1, "custom", 1, "a01")),
        ("1.2.3-beta2+custom1", (1, 2, 3, Version.TYPE_BETA, 2, "custom", 1, "b02")),
        ("1.2.3-rc3+custom1", (1, 2, 3, Version.TYPE_RC, 3, "custom", 1, "r03")),
        # wrong x.y.z versions
        ("1.2.3-test", None),
        ("1.2.3-alpha0", None),
        ("1.2.3-beta0", None),
        ("1.2.3-rc0", None),
        # invalid version strings
        (None, None),
        ("1.2", None),
        ("not_a_version", None),
        ("1.2.3-ALPHA4", None),
        ("1.2.3.4", None),
        ("1.2.3-alpha2 with spaces", None),
        (" 1.2.3", None),
        ("1.2.3 ", None),
        ("1.2.3+no_number", None),
        ("1.2.3+with space1", None),
        ("1.2.3+1", None),
        ("1.2.3+with1number2", None),
        ("0.0.0+longlonglonglonglonglonglonglonglonglong1", None),
    ]

    for s, fields in test_constructor:
        did_fail = False
        # print("parsing", s)
        try:
            version = Version(s)
        except (ValueError, TypeError):
            did_fail = True
        else:
            assert version.major == fields[0]
            assert version.minor == fields[1]
            assert version.patch == fields[2]
            assert version.type == fields[3]
            assert version.build == fields[4]
            assert version.custom == fields[5]
            assert version.custom_number == fields[6]
            assert version.p_lang == fields[7]
            s2 = str(version)
            assert s == s2
        finally:
            # If fields are passed, constructor should not fail
            assert did_fail != bool(fields)

    # compare result (<, <=, ==, >=, >, name)
    SAME = (False, True, True, True, False, "equal")
    OLDER = (True, True, False, False, False, "lower")
    NEWER = (False, False, False, True, True, "greater")

    test_compare = [
        # A, expected result, B
        # equalities
        ("0.0.0", SAME, "0.0.0"),
        ("1.2.3-alpha4", SAME, "1.2.3-alpha4"),
        ("1.2.3-beta5", SAME, "1.2.3-beta5"),
        ("1.2.3-rc6", SAME, "1.2.3-rc6"),
        # change in major
        ("2.2.3", NEWER, "1.2.3"),
        ("2.2.3-alpha1", NEWER, "1.2.3"),
        ("2.2.3", NEWER, "1.2.3-rc3"),
        ("1.2.3", OLDER, "2.2.3"),
        # change in minor
        ("1.3.3", NEWER, "1.2.3"),
        ("1.3.3-alpha1", NEWER, "1.2.3"),
        ("1.3.3", NEWER, "1.2.3-rc3"),
        ("1.2.3", OLDER, "1.3.3"),
        # change in patch
        ("1.2.4", NEWER, "1.2.3"),
        ("1.2.4-alpha1", NEWER, "1.2.3"),
        ("1.2.4", NEWER, "1.2.3-rc3"),
        ("1.2.3", OLDER, "1.2.4"),
        # change in type
        ("1.2.3", NEWER, "1.2.3-rc1"),
        ("1.2.3-rc1", NEWER, "1.2.3-beta1"),
        ("1.2.3-beta1", NEWER, "1.2.3-alpha1"),
        ("1.2.3-alpha1", OLDER, "1.2.3-rc1"),
        # change in build
        ("1.2.3-alpha1", OLDER, "1.2.3-alpha2"),
        ("1.2.3-beta1", OLDER, "1.2.3-beta2"),
        ("1.2.3-rc1", OLDER, "1.2.3-rc2"),
        # add custom
        ("0.0.0", OLDER, "0.0.0+custom1"),
        ("1.2.3-alpha1", OLDER, "1.2.3-alpha1+custom1"),
        ("1.2.3-beta1", OLDER, "1.2.3-beta1+custom1"),
        ("1.2.3-rc1", OLDER, "1.2.3-rc1+custom1"),
        ("1.2.3", OLDER, "1.2.3+custom1"),
        # upgrade from custom
        ("0.0.0+custom1", OLDER, "1.0.0"),
        ("1.2.3-alpha1+custom1", OLDER, "1.2.3-alpha2"),
        ("1.2.3-beta1+custom1", OLDER, "1.2.3-rc1"),
        ("1.2.3-rc1+custom1", OLDER, "1.2.4-alpha1"),
        ("1.2.3+custom1", OLDER, "1.2.4+custom1"),
        # equalities with custom
        ("1.2.3+custom1", SAME, "1.2.3+custom1"),
        ("0.0.0+custom1", SAME, "0.0.0+other2"),
        ("1.2.3-alpha1+custom1", SAME, "1.2.3-alpha1+other2"),
        ("1.2.3-beta1+custom1", SAME, "1.2.3-beta1+other2"),
        ("1.2.3-rc1+custom1", SAME, "1.2.3-rc1+other2"),
        ("1.2.3+custom1", SAME, "1.2.3+other2"),
        ("1.2.3+custom1", SAME, "1.2.3+custom2"),
    ]

    for a, res, b in test_compare:
        # print("comparing", a, "and", b, "expecting", res[5])
        v1 = Version(a)
        v2 = Version(b)
        assert (v1 < v2) == res[0]
        assert (v1 <= v2) == res[1]
        assert (v1 == v2) == res[2]
        assert (v1 >= v2) == res[3]
        assert (v1 > v2) == res[4]
        # transitivity
        assert (v2 > v1) == res[0]
        assert (v2 >= v1) == res[1]
        assert (v2 == v1) == res[2]
        assert (v2 <= v1) == res[3]
        assert (v2 < v1) == res[4]

    test_split = [
        ("product-variant-1.2.3", "product-variant", "1.2.3"),
        ("product-variant-0.0.0-test", "product-variant", "0.0.0-test"),
        ("p-v-more-1.2.3-alpha1", "p-v-more", "1.2.3-alpha1"),
        ("1.2.3-beta2", "", "1.2.3-beta2"),
        ("p-v-1.2.3+custom1", "p-v", "1.2.3+custom1"),
        ("bad", None, None),
    ]

    for src, prod, ver in test_split:
        # print("splitting", src, "expecting", prod, "and", ver)
        if not prod and not ver:
            try:
                split_uid(src)
            except ValueError:
                pass
            else:
                assert False
        else:
            p, v = split_uid(src)
            assert p == prod
            assert v == ver

    test_replace = [
        # replace one element
        ("1.2.3", dict(major=2), "2.2.3"),
        ("1.2.3", dict(minor=3), "1.3.3"),
        ("1.2.3", dict(patch=4), "1.2.4"),
        ("1.2.3-alpha1", dict(type=Version.TYPE_BETA), "1.2.3-beta1"),
        ("0.0.0-init", dict(type_string="final"), "0.0.0-final"),
        ("1.2.3-alpha1", dict(build=2), "1.2.3-alpha2"),
        ("1.2.3", dict(custom="test", custom_number=1), "1.2.3+test1"),
        # invalid replacements
        # TYPE_DEV must be 0.0.0
        ("1.2.3", dict(type=Version.TYPE_DEV), None),
        # type_string is only for TYPE_DEV
        ("1.2.3", dict(type_string="test"), None),
        # TYPE_DEV must have build set to 0
        ("0.0.0", dict(build=1), None),
        # TYPE_RELEASE must have build set to 0
        ("1.2.3", dict(build=1), None),
        # TYPE_ALPHA must have build set to non-0
        ("1.2.3-alpha1", dict(build=0), None),
        # TYPE_BETA must have build set to non-0
        ("1.2.3-beta1", dict(build=0), None),
        # TYPE_RC must have build set to non-0
        ("1.2.3-rc1", dict(build=0), None),
        # missing custom_number
        ("1.2.3", dict(custom="test"), None),
        # zero custom_number
        ("1.2.3", dict(custom="test"), None),
        # too long custom string
        (
            "1.2.3",
            dict(custom="thisistoolongtobeavalidcustomstring", custom_number=1),
            None,
        ),
        # invalid characters in custom string
        ("1.2.3", dict(custom="CAPS42", custom_number=1), None),
        # missing custom
        ("1.2.3", dict(custom_number=1), None),
    ]
    for src, args, target in test_replace:
        v = Version(src)
        if target is not None:
            d = v.replace(**args)
            assert d.__repr__() == target
        else:
            try:
                v.replace(**args)
            except ValueError:
                pass
            else:
                assert False


def _main():
    print("Running version tests...")
    _test()
    print("Success.")


if __name__ == "__main__":
    _main()
