#!/bin/sh

TOP_DIR=$(pwd)

# Display a short help message
usage() {
	echo "Usage: $0 [--home] <image> <command> [<args>]"
	echo "  Run the command inside a docker container."
	echo "  The current directory shall be the top of the workspace."
	echo ""
	echo "  If --home is given the home directory will be mounted as a docker volume"
	echo ""
	echo "  For custom docker options, please use the env var DOCKER_OPTS."
}

if [ "$1" = "-h" -o "$1" = "--help" ]; then
	usage
	exit 0
fi

MOUNT_HOME=
if [ "$1" = "--home" ]; then
	MOUNT_HOME=true
	shift
fi

if [ $# -lt 2 ]; then
	echo "Missing image or command"
	usage
	exit 1
fi

DOCKER_IMAGE=$1; shift
VOLUME_OPTS=

# Mount top dir
VOLUME_OPTS="${VOLUME_OPTS} --volume ${TOP_DIR}:${TOP_DIR}"

# For X11 socket access
if [ "${XAUTHORITY}" != "" ]; then
	VOLUME_OPTS="${VOLUME_OPTS} --volume ${XAUTHORITY}:${XAUTHORITY}"
fi

# Mount passwd and group to restore user configuration (groups and git auth)
VOLUME_OPTS="${VOLUME_OPTS} --volume /etc/passwd:/etc/passwd"
VOLUME_OPTS="${VOLUME_OPTS} --volume /etc/group:/etc/group"

# By default a non-interactive pseudo-TTY is allocated, and we only
# keep STDIN open in the case of script being executed from a terminal
[ -t 0 ] && DOCKER_OPTS="${DOCKER_OPTS} --interactive"

# Duplicate all user groups
for grp in $(id -G); do
	DOCKER_OPTS="${DOCKER_OPTS} --group-add ${grp}"
done

# For settings/ssh access
if [ "${MOUNT_HOME}" != "" ]; then
	if [ "${HOME}" != "" ]; then
		VOLUME_OPTS="${VOLUME_OPTS} --volume ${HOME}:${HOME}"
	fi
fi

# Run the given image in a new container with some default options.
#
# --env QT_GRAPHICSSYSTEM="native" : allow qt application to work in container.
# --net=host : to have access to X11 socket.
# --user $(id -u):$(id -g) : to use initial user/group.
# --rm : remove container at the end.
# --interactive --tty : be interactive with tty.
exec docker run \
	--env QT_GRAPHICSSYSTEM="native" \
	--env HOME \
	--env DISPLAY \
	--env SHELL \
	--env XAUTHORITY \
	--env DRAGON_OUT_ROOT_DIR \
	--env DRAGON_OUT_DIR \
	--env TARGET_DEPLOY_ROOT \
	--env PARROT_BUILD_PROP_GROUP \
	--env PARROT_BUILD_PROP_PROJECT \
	--env PARROT_BUILD_PROP_PRODUCT \
	--env PARROT_BUILD_PROP_VARIANT \
	--env PARROT_BUILD_PROP_REGION \
	--env PARROT_BUILD_PROP_UID \
	--env PARROT_BUILD_PROP_VERSION \
	--env PARROT_BUILD_TAG_PREFIX \
	--env POLICE_HOME \
	${VOLUME_OPTS} \
	--workdir ${TOP_DIR} \
	--net=host \
	--user $(id -u):$(id -g) \
	--rm \
	--tty \
	${DOCKER_OPTS} \
	${DOCKER_IMAGE} \
	"$@"
