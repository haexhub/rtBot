FROM python:3.8

# RUN useradd -ms /bin/bash docker
# ENV VIRTUAL_ENV=/opt/venv
# ENV PATH=”$VIRTUAL_ENV/bin:$PATH”

WORKDIR /usr/src/app

COPY requirements.txt .

# RUN chown docker /usr/src/app 

# USER docker
RUN pip install -r requirements.txt

COPY . .
CMD ["python3", "./rtBot.py"]