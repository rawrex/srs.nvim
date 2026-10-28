rm -rf test; echo 'Romoved old test' &&\
mkdir test && echo 'New test dir' && cd test &&\
git init && echo 'Inited new git repo' &&\
python3 ../setup/install.py && echo 'Installed SRS' &&\
git add .srs/index.txt && git commit -m 'Inited srs' && echo 'Added SRS to git' &&\
cp -rv ../test_data/* . && git add -A && git commit -m 'Added test data' &&\
python ../scripts/scan.py . &&\
git add -A && git commit -m 'Scanned notes' && echo 'Added scanned files to git' &&\
nvim . &&\
cd ..
