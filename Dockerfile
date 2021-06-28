FROM python:3.9.1

# RUN useradd -ms /bin/bash docker
# ENV VIRTUAL_ENV=/opt/venv
# ENV PATH=”$VIRTUAL_ENV/bin:$PATH”
RUN apt-get update
WORKDIR /usr/src/app

COPY . .

# RUN chown docker /usr/src/app 

# USER docker
RUN pip install -r requirements.txt

#COPY . .
ENTRYPOINT [ "python3" ]
CMD ["rtBot.py"]