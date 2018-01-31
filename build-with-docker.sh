#!/bin/sh

TOP_DIR=$(pwd)

# Display a short help message
usage() {
	echo "Usage: $0 <image> <command> [<args>]"
	echo "  Run the command inside a docker container."
	echo "  The current directory shall be the top of the workspace."
	echo ""
	echo "  For custom docker options, please use the env var DOCKER_OPTS."
}

if [ "$1" = "-h" -o "$1" = "--help" ]; then
	usage
	exit 0
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

# Duplicate all user groups
for grp in $(id -G); do
	DOCKER_OPTS="${DOCKER_OPTS} --group-add ${grp}"
done

# For settings/ssh access
if [ "${HOME}" != "" ]; then
	VOLUME_OPTS="${VOLUME_OPTS} --volume ${HOME}:${HOME}"
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
	${VOLUME_OPTS} \
	--workdir ${TOP_DIR} \
	--net=host \
	--user $(id -u):$(id -g) \
	--rm \
	--interactive \
	--tty \
	${DOCKER_OPTS} \
	${DOCKER_IMAGE} \
	"$@"
