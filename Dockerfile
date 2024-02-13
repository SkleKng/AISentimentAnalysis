# syntax=docker/dockerfile:1

#WIP NOT TO BE USED

FROM selenium/standalone-chrome
USER root
WORKDIR /python-docker

COPY requirements.txt requirements.txt
# RUN wget https://bootstrap.pypa.io/get-pip.py
# RUN python3 get-pip.py
# RUN python3 -m pip install -r requirements.txt
# RUN apt update -y
# # RUN apt upgrade -y
# # RUN apt install chromium-browser
# # RUN apt install chromium-chromedriver


COPY . .

CMD [ "python3", "app.py"]