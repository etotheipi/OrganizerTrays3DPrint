FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt update \
 && ln -fs /usr/share/zoneinfo/America/New_York /etc/localtime \
 && apt install -y openscad python3-pip \
 && mkdir -p /bin/gentray/flask_serve

COPY requirements.txt /bin/gentray/
COPY flask_serve/requirements.txt /bin/gentray/flask_serve/

RUN pip3 install -r /bin/gentray/requirements.txt \
 && pip3 install -r /bin/gentray/flask_serve/requirements.txt

COPY *.py /bin/gentray/
COPY *.txt /bin/gentray/
COPY ./flask_serve/ /bin/gentray/flask_serve/

WORKDIR /mnt
EXPOSE 5000

ENTRYPOINT ["python3", "/bin/gentray/generate_tray.py"]
