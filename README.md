# RTC-Attacks
A reproducible security testbed for experimenting with attacks against real-time communication (RTC) systems, including SIP, RTP, and WebRTC environments.

The platform provides a web-based interface to deploy, execute, and monitor controlled attack scenarios with integrated observability.
![web_application](webapp.png)

## Scenarios
The following attacks are included:
- SIP Spoofing and SIP Flooding
- SIP Overflow
- RTP Injection
- Relay Abuse
- Remote Code Execution
- NoSQLi and XSS
- Permission Abuse

## Requirements
To use this web application, you need to have:
- nodejs
- docker
- docker-compose
- git
- make

Additionally, the following applications are required:
- Linphone
- Wireshark
- Firefox

## Setup
After installing the required software, clone the repository and move into the project directory:
```bash
git clone https://github.com/NS-unina/RTC-Attacks
cd RTC_Attacks
```
Install the dependencies and start the web application:
```bash
npm install
node server.js
```
At the first run, the application will automatically build the necessary Docker images for the attack scenarios, which may take some time.

If you want to monitor the build of the several images, you can run the following command before starting the web application:
```bash
docker-compose -f docker-compose.yml build --progress=plain
``` 
When the build is complete, you can start the web application as described above.


After that you can connect at: ```http://localhost:8888```


# Disclaimer

This project is intended for educational and research purposes only.
Do not deploy or use these scenarios against systems without explicit authorization.
