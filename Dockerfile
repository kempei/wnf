FROM python:3.11-alpine3.18

# update apk repo
RUN echo "http://dl-4.alpinelinux.org/alpine/v3.18/main" >> /etc/apk/repositories && \
    echo "http://dl-4.alpinelinux.org/alpine/v3.18/community" >>  /etc/apk/repositories

VOLUME /tmp/

ARG project_dir=/tmp/work
WORKDIR $project_dir
ADD requirements.txt $project_dir

RUN apk add --no-cache --virtual .build-deps \
    gcc \
    python3-dev \
    musl-dev \
    libffi-dev \
    build-base && \
    apk add --no-cache \
    chromium \
    chromium-chromedriver \
    sqlite-dev && \
    pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    apk del --no-cache .build-deps && \
    find /usr/local -depth \
    \( \
    \( -type d -a \( -name test -o -name tests \) \) \
    -o \
    \( -type f -a \( -name '*.pyc' -o -name '*.pyo' \) \) \
    \) -exec rm -rf '{}' + && \
    rm -f get-pip.py && \
    rm -Rf /root/.cache/

COPY wnf/ $project_dir/wnf/
COPY tests/ $project_dir/tests/
ADD run.sh $project_dir/

CMD [ "/tmp/work/run.sh" ]
