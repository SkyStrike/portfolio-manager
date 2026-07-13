#!/bin/bash

docker build -t portfolio-manager:1.0 .
docker run -d -p 8080:8080 --name portfolio-manager portfolio-manager:1.0