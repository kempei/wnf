FROM joyzoursky/python-chromedriver:3.7-alpine3.8-selenium

ARG project_dir=/tmp/work
RUN mkdir $project_dir
ADD requirements.txt $project_dir
WORKDIR $project_dir

RUN apk update && \
    apk add postgresql-libs && \
    apk add --virtual .build-deps gcc musl-dev postgresql-dev && \
    pip install --upgrade pip && \
    pip install -r requirements.txt && \
    apk --purge del .build-deps && \
    find /usr/local -depth \
    \( \
		\( -type d -a \( -name test -o -name tests \) \) \
		-o \
		\( -type f -a \( -name '*.pyc' -o -name '*.pyo' \) \) \
	\) \
	-exec rm -rf '{}' +; \
	rm -f get-pip.py

ADD prepare.py $project_dir
ADD scraper.py $project_dir
ADD simpleslack.py $project_dir
ADD trade.py $project_dir
ADD wnf.py $project_dir
ADD sbi.py $project_dir

CMD [ "python", "-u", "/tmp/work/trade.py" ]
