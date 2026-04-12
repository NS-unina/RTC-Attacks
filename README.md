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

After that you can connect at: ```http://localhost:8888```


# Disclaimer

This project is intended for educational and research purposes only.
Do not deploy or use these scenarios against systems without explicit authorization.
