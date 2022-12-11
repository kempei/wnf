FROM python:3.9-alpine3.15

# update apk rep
RUN echo "http://dl-4.alpinelinux.org/alpine/v3.15/main" >> /etc/apk/repositories && \
    echo "http://dl-4.alpinelinux.org/alpine/v3.15/community" >> /etc/apk/repositories

# install chromedriver
RUN apk add --update --no-cache \
    chromium chromium-chromedriver \
    py3-aiohttp py3-multidict py3-yarl postgresql-libs

ARG project_dir=/tmp/work
RUN mkdir $project_dir
ADD requirements.txt $project_dir
WORKDIR $project_dir

RUN apk add --no-cache --virtual .build-deps \
    gcc \
    python3-dev \
    musl-dev \
    libffi-dev \
    build-base \
    postgresql-dev && \
    pip install --no-cache-dir -r requirements.txt && \
    apk del --no-cache .build-deps && \
    find /usr/local -depth \
    \( \
		\( -type d -a \( -name test -o -name tests \) \) \
		-o \
		\( -type f -a \( -name '*.pyc' -o -name '*.pyo' \) \) \
	\) \
	-exec rm -rf '{}' +

COPY wnf/ $project_dir/wnf/
ADD run.sh $project_dir/

CMD [ "/tmp/work/run.sh" ]
