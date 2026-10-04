# Bundled data (Qt-free)

## `dbip-asn-lite.mmdb.gz`

DB-IP Lite ASN, month in `dbip-asn-lite.month`, from
<https://db-ip.com/db/download/ip-to-asn-lite>
(`https://download.db-ip.com/free/dbip-asn-lite-YYYY-MM.mmdb.gz`, unchanged).

**Licence: Creative Commons Attribution 4.0 International.** Attribution:
"IP Geolocation by DB-IP" with a link to https://db-ip.com, shown in About,
Help > Third-Party Notices, the map, and every export.

Shipped so the AS path works offline from the first trace. It is unpacked into
the data folder on first use (`routemap/dbip.py`); Settings > Sources > Update
now replaces it with a newer month. Refresh this copy at release time:

    curl -fLo routemap/data/dbip-asn-lite.mmdb.gz \
      https://download.db-ip.com/free/dbip-asn-lite-YYYY-MM.mmdb.gz
    printf 'YYYY-MM\n' > routemap/data/dbip-asn-lite.month

DB-IP Lite City is not shipped (60 MB compressed): the app downloads it on
first run when the user agrees, or imports a file the user provides.
