FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt update \
 && ln -fs /usr/share/zoneinfo/America/New_York /etc/localtime \
 && apt install -y openscad python3-pip \
 && pip3 install solidpython

COPY create_tray_solidpython.py /bin/create_tray_solidpython.py

WORKDIR /mnt

ENTRYPOINT ["python3", "/bin/create_tray_solidpython.py"]
