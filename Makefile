PYTHON := python3
PANDOC := pandoc

.PHONY: all build test install clean doc

all: build

build:
	$(PYTHON) -m pip wheel --no-deps --wheel-dir dist .

test:
	$(PYTHON) -Wd -m unittest discover -v

install:
	$(PYTHON) -m pip install .

clean:
	$(RM) -r build dist rdumtool.egg-info

doc: README

README: README.md
	$(PANDOC) -s -t plain -o $@ $<
