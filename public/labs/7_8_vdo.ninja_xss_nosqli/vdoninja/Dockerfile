# Previous implementation kept for traceability:
# FROM projectdiscovery/nuclei:latest
# WORKDIR /app
# COPY cve-2025-62613.yaml /app/templates/cve-2025-62613.yaml
# ENTRYPOINT ["nuclei"]
#
# Change rationale: this service must run vulnerable VDO.Ninja, while Nuclei belongs to a
# separate proof-of-concept scanner container. The nginx-based image below serves VDO.Ninja
# v28.0 so the XSS scenario can be exercised by the lab stack itself.
FROM --platform=linux/amd64 alpine:latest

RUN apk add --no-cache git nginx

RUN git clone --branch v28.0 --single-branch https://github.com/steveseguin/vdo.ninja /usr/share/vdo.ninja

RUN mkdir -p /run/nginx

COPY nginx.conf /etc/nginx/http.d/default.conf

WORKDIR /usr/share/vdo.ninja

EXPOSE 18080

CMD ["nginx", "-g", "daemon off;"]
