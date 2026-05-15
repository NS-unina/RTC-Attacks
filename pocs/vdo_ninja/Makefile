NUCLEI_POC :=/root/nuclei-templates/http/cves/2025/CVE-2025-62613.yaml
IP_ADDRESS ?= 192.168.1.50

build:
	@docker build -t poc-7vdoninja .

run: build
	@docker run --rm -it --net=host --name poc-7 poc-7vdoninja -t ${NUCLEI_POC} -u http://${IP_ADDRESS}