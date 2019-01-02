#!/bin/bash -
#===============================================================================
#
#          FILE: run.sh
#        AUTHOR: Peng Wang
#         EMAIL: pw2191195@gmail.com
#       CREATED: 12/27/18 10:09:58
#         USAGE: ./run.sh
#   DESCRIPTION: 
#===============================================================================


set -o nounset                         # Treat unset variables as an error

set -e

pipenv run python3 main.py
