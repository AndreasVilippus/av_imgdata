include /env.mak

JS_DIR="dist"
JS_NAMESPACE="SYNO.SDS.App.AV_ImgData"
BUNDLE_JS="dist/av-img-data.bundle.js"
BUNDLE_CSS="dist/style/av-img-data.bundle.css"

.PHONY: all clean $(SUBDIR)

all: $(BUNDLE_JS) style.css $(SUBDIR)

$(BUNDLE_JS):
	# Snpm is a tool to install npm modules in Synology
	/usr/local/tool/snpm install
	/usr/local/tool/snpm run build
	$(MAKE) -f Makefile.js.inc JSCompress JS_NAMESPACE=\"${JS_NAMESPACE}\" JS_DIR=${JS_DIR}

$(SUBDIR):
	@echo "===>" $@
	$(MAKE) -C $@ INSTALLDIR=$(INSTALLDIR)/$@ DESTDIR=$(DESTDIR) PREFIX=$(PREFIX) $(MAKECMDGOALS);
	@echo "<===" $@

style.css: $(BUNDLE_JS)
	cp $(BUNDLE_CSS) $@

clean: clean_JSCompress
	rm -rf dist
	rm -f style.css

install: $(SUBDIR) install_JSCompress
	[ -d $(INSTALLDIR)/texts ] || install -d $(INSTALLDIR)/texts
	cp -a texts $(INSTALLDIR)
	[ -d $(INSTALLDIR)/images ] || install -d $(INSTALLDIR)/images
	cp -a images $(INSTALLDIR)
	install -m 755 index.cgi $(INSTALLDIR)/index.cgi
	install -m 644 app.config $(INSTALLDIR)/app.config
	install -m 644 config.define $(INSTALLDIR)/config.define

packageinstall: $(SUBDIR)

include Makefile.js.inc
