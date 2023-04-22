# navdata_sql
A tool to convert FAA CIFP aviation navdata ARINC 424 files into an SQLite database for easy querying.

## Quickstart

Get the download link for the latest data from the FAA on the [dataset homepage](https://www.faa.gov/air_traffic/flight_info/aeronav/digital_products/cifp/download/).

```
$ wget 'https://aeronav.faa.gov/Upload_313-d/cifp/CIFP_230420.zip' # Get latest URL with link above
$ unzip CIFP_230420.zip
$ python navdata_sql --output avdb.sqlite FAACIFP18

$ sqlite3 -header -column avdb.sqlite
SQLite version 3.39.3 2022-09-05 11:02:23
Enter ".help" for usage hints.
sqlite> SELECT code,name,airport_elevation,latitude,longitude,airport_elevation,longest_runway_surface_code,ifr_capability FROM Airport WHERE area_code='USA' LIMIT 20;
code  name                       airport_elevation  latitude   longitude    airport_elevation  longest_runway_surface_code  ifr_capability
----  -------------------------  -----------------  ---------  -----------  -----------------  ---------------------------  --------------
00AA  AERO B RANCH               3435               38.704022  -101.473911  3435               S                            N
00AL  EPPS AIRPARK               820                34.864811  -86.770278   820                S                            N
00AR  ARLAND                     1352               38.969650  -97.601556   1352               S                            N
00AS  FULTON                     1100               34.942803  -97.818019   1100               S                            N
00C   ANIMAS AIR PARK            6684               37.203178  -107.869194  6684               H                            N
00CA  GOLDSTONE /GTS/            3038               35.354972  -116.885208  3038               H                            N
00CL  WILLIAMS AG                87                 39.427189  -121.763428  87                 H                            N
00F   BROADUS                    3282               45.470472  -105.457139  3282               H                            N
00FA  GRASS PATCH                53                 28.645547  -82.218975   53                 H                            N
00FL  RIVER OAK                  35                 27.230881  -80.969231   35                 S                            N
00GA  LT WORLD                   700                33.767500  -84.068333   700                S                            N
00ID  DELTA SHORES               2064               48.145278  -116.214444  2064               S                            N
00IG  GOLTL                      3359               39.724028  -101.395994  3359               S                            N
00IL  HAMMER                     840                41.978364  -89.560389   840                S                            N
00IS  HAYENGA'S CANT FIND FARMS  820                40.025594  -89.122864   820                S                            N
00KS  HAYDEN FARM                1100               38.727786  -94.930519   1100               S                            N
00KY  ROBBINS ROOST              1265               37.409444  -84.619722   1265               S                            N
00LS  LEJEUNE                    12                 30.136278  -92.429361   12                 S                            N
00M   THIGPEN FLD                351                31.953750  -89.235333   351                H                            N
00MD  SLATER FLD                 45                 38.757058  -75.753822   45                 S                            N
sqlite>

```

## Examples

Run the report script to see the output of several example queries.

```

$ bash report

Longest paved runways
=====================

code  apt name                        id     length (ft)
----  ------------------------------  -----  -----------
KDEN  DENVER INTL                     RW16R  16000
KDEN  DENVER INTL                     RW34L  16000
KEDW  EDWARDS AFB                     RW05R  15024
KEDW  EDWARDS AFB                     RW23L  15024
KTTS  SPACE FLORIDA LAUNCH AND LANDI  RW15   15001
KTTS  SPACE FLORIDA LAUNCH AND LANDI  RW33   15001
KVBG  VANDENBERG SPACE FORCE BASE     RW12   15000
KVBG  VANDENBERG SPACE FORCE BASE     RW30   15000
PAEI  EIELSON AFB                     RW14   14530
PAEI  EIELSON AFB                     RW32   14530
KLAS  HARRY REID INTL                 RW08L  14515
KLAS  HARRY REID INTL                 RW26R  14515
KJFK  JOHN F KENNEDY INTL             RW13R  14511
KJFK  JOHN F KENNEDY INTL             RW31L  14511
KNFL  FALLON NAS (VAN VOORHIS FLD)    RW13R  14001
KNFL  FALLON NAS (VAN VOORHIS FLD)    RW31L  14001
KSKA  FAIRCHILD AFB                   RW05   13899
KSKA  FAIRCHILD AFB                   RW23   13899
KABQ  ALBUQUERQUE INTL SUNPORT        RW08   13793
KABQ  ALBUQUERQUE INTL SUNPORT        RW26   13793


Airports with more than 8 runways
=================================

code  apt name                        runway count
----  ------------------------------  ------------
KORD  CHICAGO O'HARE INTL             16
KDFW  DALLAS-FORT WORTH INTL          14
PHNL  DANIEL K INOUYE INTL            12
KDTW  DETROIT METRO WAYNE COUNTY      12
KDEN  DENVER INTL                     12
KBOS  GENERAL EDWARD LAWRENCE LOGAN   12
KTCS  TRUTH OR CONSEQUENCES MUNI      10
KMWH  GRANT COUNTY INTL               10
KMKE  GENERAL MITCHELL INTL           10
KMDW  CHICAGO MIDWAY INTL             10
KIAH  GEORGE BUSH INTCNTL/HOUSTON     10
KFST  FORT STOCKTON-PECOS COUNTY      10
KATL  HARTSFIELD - JACKSON ATLANTA I  10


Runways with a localizer backcourse approach
============================================

code  runway
----  ------
PABR  26
PACD  33
PAHO  22
PAKN  30
PAOM  10
PASC  24
PAYA  29
KALO  30
KBMI  11
KBRO  31

...

```

## Using spatialite for distance calculations

Geographic coordinates in the SQL database are compatible with the [spatialite](https://www.gaia-gis.it/fossil/libspatialite/index) SQLite extension. This can be for useful to compute distances between locations found in the database.

To do so, install the spatialite SQLite extension (example for Debian):

```
# apt install libsqlite3-mod-spatialite
```

When using SQLite, first load the spatialite extension:

```
sqlite> SELECT load_extension('mod_spatialite');
```

Before much of the spatialite functionality can be used, a database created with `navdata_sql` must be augmented with metadata tables:

```
sqlite> SELECT InitSpatialMetaData("WGS84");
```

Thereafter, spatialite functions can be used in SQL queries. Here we lookup the airports within 20nm of downtown Philadelphia, limiting the results to airports whose longest runway is hard-surfaced:


```
sqlite> SELECT code AS apt, name, longest_runway * 100 AS longest_rwy_ft, ROUND(CvtToKmi(GeodesicArcLength(makepoint(-75.163625, 39.952371, 4326), makepoint(CAST(longitude AS decimal), CAST(latitude AS decimal), 4326))), 2) AS dist_nm FROM airport WHERE longest_runway_surface_code='H' AND dist_nm <= 20 ORDER BY dist_nm;
apt   name                    longest_rwy_ft  dist_nm
----  ----------------------  --------------  -------
KPHL  PHILADELPHIA INTL       12000           5.98
KPNE  NORTHEAST PHILADELPHIA  7000            10.49
KLOM  WINGS FLD               3700            12.05
19N   CAMDEN COUNTY           3000            14.43
KVAY  SOUTH JERSEY RGNL       3800            14.68
3NJ6  INDUCTOTHERM            4000            15.34
17N   CROSS KEYS              3500            15.99
N14   FLYING W                3400            16.48
7N7   OLDMANS TOWNSHIP        2400            16.91
JY73  RED LION                2800            19.33
KOQN  BRANDYWINE RGNL         3300            19.43
32PA  PERKIOMEN VALLEY        2800            19.45

```
