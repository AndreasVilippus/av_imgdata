include /env.mak

JS_DIR=dist
JS_NAMESPACE=SYNO.SDS.App.AV_ImgData
BUNDLE_JS=dist/av-img-data.bundle.js
BUNDLE_CSS=dist/style/av-img-data.bundle.css
APP_JS=AV_ImgData.js
APP_CONFIG_INDEX=config
MAKEFILE_JS_INC=Makefile.js.inc
MODULE_GENERATOR?=/pkgscripts-ng/tool/GenerateModuleFiles.php
AUTO_CONFIG_TOOL?=/usr/local/tool/parse_requires.py
JS_DEPENDER?=/usr/syno/bin/GenerateJSDepend.php
DSM_HELP_RENDERER=../tools/docs/render_dsm_help.py
DSM_HELP_SOURCES=$(shell find ../docs/core/de ../docs/core/en -type f -name '*.md' 2>/dev/null)
DSM_HELP_STAMP=.dsm-help.stamp

.PHONY: all clean $(SUBDIR) dsm-help

all: dsm-help $(APP_JS) style.css $(APP_CONFIG_INDEX) $(SUBDIR)

dsm-help: $(DSM_HELP_STAMP)

$(DSM_HELP_STAMP): $(DSM_HELP_RENDERER) $(DSM_HELP_SOURCES) ../INFO.sh
	python3 $(DSM_HELP_RENDERER)
	@touch $@

$(BUNDLE_JS):
	# Snpm is a tool to install npm modules in Synology
	PYTHONIOENCODING=utf-8 /usr/local/tool/snpm install
	PYTHONIOENCODING=utf-8 /usr/local/tool/snpm run build

$(APP_JS): $(BUNDLE_JS)
	cp $(BUNDLE_JS) $@

$(SUBDIR):
	@echo "===>" $@
	$(MAKE) -C $@ INSTALLDIR=$(INSTALLDIR)/$@ DESTDIR=$(DESTDIR) PREFIX=$(PREFIX) $(MAKECMDGOALS);
	@echo "<===" $@

style.css: $(BUNDLE_JS)
	cp $(BUNDLE_CSS) $@

$(MAKEFILE_JS_INC): config.define
	if [ -x "$(MODULE_GENERATOR)" ]; then \
		"$(MODULE_GENERATOR)" . .; \
	elif command -v GenerateModuleFiles.php >/dev/null 2>&1; then \
		GenerateModuleFiles.php . .; \
	else \
		printf '# GenerateModuleFiles.php not available outside Synology Toolkit\n' > $@; \
	fi

$(APP_CONFIG_INDEX): app.config config.define $(BUNDLE_JS) $(MAKEFILE_JS_INC)
	rm -f auto_config.debug config.depends $@
	if [ -x "$(AUTO_CONFIG_TOOL)" ] && [ -x "$(JS_DEPENDER)" ]; then \
		"$(AUTO_CONFIG_TOOL)" --makegoal=JSCompress $(JS_DIR) "$(JS_NAMESPACE)" && \
		"$(JS_DEPENDER)" "$$(pwd)" "" && \
		[ -s "$@" ]; \
	else \
		printf '{"AV_ImgData.js":{"SYNO.SDS.App.AV_ImgData.Instance":{"depend":[],"title":"ImgData","appWindow":"SYNO.SDS.App.AV_ImgData.Instance","allUsers":true,"allowMultiInstance":false,"hidden":false,"type":"app","icon":"images\\/icon.png"}}}' > $@; \
	fi

clean:
	rm -rf dist
	rm -f $(APP_JS) style.css $(APP_CONFIG_INDEX) $(MAKEFILE_JS_INC) auto_config.debug config.depends $(DSM_HELP_STAMP)

install: dsm-help $(APP_JS) style.css $(APP_CONFIG_INDEX) $(SUBDIR)
	[ -d $(INSTALLDIR) ] || install -d $(INSTALLDIR)
	install -m 644 $(APP_JS) $(INSTALLDIR)/$(APP_JS)
	install -m 644 style.css $(INSTALLDIR)/style.css
	install -m 644 $(APP_CONFIG_INDEX) $(INSTALLDIR)/$(APP_CONFIG_INDEX)
	[ -d $(INSTALLDIR)/texts ] || install -d $(INSTALLDIR)/texts
	cp -a texts $(INSTALLDIR)
	[ -d $(INSTALLDIR)/help ] || install -d $(INSTALLDIR)/help
	cp -a help $(INSTALLDIR)
	if [ -f helptoc.conf ]; then install -m 644 helptoc.conf $(INSTALLDIR)/helptoc.conf; fi
	[ -d $(INSTALLDIR)/images ] || install -d $(INSTALLDIR)/images
	cp -a images $(INSTALLDIR)
	install -m 755 index.cgi $(INSTALLDIR)/index.cgi
	install -m 644 app.config $(INSTALLDIR)/app.config
	install -m 644 config.define $(INSTALLDIR)/config.define

packageinstall: $(SUBDIR)
