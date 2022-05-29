#!/bin/sh
mkdir real 
mkdir fake 
python3 ./run_generator.py $1 $2 $3 $4 
pip install pytorch-fid 
python -m pytorch_fid --device cuda:0 ./real/ ./fake/ 
