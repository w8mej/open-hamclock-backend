## Project Completion Status

HamClock requests about 40+ artifacts. I have locally replicated all of them that I could find.

### Dynamic Text Files
- [x] Bz/Bz.txt
- [x] aurora/aurora.txt
- [x] xray/xray.txt
- [x] worldwx/wx.txt
- [x] esats/esats.txt
- [x] solarflux/solarflux-history.txt
- [x] ssn/ssn-history.txt
- [x] solar-flux/solarflux-99.txt
- [x] geomag/kindex.txt
- [ ] dst/dst.txt - proxied by CSI until we can work out kinks
- [x] drap/stats.txt
- [x] solar-wind/swind-24hr.txt
- [x] ssn/ssn-31.txt
- [x] ONTA/onta.txt
- [x] contests/contests311.txt
- [x] dxpeds/dxpeditions.txt
- [x] NOAASpaceWX/noaaswx.txt
- [x] ham/HamClock/cty/cty_wt_mod-ll-dxcc.txt
      
### Dynamic Map Files
Note: Anything under maps/ is considered a "Core Map" in HamClock

- [x] maps/Clouds*
- [x] maps/Countries*
- [x] maps/Wx-mB*
- [x] maps/Aurora
- [x] maps/DRAP
- [x] maps/MUF-RT
- [x] maps/Terrain
- [x] SDO/*

### Dynamic Web Endpoints
- [x] ham/HamClock/RSS/web15rss.pl
- [x] ham/HamClock/version.pl
- [x] ham/HamClock/wx.pl
- [x] ham/HamClock/fetchIPGeoloc.pl - requires free tier 1000 req per day account and API key
- [x] ham/HamClock/fetchBandConditions.pl
- [ ] ham/HamClock/fetchVOACAPArea.pl - proxied by CSI until we can work out complex task
- [ ] ham/HamClock/fetchVOACAP-MUF.pl - proxied by CSI until we can work out complex task
- [ ] ham/HamClock/fetchVOACAP-TOA.pl - proxied by CSI until we can work out complex task
- [x] ham/HamClock/fetchPSKReporter.pl=
- [x] ham/HamClock/fetchWSPR.pl
- [x] ham/HamClock/fetchRBN.pl

### Static Files
- [x] ham/HamClock/cities2.txt
- [x] ham/HamClock/NOAASpaceWx/rank2_coeffs.txt

## Integration Testing Status
- [x] GOES-16 X-Ray
- [x] Countries map download
- [x] Terrain map download
- [x] SDO generation, download, and display
- [x] MUF-RT map generation, download, and display
- [x] Weather map generation, download, and display
- [x] Clouds map generation, download, and display
- [x] Aurora map generation, download, and display
- [x] Aurora map generation, download, and display
- [x] Parks on the Air generation, pull and display
- [x] SSN generation, pull, and display
- [x] Solar wind generation, pull and display
- [x] DRAP data generation, pull and display
- [x] Planetary Kp data generation, pull and display
- [x] Solar flux data generation, pull and display
- [x] Amateur Satellites data generation, pull and display
- [x] PSK Reporter WSPR
- [X] VOACAP DE DX - proxied
- [x] VOACAP MUF MAP - proxied
- [x] RBN
