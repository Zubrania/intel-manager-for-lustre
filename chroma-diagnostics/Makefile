include ../include/Makefile.version


all: rpms

cleandist:
	rm -rf dist
	mkdir dist

version:
	echo 'VERSION = "$(VERSION)"' > chroma_diagnostics/scm_version.py
	echo 'PACKAGE_VERSION = "$(PACKAGE_VERSION)"' >> chroma_diagnostics/scm_version.py
	echo 'BUILD = "$(BUILD_NUMBER)"' >> chroma_diagnostics/scm_version.py
	echo 'IS_RELEASE = $(IS_RELEASE)' >> chroma_diagnostics/scm_version.py

tarball: version
	echo "jenkins_fold:start:Make Diagnostics Tarball"
	rm -f MANIFEST
	python setup.py sdist
	echo "jenkins_fold:end:Make Diagnostics Tarball"

rpms: cleandist tarball
	echo "jenkins_fold:start:Make Diagnostics RPMS"
	rm -rf _topdir
	mkdir -p _topdir/{BUILD,S{PEC,OURCE,RPM}S,RPMS/noarch}
	cp dist/chroma-diagnostics-*.tar.gz _topdir/SOURCES
	cp chroma-diagnostics.spec _topdir/SPECS
	rpmbuild --define "_topdir $$(pwd)/_topdir" \
		--define "version $(PACKAGE_VERSION)" \
		--define "package_release $(PACKAGE_RELEASE)" \
		-bb _topdir/SPECS/chroma-diagnostics.spec
	mv _topdir/RPMS/noarch/chroma-diagnostics-*.noarch.rpm dist/
	rm -rf _topdir
	echo "jenkins_fold:end:Make Diagnostics RPMS"

docs download:
	@echo "Nothing to do here"
