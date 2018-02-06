# Aqqu Question Answering System

This is the code accompanying the publication "More Accurate Question Answering on Freebase, Hannah Bast and Elmar Haussmann, CIKM 2015"

Follow the instructions in QUICKSTART.md to set up the system. This also includes descriptions on how to 
obtain pre-requisite data, e.g., a complete index of Freebase.

Setup is easy if all pre-requisites are met.

## Requirements:

* OS: Linux system (tested on Ubuntu 12.04)
* Software: Python 2.7 as well as Java 8 + Prerequisites for Virtuoso, see
  QUICKSTART.md for more details.
* RAM: 40 GB for training the large WebQuestions models
* Disk: about 40 GB for all pre-requisite data

## Get the Dataset

All data required for learning can be found under
`/nfs/datastets/aqqu_input_data`, all other data is generated automatically.

    cp -r /nfs/datasets/aqqu_input_data/* input/

## Train with the provided script

    ./build_and_run.sh learner <user_provided_name> <ranker e.g. WQSP_Ranker> <port>

## Run with the provided script

    ./build_and_run.sh backend <user_provided_name> <ranker e.g. WQSP_Ranker> <port>

## Disabling GPU
To disable GPU use run above commands with the environment variable `NO_GPU=1`

## Commands to run training in nvidia-docker manually
    NAME=nameit
    nvidia-docker build -t tf_aqqu --build-arg TENSORFLOW=gcr.io/tensorflow/tensorflow:latest-gpu-py3 \
       -f Dockerfile.learner .
    nvidia-docker run --rm -it --name tf_aqqu_learner_inst 
       --build-arg TENSORFLOW=gcr.io/tensorflow/tensorflow:latest-gpu-py3
       -v $(pwd)/data/:/app/data \
       -v $(pwd)/input/:/app/input \
       -v $(pwd)/models/:/app/models \
       tf_aqqu

## Commands to run the backend in nvidia-docker manually

    NAME=nameit
    nvidia-docker run --rm -it --name tf_aqqu_backend_inst \ 
       -v $(pwd)/data/:/app/data \
       -v $(pwd)/input/:/app/input \
       -v $(pwd)/models/:/app/models \
       tf_aqqu translator_server WQSP_Ranker



