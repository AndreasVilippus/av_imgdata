#!/bin/bash

source /pkgscripts-ng/include/pkg_util.sh

package="AV_ImgData"
version="0.5.0"
displayname="ImgData"
description="Shell- & Python-Tool für Fotodatentransfer"
maintainer="Andreas Vilippus"
maintainer_url=""
arch="noarch"
os_min_ver="7.3-00000"

startable="yes"
privilege="yes"
support_cgi="yes"
#install_dep_packages="Python3"
beta="no"
reloadui="yes"
dsmappname="SYNO.SDS.App.AV_ImgData.Instance"
dsmuidir="ui"

[ "$(caller)" != "0 NULL" ] && return 0

pkg_dump_info
