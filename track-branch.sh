#!/bin/bash

if [ "${REPO_PROJECT}" = "" ]; then

	# Not inside a repo forall, do it ourself
	repo forall -c $0
	echo "Done !"

else

	# If project is on a branch, track it
	if [ -n "$(echo ${REPO_RREV}|sed -e '/refs\/tags/d;/[0-9a-fA-F]\{40\}/d')" ]; then
		readonly BRANCH=$(echo ${REPO_RREV}|sed -e '/tags/d;/[0-9a-fA-F]\{40\}/d;s/refs\/heads\///')
		if [ "$(git branch | grep " ${BRANCH}\$")" = "" ]; then
			readonly TRACK_CMD="git checkout -q -b ${BRANCH} -t ${REPO_REMOTE}/${BRANCH}"
			echo "${REPO_PATH} : ${TRACK_CMD}"
			${TRACK_CMD}
		else
			readonly CHECKOUT_CMD="git checkout -q ${BRANCH}"
			${CHECKOUT_CMD}
			if [ "$?" != "0" ]; then
				echo "Failure in ${REPO_PATH} : ${CHECKOUT_CMD}"
			fi
			readonly MERGE_CMD="git merge --ff-only ${REPO_REMOTE}/${BRANCH} -q"
			echo "${REPO_PATH}: ${BRANCH}"
			${MERGE_CMD}
			if [ "$?" != "0" ]; then
				echo "Failure in ${REPO_PATH} : ${MERGE_CMD}"
			fi
		fi
	fi
fi

