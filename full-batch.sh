#!/bin/bash

# Create the results directory if it doesn't exist
mkdir -p ./results

# Get the current date in YYYY-MM-DD format
NOW=$(date +"%Y%m%d_%H%M%S")

# Run the Python script and redirect output to a file named with the current date
python full-batch.py > "./results/full-batch_$NOW.txt"
