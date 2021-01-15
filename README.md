# akamai-samples
This package contains some examples of how akamai API's can be used to get specific information of your Akamai configuration. Be noted that error-handling is limited or absent, be prepare for stack-traces or silent failures.

## akamai-get
Extension based on or on top of the already existing command-line utilities.

General usage:
```
$ python3 akamai-get.py --help
```
or when you are on linux/MAC and your path is setup correctly
```
akamai-get --help
```
Tip:
Use --json file.json to get full info instead of the abbreviated text

### akamai-get urldebug
Use the diagnostic urldebug API to get information related to a request
```
$ akamai-get urldebug https://debeij.example.com/get
```
```
Edge Status Code      : 200
Origin Response Code  : 200
Origin Server Host    : origin.example.org
Origin Server IP      : 1.2.3.4
Cache Setting         : TCP_MISS
CpCode                : 123456
Error Message (if any): -
```

Use the JSON output to view the logfiles and other related information

### akamai-get reference
Use the diagnostics errors API to get information for an Akamai reference code. No need to html-decode.

```
$ akamai-get reference '6.2c373217.1610710834.3647c1'
```
```
url                   : https://debeij.example.com/error
httpResponseCode      : 503
timestamp             : Fri, Jan 15, 2021 11:38 GMT
epochTime             : 1610710716
clientIp              : 163.158.10.35 (AMSTERDAM,-,NL)
connectingIp          : 163.158.10.35 (AMSTERDAM,-,NL)
serverIp              : 23.50.55.44 (FRANKFURT,HE,DE)
userAgent             : -
requestMethod         : GET
reasonForFailure      : Connection to the origin server from the edge server timed out and the connection was never established. Also see: <a href="https://control.akamai.com/core/search/kb_article.search?articleId=4719">KB 4719</a>
wafDetails
```

Use the JSON output to view the logfiles and other related information

### akamai-get origins
Use the property manager API to get origins linked to host via the property manager (used and not used).
Be noted that not all origins might be actually used by the external hostname based on property manager logic

```
$ akamai-get origins debeij.example.get
```
```
origin.example.org
example.download.akamai.com
```

Use the JSON output to review the origin definition