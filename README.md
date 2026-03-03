# 🛟 OHB — Open HamClock Backend

When the original backend went dark, the clocks didn’t have to.

Open-source, self-hostable backend replacement for HamClock — restoring live propagation data, maps, and feeds.

What's a backend? It is how HamClock got all of its data. Without a separate backend, all HamClock's will cease to function by June 2026.

Drop-in compatible with existing HamClock's — no firmware changes required.

OHB provides faithful replacements for the data feeds and map assets
that HamClock depends on — built by operators, for operators.

> This project is not affiliated with HamClock or its creator,
> Elwood Downey, WB0OEW.
> We extend our sincere condolences to the Downey family.

## ✨ What OHB Does

- Rebuilds HamClock dynamic text feeds (solar, geomag, DRAP, PSK, RBN, WSPR, Amateur Satellites, DxNews, Contests, etc)
- Generates map overlays (MUF-RT, DRAP, Aurora, Wx-mB, etc.)
- Produces zlib-compressed BMP assets in multiple resolutions
- Designed for Raspberry Pi, cloud, or on-prem deployment
- Fully open source and community maintained
- Auto log rotation
- Command and Control Dashboard (future)
- Secure

## 🧭 Architecture
```
[ NOAA / KC2G / PSK / SWPC ]
              |
              v
        +-------------+
        |     OHB     |
        |-------------|
        | Python/Perl|
        | GMT/Maps   |
        | Cron Jobs  |
        +-------------+
              |
           HTTP/ZLIB
              |
         +----------+
         | lighttpd |
         +----------+
              |
         +----------+
         | HamClock |
         +----------+
```

## 💬 Join us on Discord
We are building a community-powered backend to keep HamClock running. \
Discord is where we can collaborate, troubleshoot, and exchange ideas — no RF license required 😎 \
https://discord.gg/wb8ATjVn6M

# OHB in Production (Live HamClock Clients)

## Automatic AMSAT Satellite Updater Backend - Keep Your Satellites Fresh!
<img width="795" height="459" alt="image" src="https://github.com/user-attachments/assets/47ee3b6f-2075-42e2-a55f-618a0fb9fad5" />
<img width="798" height="568" alt="image" src="https://github.com/user-attachments/assets/14b24350-c0a5-4b00-a36f-9c34c74fef3d" />
<img width="799" height="568" alt="image" src="https://github.com/user-attachments/assets/f10d67f5-186c-43b6-b9d9-71149fd897f7" />
<img width="804" height="482" alt="image" src="https://github.com/user-attachments/assets/e1778c0e-e22c-4a42-8e50-789b1bc85692" />
<img width="797" height="569" alt="image" src="https://github.com/user-attachments/assets/35e843bf-f2c6-4b99-881b-1bf675660b7a" />
<img width="797" height="571" alt="image" src="https://github.com/user-attachments/assets/859d158c-e441-4788-bd67-3aaa48be45e0" />
<img width="801" height="480" alt="image" src="https://github.com/user-attachments/assets/8313d34e-e71c-4455-98c4-7f204d3ac59f" />
<img width="805" height="486" alt="image" src="https://github.com/user-attachments/assets/c59d485f-08ed-4bf6-85e1-aed5e4a6cabe" />
<img width="822" height="505" alt="image" src="https://github.com/user-attachments/assets/0a0b8c73-293e-4723-a8ba-c32abdfa7bdd" />
<img width="803" height="487" alt="image" src="https://github.com/user-attachments/assets/c507f348-bdda-4683-9473-796545067e0e" />

## 🚀 Quick Start 👉 [Quick Start Guide](QUICK_START.md)
## 📦 Installation 👉 [Detailed installation instructions](INSTALL.md)
## 📊 Project Completion Status

OHB targets ~40+ HamClock artifacts (feeds, maps, and endpoints).

As of today:

- All core dynamic maps implemented
- All text feeds replicated
- Amateur satellites with fresh TLEs
- RSS feed works for thousands for clients
- Integration-tested on live HamClock clients
- Remaining work focused on VOACAP + RBN endpoints  

👉 Full artifact tracking and integration status:
[PROJECT_STATUS.md](PROJECT_STATUS.md) 
## 📚 Data Attribution 👉 [Attribution](ATTRIBUTION.md)
## 🤝 Contributing
Bug reports and pull requests are welcome on GitHub at
https://github.com/BrianWilkinsFL/open-hamclock-backend/issues
## Related
- [ohb-pskreporter-proxy](https://github.com/BrianWilkinsFL/ohb-pskreporter-proxy)
- [hamclock-proxy-lite](https://github.com/BrianWilkinsFL/hamclock-proxy-lite)
- [HamClockLauncher](https://github.com/huberthickman/HamClockLauncher)
