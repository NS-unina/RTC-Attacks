# Docker Images Export

This directory contains exported Docker images from the RTC-Attacks lab environments as tarballs.

## Purpose

These tarballs allow you to:
- Share lab images without requiring rebuilds
- Deploy labs in offline environments
- Archive specific image versions
- Transfer images between machines

## Usage

### Export Images

To export all lab images as tarballs:

```bash
./scripts/export_lab_images.sh
```

**Note**: Images must be built first. If an image is missing, build it with:

```bash
cd public/labs/<lab_directory>
docker compose build
```

The exported tarballs will be saved in `docker-images/` directory.

### Import Images

To import all tarballs on another machine:

```bash
./scripts/import_lab_images.sh
```

Or import a single image:

```bash
docker load -i docker-images/<image-name>.tar
```

## Exported Images

The following custom lab images are exported:

- `freeswitch` - FreeSWITCH VoIP server (Labs 1-2)
- `attacker` - Generic attacker container (Lab 1-2)
- `sip-cli-fs` - SIP CLI client for FreeSWITCH (Lab 1-2)
- `kamailio` - Kamailio SIP server (Lab 3)
- `sipp101` - SIPp testing tool (Lab 3)
- `asterisk` - Asterisk PBX server (Lab 4)
- `baresip-cli` - Baresip CLI client (Lab 4)
- `sippts` - SIP penetration testing suite (Lab 4)
- `wireshark` - Network protocol analyzer (Lab 4)
- `coturn` - TURN/STUN server (Lab 5)
- `stunner` - STUN/TURN client (Lab 5)
- `node_socketiofile` - Socket.IO vulnerable app (Lab 6)
- `vdoninja` - VDO.Ninja platform (Labs 7-8)
- `node_mongoose` - MongoDB/Mongoose app (Labs 7-8)
- `node_firefox` - Firefox vulnerable web app (Lab 9)
- `gophish` - Phishing framework (Lab 9)
- `firefox` - Firefox browser container (Lab 9)

**External images** (pulled from Docker Hub) are **not** exported:
- `mongo` - MongoDB database
- `curlimages/curl:8.8.0` - cURL utility

These can be pulled with: `docker pull <image-name>`

## File Size

Docker image tarballs can be large (100MB - 2GB each). The `.gitignore` in this directory excludes `*.tar` files from version control.

## Cleanup

To remove all exported tarballs:

```bash
rm -rf docker-images/*.tar
```
