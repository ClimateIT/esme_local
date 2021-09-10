#!/bin/bash

export ESME_HOME="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
export PATH=${ESME_HOME}/env/bin:$PATH

eval "$(${ESME_HOME}/env/bin/conda shell.bash hook)"
conda activate esme
