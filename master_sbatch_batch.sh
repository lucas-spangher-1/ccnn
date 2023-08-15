#!/bin/bash

for i in $(seq 1 "$1")
do
	sbatch submit_submit.sh "$2"
done
