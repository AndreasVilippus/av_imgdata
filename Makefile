## You can use CC CFLAGS LD LDFLAGS CXX CXXFLAGS AR RANLIB READELF STRIP after include env.mak
include /env.mak

SUBDIR=ui

.PHONY: all install $(SUBDIR)

all: $(SUBDIR)

$(SUBDIR):
	@echo "===>" $@
	GenerateModuleFiles.php $@ $@
	$(MAKE) -C $@ INSTALLDIR=$(INSTALLDIR)/$@ DESTDIR=$(DESTDIR) PREFIX=$(PREFIX) $(MAKECMDGOALS);
	@echo "<===" $@

packageinstall: $(SUBDIR)

install: $(SUBDIR)
#	mkdir -p $(DESTDIR)/usr/local/bin/
#	install $< $(DESTDIR)/usr/local/bin/
