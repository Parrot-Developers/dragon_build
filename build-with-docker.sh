#!/bin/sh

TOP_DIR=$(pwd)

# Display a short help message
usage() {
	echo "Usage: $0 <image> [<build-args>]"
	echo "  Run the 'build.sh' script inside a docker container."
	echo "  The current directory shall be the top of the workspace."
	echo ""
	echo "  For custom docker options, please use the env var DOCKER_OPTS."
	exit 0
}

# Make sure there is a 'build.sh' in ${TOP_DIR}
if [ ! -x "${TOP_DIR}/build.sh" ]; then
	echo "No 'build.sh' script found in '${TOP_DIR}'"
	exit 1
fi

# Parse options
DOCKER_IMAGE=""
ARGS=""
VOLUME_OPTS=

COMMAND="${TOP_DIR}/build.sh \${ARGS}"
while [ $# -ne 0 ]; do
	case ${1} in
		--interactive) COMMAND="/bin/bash";;
		--help) usage;;
		-*)	# We assume that this is an argument
			ARGS="${ARGS} ${1}";;
		*)if [ -z "${DOCKER_IMAGE}" ]; then
			# Docker image should be the first argument
			DOCKER_IMAGE="${1}"
		else
			# Otherwise consider it a custom arg
			ARGS="${ARGS} ${1}"
		fi;;
	esac
	shift
done
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
eval exec docker run \
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
	${COMMAND}
