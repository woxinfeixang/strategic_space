#!/bin/bash

# Step 1: Check current status
echo "Current Git Status:"
git status

# Step 2: Add all files to staging area
git add .

# Step 3: Commit changes
git commit -m "Add all project files"

# Step 4: Push to remote repository
git push origin master