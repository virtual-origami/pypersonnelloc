FROM python:3.8.3-slim-buster AS base
RUN apt-get update && apt-get -y python3-pandas


# Dedicated Workdir for App
WORKDIR /pypersonnelloc

# Do not run as root
RUN useradd -m -r pypersonnelloc && \
    chown pypersonnelloc /pypersonnelloc

COPY requirements.txt /pypersonnelloc
# RUN pip3 install -r requirements.txt

FROM base AS src
COPY . /pypersonnelloc

# install pypersonnelloc here as a python package
RUN pip3 install .

# USER pypersonnelloc is commented to fix the bug related to permission
# USER pypersonnelloc

COPY scripts/docker-entrypoint.sh /entrypoint.sh

# Use the `personnel-localization` binary as Application
FROM src AS prod

# this is add to fix the bug related to permission
RUN chmod +x /entrypoint.sh

ENTRYPOINT [ "/entrypoint.sh" ]

CMD ["personnel-loc", "-c", "config.yaml"]
