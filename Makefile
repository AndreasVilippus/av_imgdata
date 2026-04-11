## You can use CC CFLAGS LD LDFLAGS CXX CXXFLAGS AR RANLIB READELF STRIP after include env.mak
include /env.mak

SUBDIR=ui

.PHONY: all clean clean_python_artifacts install $(SUBDIR)

all: $(SUBDIR)

clean: clean_python_artifacts $(SUBDIR)

clean_python_artifacts:
	find app src -type d -name '__pycache__' -prune -exec rm -rf {} +
	find app src -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

$(SUBDIR):
	@echo "===>" $@
	GenerateModuleFiles.php $@ $@
	$(MAKE) -C $@ INSTALLDIR=$(INSTALLDIR)/$@ DESTDIR=$(DESTDIR) PREFIX=$(PREFIX) $(MAKECMDGOALS);
	@echo "<===" $@

packageinstall: $(SUBDIR)

install: $(SUBDIR)
#	mkdir -p $(DESTDIR)/usr/local/bin/
#	install $< $(DESTDIR)/usr/local/bin/
