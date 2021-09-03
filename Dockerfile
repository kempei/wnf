FROM python:3.9.6-alpine3.14

# update apk repo
RUN echo "http://dl-4.alpinelinux.org/alpine/v3.13/main" >> /etc/apk/repositories && \
    echo "http://dl-4.alpinelinux.org/alpine/v3.13/community" >> /etc/apk/repositories

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
