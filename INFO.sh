#!/bin/bash

source /pkgscripts-ng/include/pkg_util.sh

package="AV_ImgData"
version="0.11.0"
displayname="ImgData"
description="Photo metadata and face matching with Python, shell, native C++, and external worker packages for offloading compute-intensive image processing."
description_enu="Photo metadata and face matching with Python, shell, native C++, and external worker packages for offloading compute-intensive image processing."
description_ger="Foto-Metadaten und Gesichtsabgleich mit Python, Shell, nativem C++ und externen Worker-Paketen zur Auslagerung rechenintensiver Bildprozesse."
maintainer="Andreas Vilippus"
maintainer_url=""
arch="$(pkg_get_platform)"
os_min_ver="7.4-00000"

startable="yes"
privilege="yes"
support_cgi="yes"
beta="no"
reloadui="yes"
dsmappname="SYNO.SDS.App.AV_ImgData.Instance"
dsmuidir="ui"

[ "$(caller)" != "0 NULL" ] && return 0

pkg_dump_info
