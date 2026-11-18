#!/usr/bin/env bash
# Download the three public datasets into data/external/ (plain git clones).
set -e
mkdir -p data/external
cd data/external
[ -d ec-darkpattern ] || git clone --depth 1 https://github.com/yamanalab/ec-darkpattern
[ -d dark-patterns ]  || git clone --depth 1 https://github.com/aruneshmathur/dark-patterns
[ -d AidUI ]          || git clone --depth 1 https://github.com/SageSELab/AidUI
echo "Datasets ready in data/external/"
