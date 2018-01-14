#/bin/sh

# Get ffmpeg
wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-64bit-static.tar.xz
tar xvf ffmpeg-release-64bit-static.tar.xz
mv ffmpeg-*-64bit-static/ffmpeg ./

rm -rf ffmpeg-*-64bit-static
rm -rf ffmpeg-release-64bit-static.tar.xz

# pip install
pip install -r requirements.txt -t ./
# remove unsed module
rm -rf concurrent/
