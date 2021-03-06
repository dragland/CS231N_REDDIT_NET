#!/usr/bin/env bash
#Davy Ragland | dragland@stanford.edu
#Adrien Truong | aqtruong@stanford.edu
#CS231N_REDDIT_NET | 2018

python classifier.py -t -l=1e-4 -e -i=datasets/cats50.jpg
python classifier.py -t -l=5e-5 -e -i=datasets/cats50.jpg
python classifier.py -t -l=1e-5 -e -i=datasets/cats50.jpg
python classifier.py -t -l=5e-6 -e -i=datasets/cats50.jpg
python classifier.py -t -l=1e-6 -e -i=datasets/cats50.jpg

tail -n +1 experiments/*/val_acc.txt