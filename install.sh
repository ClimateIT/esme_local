#!/bin/bash

wget https://repo.anaconda.com/miniconda/Miniconda3-py39_4.9.2-Linux-x86_64.sh && \
sh Miniconda3-py39_4.9.2-Linux-x86_64.sh -b -p $(pwd)/env && \

export PATH=$(pwd)/env/bin:$PATH
./env/bin/conda install -y mamba -c conda-forge && \
./env/bin/mamba env create --file conda_env.yaml && \

rm Miniconda3-py39_4.9.2-Linux-x86_64.sh

