#!/bin/bash
echo "WARNING: All your local branches will be deleted, (y|n)"
read input
if [ "$input" == "y" -o "$input" == "Y" ]; then
    repo forall -c "pwd;git checkout -q --detach;git branch |/bin/grep -v \"^* \" | xargs -r git branch -D"
fi

